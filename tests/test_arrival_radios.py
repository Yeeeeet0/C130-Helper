import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from arrival_radios import arrival_radios
from airport_reference import associate_runway_aids,parse_sources
from route_runner import RouteRunner
from procedures import runway_direction_options
from test_route_runner import display


class ArrivalAidTests(unittest.TestCase):
    def test_runway_direction_options_pair_ends_with_their_own_ils(self):
        airport,runways=self.imported_airport()
        directions=runway_direction_options(airport,['07','25'],runways,[],'Kola')
        self.assertEqual([(r['designation'],r['heading'],r['opposite'],r['ils']['ident']) for r in directions],
                         [('07',77.8,'25','BO'),('25',257.8,'07','BD')])
        self.assertNotEqual(directions[0]['threshold']['x'],directions[1]['threshold']['x'])

    def test_runway_direction_options_keep_cdu_alias_and_parallel_pairing(self):
        airport=dict(ident='URMO',lat=0,lon=0)
        rows=[dict(name=r,lat=0,lon=i*.01,hdg=None) for i,r in enumerate(['09','27','09L','27R','09R','27L'])]
        directions=runway_direction_options(airport,[r['name'] for r in rows],rows,[],'Caucasus')
        self.assertEqual([(r['source'],r['designation'],r['cdu_designation']) for r in directions[:2]],[('09','09','10'),('27','27','28')])
        self.assertEqual(directions[2]['opposite'],'27R')
        self.assertEqual(directions[4]['opposite'],'27L')
        self.assertEqual([r['heading'] for r in directions[:2]],[94,274])
        self.assertTrue(all(r['ils'] is None for r in directions))

    def airport(self, name):
        with sqlite3.connect(Path(__file__).resolve().parents[1]/'assets/caucasus.sqlite') as c:
            lat, lon = c.execute('SELECT reference_lat_deg,reference_lon_deg FROM airfields WHERE dcs_name=?',(name,)).fetchone()
        return dict(ident='TEST',lat=lat,lon=lon)

    def test_selected_end_does_not_inherit_opposite_runway_ils(self):
        a=self.airport('Kobuleti')
        selected=arrival_radios(a,dict(runway='07'))
        self.assertEqual(selected['ils']['ident'],'IKB')
        self.assertEqual(selected['ils']['frequency'],'111.50')
        self.assertEqual(selected['tacan']['channel'],'67X')
        opposite=arrival_radios(a,dict(runway='25'))
        self.assertIsNone(opposite['ils'])
        self.assertEqual(opposite['tacan']['channel'],'67X')

    def test_cockpit_runway_overrides_source_designator(self):
        aids=arrival_radios(self.airport('Beslan'),dict(runway='09',cdu_runway='10'))
        self.assertEqual(aids['ils']['ident'],'ICH')

    def test_unassociated_airport_does_not_tune_nearby_aid(self):
        self.assertIsNone(arrival_radios(dict(ident='NONE',lat=0,lon=0),dict(runway='07'))['ils'])

    def imported_airport(self):
        airport=dict(ident='ENBO',lat=67.269203,lon=14.3653,dcs_airport=dict(aids=[
            dict(kind='ILS_GLIDESLOPE',ident='BO',frequency_hz=110300000,lat=67.266378,lon=14.341383),
            dict(kind='ILS_LOCALIZER',ident='BO',frequency_hz=110300000,direction_deg=263.905802),
            dict(kind='ILS_GLIDESLOPE',ident='BD',frequency_hz=108700000,lat=67.272442,lon=14.391316),
            dict(kind='ILS_LOCALIZER',ident='BD',frequency_hz=108700000,direction_deg=94.10579),
            dict(kind='TACAN',ident='BOO',channel=45,band='X')]))
        runways=[dict(name='07',hdg=77.8,lat=67.265297,lon=14.3183),dict(name='25',hdg=257.8,lat=67.271698,lon=14.3952)]
        associate_runway_aids(airport['dcs_airport'],runways)
        return airport,runways

    def test_imported_bodo_ils_follows_arrival_runway_and_tacan_is_airport_wide(self):
        airport,_=self.imported_airport()
        for runway,ident,frequency in [('07','BO','110.30'),('25','BD','108.70')]:
            aids=arrival_radios(airport,dict(runway=runway))
            self.assertEqual(aids['ils'],dict(ident=ident,frequency=frequency,runway=runway))
            self.assertEqual(aids['tacan'],dict(ident='BOO',channel='45X'))
            state,keys,runner=self.radio_model()
            runner.tune_arrival(aids)
            self.assertEqual((state['vor'],state['tac'],state['ident']),(frequency,'45X',ident))
            self.assertEqual(keys.count('NAV_TUNE'),1)

    def test_imported_ils_missing_or_ambiguous_runway_does_not_prevent_tacan(self):
        airport,runways=self.imported_airport()
        for aid in airport['dcs_airport']['aids']:aid.pop('runway',None)
        associate_runway_aids(airport['dcs_airport'],runways+[dict(runways[0],name='07L')])
        aids=arrival_radios(airport,dict(runway='07'))
        self.assertIsNone(aids['ils'])
        self.assertEqual(aids['tacan']['channel'],'45X')
        self.assertIsNone(arrival_radios(airport,dict(runway='04'))['ils'])

    def test_imported_tacan_requires_valid_channel_and_known_band(self):
        airport,_=self.imported_airport()
        tacan=airport['dcs_airport']['aids'][-1]
        for channel,band in [(45,None),(127,'X'),(45.5,'Y')]:
            tacan.update(channel=channel,band=band)
            self.assertIsNone(arrival_radios(airport,dict(runway='25'))['tacan'])

    def test_ground_tacan_default_band_and_explicit_band_import(self):
        raw="beacons={{beaconId='airfield7_3';type=BEACON_TYPE_TACAN;channel=45;direction=-96.3;positionGeo={latitude=67.26,longitude=14.36};}}"
        aid=parse_sources('',raw)['7']['aids'][0]
        self.assertEqual((aid['channel'],aid['band'],aid['direction_deg']),(45,'X',263.7))
        aid=parse_sources('',raw.replace('channel=45;',"channel=45;channelTACAN='46Y';"))['7']['aids'][0]
        self.assertEqual((aid['channel'],aid['band']),(46,'Y'))
        aid=parse_sources('',raw.replace('channel=45;','channel=45;system=SystemName.CUSTOM;'))['7']['aids'][0]
        self.assertNotIn('band',aid)

    def radio_model(self, reject=None, index=1):
        state=dict(page='LEGS 1',index=index,scratch='',vor='108.00',tac='001X',ident='-----')
        keys=[]
        def exchange(command):
            if command=='READ':
                if state['page']=='NAV TUNE INDEX':
                    values=['<VOR1    OFF','000','M:','',state['vor'],'<VOR2','000','M:','111.50','<TAC1','000','M:','',state['tac'],'<TAC2','000','M:','67X']
                elif state['page']=='INDEX':
                    values=[str(state['index'])+'/2']+(['NAV DATA>'] if state['index']==2 else ['RTE 1>'])
                else: values=[' IDENT',state['ident'],'FREQ','111.50']
                return display(state['page'], values, state['scratch'])
            key=command[4:];keys.append(key)
            if key=='NAV_TUNE':state['page']='NAV TUNE INDEX'
            elif key=='INDEX':state['page']='INDEX'
            elif key=='NEXT':state['index']=2
            elif key.startswith('KBD_'):state['scratch']+='.' if key=='KBD_DOT' else key[4:]
            elif state['page']=='INDEX' and key=='SELECT_7':state['page']='NAV DATA'
            elif key.startswith('SELECT_'):
                field=('vor' if key=='SELECT_7' else 'tac') if state['page']=='NAV TUNE INDEX' else 'ident'
                if reject==field:
                    if reject=='ident':state['scratch']='NOT IN DATABASE'
                    else:state['scratch']=''
                else:state[field]=state['scratch'];state['scratch']=''
            return 'OK KEY'
        return state,keys,RouteRunner(exchange,lambda _:False,lambda _:None)

    def test_tuning_keys_page_order_and_nav_data(self):
        for index in (1,2):
            state,keys,runner=self.radio_model(index=index)
            result=runner.tune_arrival(dict(ils=dict(ident='IKB',frequency='111.50'),tacan=dict(channel='67X')))
            self.assertEqual((state['vor'],state['tac'],state['ident']),('111.50','67X','IKB'))
            self.assertEqual(state['page'],'NAV DATA')
            self.assertEqual(keys.count('NAV_TUNE'),1)
            self.assertIn('KBD_DOT',keys)
            self.assertEqual(keys.count('NEXT'),1 if index==1 else 0)
            self.assertIn('NAV DATA IKB',result)

    def test_same_frequency_on_other_receiver_does_not_confirm_vor1(self):
        _,keys,runner=self.radio_model(reject='vor')
        with self.assertRaisesRegex(RuntimeError,'did not confirm VOR1'):
            runner.tune_arrival(dict(ils=dict(ident='IKB',frequency='111.50')))
        self.assertNotIn('INDEX',keys)

    def test_same_channel_on_other_receiver_does_not_confirm_tac1(self):
        _,_,runner=self.radio_model(reject='tac')
        with self.assertRaisesRegex(RuntimeError,'did not confirm TAC1'):
            runner.tune_arrival(dict(tacan=dict(channel='67X')))

    def test_rejected_nav_data_is_reported(self):
        _,_,runner=self.radio_model(reject='ident')
        with self.assertRaisesRegex(RuntimeError,'NOT IN DATABASE'):
            runner.tune_arrival(dict(ils=dict(ident='IKB',frequency='111.50')))

    def test_no_aids_sends_no_keys(self):
        _,keys,runner=self.radio_model()
        runner.tune_arrival({})
        self.assertEqual(keys,[])

    def test_missing_nav_tune_capability_rejected_before_arming(self):
        from cdu_helper import CduApi
        api=CduApi()
        with patch.object(api,'_exchange',side_effect=['OK C-130J bridge connected','OK DEL']):
            self.assertIn('Restart DCS',api.connection()['error'])
        self.assertFalse(api.status()['connected'])


if __name__=='__main__':unittest.main()
