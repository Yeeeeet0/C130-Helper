import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from route_constraints import normalise_constraint,manual_values,normalise_route_constraints
from cdu_helper import CduApi
from flight_plan_library import FlightPlanLibrary

def point(name,c=None):
    p=dict(id=name,ident=name,kind='FIX',lat=42.5,lon=43.5)
    if c:p['constraint']=c
    return p

class RouteConstraintTests(unittest.TestCase):
    def test_mach_source_recalculates_knots_when_altitude_changes(self):
        c={'speed_mach':.8,'speed_mode':'mach','altitude_ft':10000}
        low=normalise_constraint(c);high=normalise_constraint({**c,'altitude_ft':20000})
        self.assertAlmostEqual(low['speed_kt'],448.546089,places=5)
        self.assertAlmostEqual(high['speed_kt'],373.084489,places=5)
        self.assertEqual(set(low),{'speed_kt','altitude_ft'})
        self.assertEqual(manual_values(c),[('Speed','449'),('Altitude','10000')])

    def test_mach_requires_altitude_and_retains_saved_reference(self):
        for c in [{'speed_mach':.8},{'speed_mach':1.1,'altitude_ft':10000},
                  {'speed_mode':'mach','speed_kt':250},{'speed_mode':'TAS','speed_kt':250}]:
            with self.subTest(c=c),self.assertRaises(ValueError):normalise_constraint(c)
        c=normalise_constraint({'speed_mode':'mach','speed_kt':250,'altitude_ft':18000})
        self.assertEqual(c,{'speed_kt':250,'altitude_ft':18000})

    def test_native_values_and_independent_optional_fields(self):
        self.assertEqual(manual_values({'speed_kt':250}),[('Speed','250')])
        self.assertEqual(manual_values({'altitude_ft':18000,'altitude_type':'flight_level'}),[('Altitude','18000')])
        self.assertEqual(manual_values({'altitude_ft':12345}),[('Altitude','12345')])
        self.assertEqual(normalise_constraint(None),{})

    def test_rejects_invalid_or_ambiguous_values(self):
        for c in [{'speed_kt':True},{'speed_kt':float('nan')},{'speed_kt':1000},{'speed_kt':float('inf')},
                  {'altitude_ft':60001},{'altitude_ft':-1501},{'altitude_ft':18001,'altitude_type':'flight_level'},
                  {'altitude_ft':-100,'altitude_type':'flight_level'},{'altitude_type':'AGL'},{'mach':.5},'250/10000']:
            with self.subTest(c=c),self.assertRaises(ValueError):normalise_constraint(c)

    def test_manual_report_contains_constraints_without_adding_auto_fields(self):
        c={'speed_kt':250,'altitude_ft':18000,'altitude_type':'flight_level'}
        plan={'points':[point('FIX1',c),point('FIX2'),point('FIX1',{'speed_kt':180})]}
        api=CduApi();api._navigation=Mock();api._navigation.resolve.side_effect=lambda saved,**kw:saved
        prepared=api.prepare_database_route(plan)
        self.assertNotIn('error',prepared)
        self.assertEqual([r['value'] for r in prepared['rows']],['FIX1','FIX2','FIX1'])
        self.assertEqual([r['value'] for r in prepared['rows'] if r.get('position')],['FIX1','FIX2','FIX1'])
        report=api.prepare_manual_plan({'kind':'navigation','plan':plan})['report']
        rows=[r for s in report['sections'] for r in s['rows']]
        fixes=next(s for s in report['sections'] if s['title']=='Fixes')
        self.assertTrue(fixes['fix_columns'])
        self.assertEqual([(r['value'],r['speed'],r['altitude']) for r in fixes['rows']],
                         [('FIX1','250','18000'),('FIX2','',''),('FIX1','180','')])
        self.assertFalse(any(r['entry'].endswith(('SPD','ALT')) for r in rows))
        self.assertIn('<th>Speed (kt)</th>',report['table_html'])
        self.assertIn('<th>Altitude (ft)</th>',report['table_html'])
        from live_kneeboard import build_pages
        self.assertIn('SPD 250',str(build_pages(report)))
        self.assertIn('ALT 18000',str(build_pages(report)))

    def test_duplicate_with_different_constraints_requires_resolution(self):
        api=CduApi();api._navigation=Mock();api._navigation.resolve.side_effect=lambda saved,**kw:saved
        result=api.prepare_database_route({'points':[point('FIX1'),point('FIX1',{'speed_kt':200})]})
        self.assertIn('different speed/altitude',result['error'])

    def test_saved_plan_retains_constraints_and_rejects_invalid_import(self):
        plan=dict(version=1,navigation=dict(workflow=2,origin={'ident':'AAA'},destination={'ident':'BBB'},
            departure={},arrival={},approach={},points=[point('FIX1',{'speed_kt':200,'altitude_ft':5000})]))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            library=FlightPlanLibrary(folder);key=library.save('Constraints',plan)['saved']['id']
            self.assertEqual(library.load(key)['plan'],plan)
            bad=copy.deepcopy(plan);bad['navigation']['points'][0]['constraint']['speed_kt']=False
            with self.assertRaises(ValueError):library.save('Bad',bad)

    def test_canonical_values_keep_precision_and_are_idempotent(self):
        c={'speed_kt':250.125,'altitude_ft':3280.839895013123}
        for _ in range(20):self.assertEqual(normalise_constraint(c),c)
        self.assertEqual(manual_values(c),[('Speed','250'),('Altitude','3281')])

    def test_legacy_plan_migration_and_saved_files_use_only_knots_and_feet(self):
        old={'speed_kt':449,'speed_mach':.8,'speed_mode':'mach','altitude_ft':10000,'altitude_type':'flight_level'}
        route=dict(workflow=2,origin={'ident':'AAA'},destination={'ident':'BBB'},departure={},arrival={},approach={},points=[point('FIX1',old)])
        original=copy.deepcopy(route);migrated=normalise_route_constraints(route)
        self.assertEqual(route,original)
        self.assertEqual(set(migrated['points'][0]['constraint']),{'speed_kt','altitude_ft'})
        self.assertEqual(migrated['points'][0]['constraint_view'],{'speed':'mach','altitude':'flight_level'})
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            library=FlightPlanLibrary(folder);key=library.save('Legacy',dict(version=1,navigation=route))['saved']['id']
            import json
            stored=json.loads(library.path(key).read_text())['plan']['navigation']['points'][0]
            self.assertEqual(stored,migrated['points'][0])
            loaded=library.load(key)['plan']['navigation']['points'][0]
            self.assertEqual(loaded,stored)
            self.assertEqual(library.load(key)['plan']['navigation']['points'][0]['constraint']['altitude_ft'],10000)
