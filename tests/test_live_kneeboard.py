import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cdu_helper import CduApi
from live_kneeboard import build_pages,publish,parse_status,WIDTHS,LINES


def report():
    return CduApi().prepare_manual_plan({'kind':'waypoints','text':'ident,lat,lon\nCW1,42.5,43.5'})['report']


class LiveKneeboardTests(unittest.TestCase):
    def test_layout_marks_sections_entries_and_wrapped_continuations(self):
        content=build_pages({'subtitle':'Test','sections':[{'title':'Departure','rows':[
            {'page':'DEP/ARR DEP','entry':'SID','value':'A'*40},
            {'page':'RTE 1','entry':'Origin','value':'URSS'}]}]})
        self.assertEqual(content['pages'][0]['LAYOUT'],'SRCR')
        self.assertEqual(len(content['pages'][0]['PAGE'].split('\n')),4)

    def test_pages_preserve_input_values_and_have_bounded_columns(self):
        content=build_pages(report())
        self.assertIn('N4230.00E04330.00','\n'.join(p['VALUE'] for p in content['pages']))
        for page in content['pages']:
            for column,width in WIDTHS.items():
                self.assertLessEqual(len(page[column].splitlines()),LINES)
                self.assertTrue(all(len(line)<=width for line in page[column].splitlines()))
                self.assertTrue(page[column].isascii())

    def test_maximum_csv_plan_fits_reserved_capacity_without_truncation(self):
        text='ident,lat,lon,elevation_ft\n'+'\n'.join(f'CW{i},42.5,43.5,1000' for i in range(100))
        prepared=CduApi().prepare_manual_plan({'kind':'waypoints','text':text})['report']
        content=build_pages(prepared)
        self.assertLessEqual(len(content['pages']),20)
        self.assertIn('CW99','\n'.join(p['VALUE'] for p in content['pages']))

    def test_publish_uses_only_text_protocol_and_requires_commit_ack(self):
        calls=[]
        def exchange(command):
            calls.append(command);parts=command.split('|')
            if parts[0]=='KB_STATUS':return 'OK KB_STATUS 1 1 0 20 -'
            if parts[0]=='KB_BEGIN':return 'OK KB_BEGIN '+parts[1]
            if parts[0]=='KB_DATA':return 'OK KB_DATA '+' '.join(parts[1:4])
            return 'OK KB_COMMITTED '+parts[1]+' 1'
        result=publish(exchange,report())
        self.assertEqual(result['pages'],1)
        self.assertTrue(all(c.startswith('KB_') for c in calls))
        self.assertTrue(all(len(c)+33<=4096 for c in calls))
        with self.assertRaisesRegex(ValueError,'not verified'):
            publish(lambda c:'OK WRONG' if c.startswith('KB_COMMIT') else exchange(c),report())

    def test_no_send_if_page_not_loaded_or_capacity_exceeded(self):
        exchange=Mock(return_value='OK KB_STATUS 1 0 0 20 -')
        with self.assertRaisesRegex(ValueError,'not loaded'):publish(exchange,report())
        self.assertEqual(exchange.call_count,1)
        huge={'subtitle':'Too long','sections':[{'title':'Fixes','rows':[{'page':'LEGS','entry':'Fix','value':'A'}]*500}]}
        with self.assertRaisesRegex(ValueError,'capacity'):publish(exchange,huge)
        self.assertEqual(exchange.call_count,1)

    def test_status_and_api_fail_closed_and_release_publish_guard(self):
        self.assertTrue(parse_status('OK KB_STATUS 1 1 2 20 abc')['ready'])
        with self.assertRaises(ValueError):parse_status('OK OLD BRIDGE')
        api=CduApi();api._state['running']=True
        self.assertIn('error',api.send_manual_kneeboard({}))
        api._state['running']=False
        self.assertIn('error',api.send_manual_kneeboard({}))
        self.assertFalse(api.status()['kneeboard_sending'])
        with patch.object(api,'_exchange',side_effect=RuntimeError('ERROR unsupported request')):
            result=api.send_manual_kneeboard({'kind':'waypoints','text':'ident,lat,lon\nCW1,42,43'})
        self.assertIn('Updated live-kneeboard bridge',result['error'])
        self.assertFalse(api.status()['kneeboard_sending'])
