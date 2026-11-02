import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation import NAV_RELATIVE
from procedures import selected_runway_position
from route_runner import RouteRunner
from test_route_target import Routes
from test_route_runner import display


class AirportRoutes(Routes):
    def __init__(self):
        super().__init__()
        self.routes={n:dict(origin='',dest='',legs=[]) for n in (1,2)}
        self.custom={};self.custom_ident=''
        self.index_page=1;self.database_error=False

    def exchange(self,command):
        if command=='READ' and self.page=='INDEX':return display('INDEX',[str(self.index_page)+'/2','CUSTOM DATA>'],self.scratch)
        if command=='KEY|INDEX':self.index_page=1
        if command=='KEY|NEXT' and self.page=='INDEX':self.index_page=2;return 'OK KEY'
        if command=='KEY|SELECT_8' and self.page=='INDEX' and self.index_page==2:self.page='CUSTOM LIST';return 'OK KEY'
        if command=='KEY|CLR':self.scratch='';return 'OK KEY'
        if command=='READ' and self.page=='CUSTOM LIST':return display('CUSTOM DATA LIST',['1/2','SHOW WAYPOINT'],self.scratch)
        if command=='READ' and self.page=='CUSTOM':
            if not self.custom.get(self.custom_ident):
                raw=(Path(__file__).parent/'fixtures/unknown-airport-custom-data.txt').read_text(encoding='utf-8')
                return 'OK DISPLAY\n'+raw.replace('UG26 CUSTOM DATA',self.custom_ident+' CUSTOM DATA').replace('cni_scratchpad\n\n','cni_scratchpad\n'+self.scratch+'\n')
            return display(self.custom_ident+' CUSTOM DATA',['LAT/LON',self.custom[self.custom_ident],'POSITION',self.custom[self.custom_ident],'CUSTOM LIST>'],self.scratch)
        if command=='KEY|SELECT_2' and self.page=='CUSTOM':
            self.keys.append((self.number,self.page,'SELECT_2'))
            self.custom[self.custom_ident]=self.scratch;self.scratch='';return 'OK KEY'
        if command=='KEY|SELECT_12' and self.page=='CUSTOM':
            self.page='CUSTOM LIST';return 'OK KEY'
        if command=='KEY|SELECT_1' and self.page=='CUSTOM LIST':
            self.custom_ident=self.scratch;self.scratch='';self.page='CUSTOM';return 'OK KEY'
        if command in ('KEY|SELECT_1','KEY|SELECT_7') and self.page=='RTE' and self.scratch=='UG26' and not self.custom.get('UG26'):
            self.keys.append((self.number,self.page,command[4:]))
            if self.database_error:self.scratch='NOT IN DATABASE';return 'OK KEY'
            self.page='CUSTOM';self.custom_ident=self.scratch;self.scratch='';return 'OK KEY'
        if command=='KEY|KBD_DOT':
            self.keys.append((self.number,self.page,'KBD_DOT'));self.scratch+='.';return 'OK KEY'
        return super().exchange(command)


