import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation import Navigation,discover_dcs
from procedures import airport_options,cdu_runway_for,validate_terminal
from runway_mappings import CONFIRMED,AIRFIELDS,map_runway_for
from route_runner import RouteRunner
from test_route_runner import display


class ConfirmedRunwayTests(unittest.TestCase):
    def test_left_notes_and_ticked_designations_remain_distinct(self):
        for airport,source,map_label,cdu in [
            ('UGSB','13','12','13'),('UGSB','31','30','31'),
            ('URMO','09','09','10'),('URMO','27','27','28'),
            ('URKG','01','04','01'),('URKG','19','22','19'),
            ('UGKO','07','08','07'),('UGKO','25','26','25'),
            ('UG24','14','13','14'),('UG24','32','31','32'),
            ('UG27','14','13','13'),('UG27','32','31','31'),
            ('URKK','05R','05','05'),('URKK','23L','23','23')]:
            self.assertEqual(map_runway_for(airport,source),map_label)
            self.assertEqual(cdu_runway_for(airport,source),cdu)
        self.assertEqual(len(CONFIRMED),21)
        self.assertEqual(set(AIRFIELDS),set(CONFIRMED))

    def test_cdu_menu_uses_asc_value_instead_of_dcs_label(self):
        keys=[];page=['RTE 1'];values={'RTE 1':['<DEP/ARR'],'DEP/ARR INDEX':['RTE 1'],'ARRIVAL RWYS':['1/1','<13','<31']}
        def exchange(command):
            if command=='READ':return display(page[0],values[page[0]])
            key=command[4:];keys.append(key)
            if key=='SELECT_5':page[0]='DEP/ARR INDEX'
            elif key=='SELECT_8':page[0]='ARRIVAL RWYS'
            return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None)
        selected=[];runner.menu=lambda name,title:selected.append(name)
        runner.procedure_list(dict(runway='13',cdu_runway='13'),False)
        self.assertEqual(selected,['13'])


@unittest.skipUnless(discover_dcs(),'Installed ASC database required')
class ConfirmedRunwayIntegrationTests(unittest.TestCase):
    def test_all_42_confirmed_ends_have_dcs_geometry_and_asc_menu_values(self):
        nav=Navigation();nav.load('Caucasus')
        for code,rows in CONFIRMED.items():
            with self.subTest(airport=code):
                options=airport_options(nav,code,'STAR')
                self.assertEqual(set(options['runways']),{r['source'] for r in rows})
                self.assertEqual(len(options['runway_directions']),2)
                for direction in options['runway_directions']:
                    expected=next(r for r in rows if r['source']==direction['source'])
                    self.assertEqual((direction['designation'],direction['cdu_designation'],direction['heading']),
                                     (expected['map'],expected['cdu'],expected['true_heading']))
                    other=next(r for r in options['runway_directions'] if r['source']==direction['opposite'])
                    a,b=direction['threshold'],other['threshold']
                    self.assertIsNotNone(a);self.assertIsNotNone(b)
                    lat1,lat2=map(math.radians,[a['lat'],b['lat']]);dlon=math.radians(b['lon']-a['lon'])
                    bearing=math.degrees(math.atan2(math.sin(dlon)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dlon)))%360
                    self.assertLess(abs((bearing-expected['true_heading']+180)%360-180),5)
                    airport=next(p for p in nav.points.values() if p['kind']=='AIRPORT' and p['ident']==code)
                    terminal=validate_terminal(nav,airport,dict(runway=direction['source'],mode='atc'),'STAR')
                    self.assertEqual(terminal['cdu_runway'],expected['cdu'])

    def test_crossed_out_strips_are_not_available_and_old_source_values_are_preserved(self):
        nav=Navigation();nav.load('Caucasus')
        self.assertEqual(airport_options(nav,'URSS','SID')['runways'],['06','24'])
        self.assertEqual(airport_options(nav,'UGTB','SID')['runways'],['13R','31L'])
        options=airport_options(nav,'UGSB','STAR','13')
        self.assertEqual(options['runway_details'][0]['name'],'13')
        self.assertEqual(options['runway_choices'][0],dict(source='13',designation='12',cdu_designation='13'))
        self.assertEqual(options['runway_directions'][0]['ils']['ident'],'ILU')
