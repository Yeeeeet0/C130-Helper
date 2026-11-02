import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cdu_helper import CduApi
from manual_plan import build_report


def entry(label,value,page,key='',**more):
    return dict(label=label,value=value,page=page,key=key,instruction='Verify in cockpit.',**more)


class ManualPlanTests(unittest.TestCase):
    def test_custom_section_removed_without_losing_fix_position_or_auto_setup(self):
        api=CduApi();api._navigation=Mock()
        api._navigation.resolve.side_effect=lambda saved,**kw:saved
        plan={'points':[{'id':'custom:CW1','ident':'CW1','kind':'CUSTOM','lat':42.5,'lon':43.5,
                         'constraint':{'speed_kt':250,'altitude_ft':10000}}]}
        prepared=api.prepare_database_route(plan)
        self.assertEqual(len(prepared['custom_waypoints']),1)
        self.assertTrue(any(r['label'].endswith('/ create') for r in prepared['rows']))
        report=api.prepare_manual_plan({'kind':'navigation','plan':plan})['report']
        self.assertNotIn('Custom',[s['title'] for s in report['sections']])
        fixes=next(s for s in report['sections'] if s['title']=='Fixes')['rows']
        self.assertEqual(len(fixes),1)
        self.assertEqual(fixes[0]['value'],'CW1')
        self.assertEqual(fixes[0]['position_ddm'],'N4230.00 E04330.00')
        self.assertEqual((fixes[0]['speed'],fixes[0]['altitude']),('250','10000'))
        self.assertNotIn('CUSTOM DATA',report['html'])

    def test_route_plan_orders_sections_and_preserves_intentional_returns(self):
        custom=[entry('CW1 / create','CW1','INDEX 2 → CUSTOM DATA LIST','L1'),
                entry('CW1 / custom position','N4230.00E04230.00','CW1 CUSTOM DATA','L2')]
        prepared=dict(manual_runways={'departure':'13','arrival':'10'},rows=[
            entry('Departure / UGSB','UGSB','RTE 1 (or your chosen standby route)','L1'),
            entry('Arrival / URMO','URMO','RTE 1 (or your chosen standby route)','R1'),
            entry('SID / SID1','SID1 · RW13','DEP/ARR — departure',manual_only=True),
            entry('STAR / STAR1','STAR1 · RW10','DEP/ARR — arrival',manual_only=True),
            *custom,entry('CW1 / en-route fix','CW1','LEGS — en-route section'),
            entry('FIX2 / en-route fix','FIX2','LEGS — en-route section'),
            *custom,entry('CW1 / en-route fix','CW1','LEGS — en-route section'),
            entry('Arrival ILS / VOR1','110.30','NAV TUNE INDEX','R1'),
            entry('Arrival TACAN / TAC1','45X','NAV TUNE INDEX','R3'),
            entry('Arrival ILS / NAV DATA','ILU','INDEX page 2 → NAV DATA','L1')])
        report=build_report(prepared,'navigation',{},2)
        groups={s['title']:s['rows'] for s in report['sections']}
        self.assertEqual([r['value'] for r in groups['Fixes']],['CW1','FIX2','CW1'])
        self.assertNotIn('Custom',groups)
        self.assertNotIn('CUSTOM DATA',report['text'])
        self.assertEqual(groups['Departure'][0]['value'],'13')
        self.assertEqual(groups['Arrival'][0]['value'],'10')
        self.assertEqual(groups['Route'][0]['page'],'RTE 2')
        self.assertEqual(groups['Route'][1]['page'],'RTE 2')
        self.assertEqual([r['entry'] for r in groups['Route']],['Origin','Destination'])
        self.assertEqual([r['entry'] for r in groups['Radios']],['VOR 1','TACAN 1','Ident'])
        self.assertEqual(groups['Departure'][0]['page'],'DEP/ARR DEP')
        self.assertEqual(groups['Departure'][1]['page'],'DEP/ARR DEP')
        self.assertEqual(groups['Arrival'][1]['page'],'DEP/ARR ARR')
        self.assertEqual([r['page'] for r in groups['Radios']],['NAV TUNE INDEX','NAV TUNE INDEX','INDEX 2 → NAV DATA'])
        self.assertEqual(groups['Radios'][-1]['value'],'ILU')
        self.assertEqual(groups['Departure'][1]['key'],'Cockpit selection')
        self.assertNotIn('Preserve intentional later returns',report['text'])
        self.assertTrue(any(r['page']=='LEGS' and r['entry']=='Fix' and r['value']=='CW1' for r in groups['Fixes']))
        self.assertNotIn('Cockpit selection',report['text'])
        self.assertNotIn('Before entry',groups)
        self.assertNotIn('Final route review',groups)
        self.assertEqual(report['html'].count('<table '),2)
        self.assertEqual(report['html'].count('class="fixes-table"'),1)
        self.assertFalse(any(s['fix_columns'] for s in report['sections'] if s['title']!='Fixes'))

    def test_waypoint_plan_needs_no_dcs_connection_and_uses_ddm_and_cdu_units(self):
        with patch('socket.socket',side_effect=AssertionError('Manual plan contacted DCS')):
            result=CduApi().prepare_manual_plan(dict(kind='waypoints',route=2,
                text='ident,lat,lon,elevation_m\nCW1,42.5,-3.25,304.8'))
        self.assertNotIn('error',result)
        text=result['report']['text']
        self.assertIn('N4230.00W00315.00',text)
        fields={r['entry']:r['value'] for group in result['report']['sections'] for r in group['rows']}
        self.assertEqual(fields['Ident'],'CW1')
        self.assertEqual(fields['Position'],'N4230.00W00315.00')
        self.assertEqual(fields['Elevation'],'1000')
        self.assertEqual(fields['Insert'],'CW1')
        self.assertIn('RTE 2',text)
        self.assertNotIn(' | L2',text)

    def test_printable_html_escapes_values_and_omits_notes(self):
        bad='<script>alert("test")</script> & reference'
        report=build_report({'rows':[entry('RPI',bad,'IPRA 1/2','L1')]},'ipra',{})
        self.assertNotIn('<script>',report['html'])
        self.assertIn('&lt;script&gt;',report['html'])
        self.assertIn('@media print',report['html'])
        self.assertIn('Print / Save as PDF',report['html'])
        self.assertNotIn('category C or D',report['text'])
        self.assertIn('<th colspan="2">Page</th><th>CDU value</th>',report['html'])
        self.assertNotIn('<th>Notes</th>',report['html'])
        self.assertNotIn('Verify in cockpit.',report['html'])
        self.assertNotIn('Verify in cockpit.',report['text'])

    def test_metric_ipra_values_are_printed_in_cdu_units(self):
        report=CduApi().prepare_manual_plan(dict(kind='ipra',units='metric',
            data={'rpi':'RPI1','faf':'1.852','elevation':'304.8'}))['report']
        fields={r['label']:r['value'] for s in report['sections'] for r in s['rows']}
        self.assertEqual(fields['RPI to FAF (NM)'],'1')
        self.assertEqual(fields['RPI elevation (ft)'],'1000')
        pages={r['label']:r['page'] for s in report['sections'] for r in s['rows']}
        self.assertEqual(pages['RPI to FAF (NM)'],'IPRA 1/2')
        self.assertEqual(pages['RPI elevation (ft)'],'IPRA 1/2')

    def test_invalid_inputs_do_not_produce_a_report(self):
        api=CduApi()
        for request in [None,{},dict(kind='waypoints',text=None),dict(kind='waypoints',route=3,text='ident,lat,lon\nA,0,0'),
                        dict(kind='waypoints',text='ident,lat,lon\nA,91,0')]:
            self.assertIn('error',api.prepare_manual_plan(request))

    def test_export_saves_same_validated_plan_and_opens_only_printable_html(self):
        import webview
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            api=CduApi();api._window=Mock()
            request=dict(kind='waypoints',route=2,text='ident,lat,lon\nCW1,42.5,-3.25')
            expected=api.prepare_manual_plan(request)['report']
            for format in ('html','txt'):
                target=Path(tmp)/('manual.'+format)
                api._window.create_file_dialog.return_value=[str(target)]
                with patch('os.startfile') as start:
                    result=api.export_manual_plan(request,format)
                    self.assertNotIn('error',result)
                    self.assertEqual(target.read_text(encoding='utf-8'),expected['html' if format=='html' else 'text'])
                    self.assertEqual(start.call_count,1 if format=='html' else 0)
            api._window.create_file_dialog.return_value=None
            self.assertTrue(api.export_manual_plan(request)['cancelled'])
            self.assertIn('error',api.export_manual_plan(request,'exe'))