class AirportFallbackTests(unittest.TestCase):
    def plan(self,role='destination',number=1):
        plan=dict(route_number=number,origin='URSS',destination='UGSB',fixes=[],departure={},arrival={})
        plan[role]='UG26';side='departure' if role=='origin' else 'arrival'
        plan[side]=dict(runway='09',mode='atc')
        plan['airport_fallbacks']={role:dict(ident='UG26',custom_ident='UG26',runway='09',position='N4214.92E04237.48')}
        return plan

    def test_unknown_origin_or_destination_uses_runway_coordinates_in_selected_route(self):
        for role in ('origin','destination'):
            for number in (1,2):
                with self.subTest(role=role,number=number):
                    model=AirportRoutes();updates=[]
                    runner=RouteRunner(model.exchange,lambda _:False,lambda _:None)
                    runner.progress=lambda done,total,label:updates.append((done,total))
                    runner.run(self.plan(role,number))
                    self.assertEqual(model.custom['UG26'],'N4214.92E04237.48')
                    self.assertEqual(model.routes[number]['origin' if role=='origin' else 'dest'],'UG26')
                    self.assertEqual(model.routes[3-number],dict(origin='',dest='',legs=[]))
                    self.assertEqual(updates[-1],(5,5))
                    self.assertEqual(sum(key=='SELECT_2' and page=='CUSTOM' for _,page,key in model.keys),1)
                    self.assertTrue(any('RW09 coordinates' in text for text in runner.replacements))

    def test_existing_airfield_code_is_updated_on_later_load(self):
        model=AirportRoutes()
        RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan())
        plan=self.plan();plan['overwrite']=True
        plan['airport_fallbacks']['destination']['position']='N4215.00E04237.50'
        runner=RouteRunner(model.exchange,lambda _:False,lambda _:None)
        runner.custom_airports={'UG26'}
        runner.run(plan)
        self.assertEqual(model.routes[1]['dest'],'UG26')
        self.assertEqual(model.custom,{'UG26':'N4215.00E04237.50'})
        custom_write=next(i for i,(_,page,key) in enumerate(model.keys) if page=='CUSTOM' and key=='SELECT_2' and i>next(j for j,(_,p,k) in enumerate(model.keys) if k=='DEL'))
        airport_entry=max(i for i,(_,page,key) in enumerate(model.keys) if page=='RTE' and key=='SELECT_7')
        self.assertLess(custom_write,airport_entry)

    def test_no_selected_threshold_stops_without_substituting_airport_centre(self):
        model=AirportRoutes();plan=self.plan();plan['airport_fallbacks']={}
        with self.assertRaisesRegex(RuntimeError,'no selected runway centre'):
            RouteRunner(model.exchange,lambda _:False,lambda _:None).run(plan)
        self.assertEqual(model.custom,{})

    def test_not_in_database_message_uses_same_checked_fallback(self):
        model=AirportRoutes();model.database_error=True
        RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan())
        self.assertEqual(model.routes[1]['dest'],'UG26')
        self.assertEqual(model.custom['UG26'],'N4214.92E04237.48')

    def test_stored_airfield_position_is_replaced_under_original_code(self):
        model=AirportRoutes();model.custom['UG26']='N4200.00E04200.00'
        runner=RouteRunner(model.exchange,lambda _:False,lambda _:None);runner.custom_airports={'UG26'}
        runner.run(self.plan())
        self.assertEqual(model.custom,{'UG26':'N4214.92E04237.48'})
        self.assertEqual(model.routes[1]['dest'],'UG26')

    def test_native_procedure_is_not_silently_dropped_for_coordinate_airport(self):
        model=AirportRoutes();plan=self.plan();plan['arrival'].update(mode='procedure',procedure=dict(name='TEST1'))
        with self.assertRaisesRegex(RuntimeError,'native SID/STAR cannot be loaded'):
            RouteRunner(model.exchange,lambda _:False,lambda _:None).run(plan)
        self.assertEqual(model.custom,{})

    def test_selected_runway_midpoint_uses_both_ends_not_airport_reference(self):
        root=Path(__file__).resolve().parents[1]/'build'
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path=Path(temporary)/NAV_RELATIVE;path.parent.mkdir(parents=True)
            con=sqlite3.connect(path)
            con.execute('CREATE TABLE runways(icao TEXT,name TEXT,lat TEXT,lon TEXT)')
            con.executemany('INSERT INTO runways VALUES(?,?,?,?)',[('UG26','09','42.24909973144531','42.61600112915039'),('UG26','27','42.24810028076172','42.63330078125')]);con.commit()
            nav=type('Nav',(),dict(root=Path(temporary)))()
            airport=dict(ident='UG26',lat=42.25,lon=42.63)
            for runway in ['09','27']:
                point=selected_runway_position(nav,airport,dict(runway=runway))
                self.assertAlmostEqual(point['lon'],42.62465097,places=6)
                self.assertAlmostEqual(point['lat'],42.24860033,places=6)
                self.assertEqual(point['custom_ident'],'UG26')
                self.assertNotEqual(point['lon'],airport['lon'])
            self.assertIsNone(selected_runway_position(nav,airport,dict(runway='18')))
            con.executemany('INSERT INTO runways VALUES(?,?,?,?)',[
                ('UG26','09L','42.25','42.61'),('UG26','27R','42.25','42.63'),
                ('UG26','09R','42.26','42.61'),('UG26','27L','42.26','42.63')]);con.commit()
            left=selected_runway_position(nav,airport,dict(runway='09L'))
            right=selected_runway_position(nav,airport,dict(runway='09R'))
            self.assertAlmostEqual(left['lat'],42.25,places=6)
            self.assertAlmostEqual(right['lat'],42.26,places=6)
            con.execute("UPDATE runways SET lat='NaN' WHERE name='09'");con.commit()
            self.assertIsNone(selected_runway_position(nav,airport,dict(runway='09')))
            con.close()
