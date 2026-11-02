import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation import Navigation,project,unproject
from terrains import TERRAINS
from cdu_helper import CduApi,waypoint_rows
from route_runner import RouteRunner,route_input_count,indication
from test_route_runner import display


class CustomWaypointTests(unittest.TestCase):
    def test_click_positions_round_trip_on_every_terrain(self):
        for theatre,settings in TERRAINS.items():
            bounds=settings[3]
            for lat,lon in [settings[4],((bounds[0]+bounds[1])/2,(bounds[2]+bounds[3])/2)]:
                actual=unproject(*project(lat,lon,theatre),theatre)
                self.assertAlmostEqual(actual[0],lat,places=6)
                self.assertAlmostEqual(actual[1],lon,places=6)

    def nav(self):
        nav=Navigation('unused');nav._data={};nav.points={}
        return nav

    def test_custom_points_validate_and_recompute_saved_map_position(self):
        nav=self.nav();point=dict(id='custom:CW001',ident='CW001',kind='CUSTOM',lat=42,lon=41,x=0,y=0)
        actual=nav.resolve(point,allow_custom=True)
        self.assertEqual((actual['x'],actual['y']),project(42,41))
        with self.assertRaises(ValueError):nav.resolve(point)
        for bad in [dict(point,lat=float('nan')),dict(point,ident='BAD NAME'),dict(point,id='custom:OTHER')]:
            with self.assertRaises(ValueError):nav.resolve(bad,allow_custom=True)
        nav.points={'existing':dict(ident='CW001')}
        with self.assertRaisesRegex(ValueError,'already exists'):nav.resolve(point,allow_custom=True)

    def test_custom_handover_keeps_creation_separate_from_route_fixes(self):
        api=CduApi();api._navigation=self.nav()
        point=dict(id='custom:CW001',ident='CW001',kind='CUSTOM',lat=42,lon=41)
        checked=api.prepare_database_route(dict(points=[point]))
        self.assertNotIn('error',checked)
        self.assertEqual(checked['custom_waypoints'],[dict(ident='CW001',position='N4200.00E04100.00')])
        self.assertEqual([r['value'] for r in checked['rows'] if r.get('position')],['CW001'])
        self.assertEqual(checked['rows'][1]['value'],'N4200.00E04100.00')
        self.assertEqual(checked['rows'][1]['key'],'L2')
        self.assertEqual(waypoint_rows('ident,lat,lon\nCW001,42,41')[1]['key'],'L2')

    def model(self,existing=False,reject=False):
        state=dict(page='INDEX',number=1,scratch='',ident='',position='N00^00.00 E000^00.00' if existing else '')
        keys=[]
        def exchange(command):
            if command=='READ':
                if state['page']=='INDEX':values=[str(state['number'])+'/2','CUSTOM DATA>']
                elif state['page']=='CUSTOM DATA LIST':values=['1/20','CW001' if existing else '-----']
                elif state['page']=='CW001 CUSTOM DATA' and not state['position']:
                    raw=(Path(__file__).parent/'fixtures/custom_data_before.txt').read_text(encoding='utf-8')
                    # Keep the real exported GUID/blank-field structure.
                    return 'OK DISPLAY\n'+raw.replace('cni_scratchpad\n\n','cni_scratchpad\n'+state['scratch']+'\n')
                else:values=['LAT/LON',state['position'],'POSITION','-----','CUSTOM LIST>']
                return display(state['page'],values,state['scratch'])
            key=command[4:];keys.append(key)
            if key=='INDEX':state.update(page='INDEX',number=1)
            elif key=='NEXT':state['number']=2
            elif key.startswith('KBD_'):state['scratch']+='.' if key=='KBD_DOT' else key[4:]
            elif key=='SELECT_8':state['page']='CUSTOM DATA LIST'
            elif key=='SELECT_12':state['page']='CUSTOM DATA LIST'
            elif key=='SELECT_1':
                if state['page']=='CUSTOM DATA LIST':
                    state.update(page=state['scratch']+' CUSTOM DATA',ident=state['scratch'])
                    if not existing:state['position']=''
                    state['scratch']=''
                # LAT/LON L1 is display-only: retain scratchpad, as in the log.
            elif key=='SELECT_2':
                if not reject:state['position']=state['scratch']
                state['scratch']=''
            return 'OK KEY'
        return state,keys,RouteRunner(exchange,lambda _:False,lambda _:None)

    def test_custom_creation_checks_position_and_reuses_list_footer(self):
        state,keys,runner=self.model()
        waits=[];runner.wait=lambda delay:waits.append(delay) or False
        points=[dict(ident='CW001',position='N4200.00E04100.00'),dict(ident='CW002',position='N4300.00E04100.00')]
        runner.create_custom_waypoints(points)
        self.assertEqual(state['position'],points[-1]['position'])
        self.assertEqual(keys.count('INDEX'),0)  # already on INDEX
        self.assertEqual(keys.count('SELECT_12'),1)
        self.assertEqual(keys.count('SELECT_2'),2)
        self.assertEqual(keys.count('SELECT_1'),2)  # identifiers only
        self.assertEqual(keys.count('NEXT'),1)  # INDEX 2 only; no list scan
        self.assertEqual(waits.count(.03),sum(len(p['ident'])+len(p['position']) for p in points))
        self.assertEqual(route_input_count(dict(fixes=['CW001'],custom_waypoints=points)),8)

    def test_existing_custom_position_is_updated_in_place(self):
        state,keys,runner=self.model(existing=True)
        runner.create_custom_waypoints([dict(ident='CW001',position='N4200.00E04100.00')])
        self.assertEqual(state['position'],'N4200.00E04100.00')
        self.assertEqual(keys.count('SELECT_2'),1)

    def test_rejected_coordinate_update_stops(self):
        _,_,runner=self.model(reject=True)
        with self.assertRaisesRegex(RuntimeError,'did not confirm'):
            runner.create_custom_waypoints([dict(ident='CW001',position='N4200.00E04100.00')])

    def test_reuses_existing_matching_page_without_typing_or_navigation(self):
        state,keys,runner=self.model(existing=True)
        state.update(page='CW001 CUSTOM DATA',position='N42^00.00 E041^00.00')
        runner.create_custom_waypoints([dict(ident='CW001',position='N4200.00E04100.00')])
        self.assertEqual(keys,[])

    def test_fast_typing_must_match_complete_scratchpad_before_submission(self):
        _,keys,runner=self.model()
        original=runner.exchange
        def dropped(command):
            if command=='KEY|KBD_N':return 'OK KEY'
            return original(command)
        runner.exchange=dropped
        with self.assertRaisesRegex(RuntimeError,'complete entry'):
            runner.create_custom_waypoints([dict(ident='CW001',position='N4200.00E04100.00')])
        self.assertNotIn('SELECT_2',keys)

    def test_recorded_failure_retains_coordinates_on_display_only_row(self):
        raw=(Path(__file__).parent/'fixtures/custom_data_l1_rejected.txt').read_text(encoding='utf-8')
        named,values=indication(raw)
        self.assertEqual(named['cni_scratchpad'],'N4341.56E04018.33')
        self.assertEqual(values[values.index('LAT/LON')+1],'')
        self.assertIn('POSITION',values)
