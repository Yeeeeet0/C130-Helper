import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation import Navigation
from procedures import terminal_candidates,validate_terminal
from cdu_helper import CduApi


class TerminalFixTests(unittest.TestCase):
    def setUp(self):
        self.nav=Navigation('unused');self.nav._data={}
        self.airport=dict(id='n:1',ident='TEST',lat=42,lon=42,kind='AIRPORT')
        self.own=dict(id='f:1',ident='OWN',lat=42.1,lon=42,kind='TERMINAL',airport='TEST')
        self.other=dict(id='f:2',ident='OTHER',lat=42.01,lon=42,kind='TERMINAL',airport='ELSE')
        self.far=dict(id='f:3',ident='FAR',lat=46,lon=42,kind='TERMINAL',airport='TEST')
        self.nav.points={p['id']:p for p in [self.airport,self.own,self.other,self.far]}
        self.options=dict(runways=['07'],runway='07',procedures=[])

    def test_associated_fixes_sort_first_and_distant_fixes_are_excluded(self):
        results=terminal_candidates(self.nav,self.airport)
        self.assertEqual([r['point']['ident'] for r in results],['OWN','OTHER'])
        self.assertTrue(results[0]['associated']);self.assertFalse(results[1]['associated'])

    @patch('procedures.airport_options')
    def test_order_defines_departure_exit_and_arrival_entry(self,options):
        options.return_value=self.options
        choice=dict(mode='terminal',runway='07',basis='atc',fixes=[self.own,self.other])
        departure=validate_terminal(self.nav,self.airport,choice,'SID')
        arrival=validate_terminal(self.nav,self.airport,choice,'STAR')
        self.assertEqual(departure['anchor']['ident'],'OTHER')
        self.assertEqual(arrival['anchor']['ident'],'OWN')
        self.assertIn('not a published',departure['guidance'])

    @patch('procedures.airport_options')
    def test_empty_nonterminal_and_distant_choices_rejected(self,options):
        options.return_value=self.options
        for fixes in [[],[self.far],[self.airport],[self.own,self.own]]:
            with self.assertRaises(ValueError):validate_terminal(self.nav,self.airport,dict(mode='terminal',runway='07',fixes=fixes),'SID')

    @patch('cdu_helper.validate_plan')
    def test_cdu_handoff_orders_custom_departure_enroute_arrival(self,validate):
        validate.return_value=dict(departure=dict(mode='terminal',runway='07',guidance='Planning only',fixes=[self.own]),arrival=dict(mode='terminal',runway='07',guidance='Planning only',fixes=[self.other]))
        api=CduApi();api._navigation=self.nav
        plan=dict(workflow=2,origin=self.airport,points=[],connection='direct')
        rows=api.prepare_database_route(plan)['rows']
        typed=[r['value'] for r in rows if not r.get('manual_only')]
        self.assertEqual(typed,['TEST','OWN','OTHER'])
        self.assertIn('custom departure',rows[-2]['label']);self.assertIn('custom arrival',rows[-1]['label'])


if __name__=='__main__':unittest.main()
