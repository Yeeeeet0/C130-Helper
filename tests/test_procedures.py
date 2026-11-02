import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from procedures import compose,runway_match
from cdu_helper import CduApi,coordinate,waypoint_rows,parse_coordinate


def leg(kind,transition,ident,seq=10,path='TF'):
    return dict(procedure_identifier='TEST1',route_type=kind,transition_identifier=transition,seqno=seq,
                waypoint_identifier=ident,waypoint_latitude=42,waypoint_longitude=42,path_termination=path,
                altitude1=None,altitude2=None,altitude_description=None,speed_limit=None)


class WorkflowTests(unittest.TestCase):
    def test_sid_common_and_enroute_transition_order(self):
        rows=[leg('2','RW07','EXIT'),leg('3','NORTH','NORTH'),leg('3','SOUTH','SOUTH')]
        result=compose(rows,'SID','07')
        self.assertEqual(len(result),2)
        self.assertEqual([p['ident'] for p in result[0]['points']],['EXIT','NORTH'])
        self.assertEqual(compose(rows,'SID','25'),[])

    def test_star_enroute_common_runway_order(self):
        rows=[leg('1','ENTRY','ENTRY'),leg('2',None,'COMMON'),leg('3','RW09','FINAL')]
        result=compose(rows,'STAR','09')[0]
        self.assertEqual([p['ident'] for p in result['points']],['ENTRY','COMMON','FINAL'])
        self.assertEqual(result['anchor']['ident'],'ENTRY')
        self.assertFalse(runway_match('RW09','27'))

    def test_vectors_remain_gaps_in_procedure_preview(self):
        vector=leg('2','RW07',None,20,'VA');vector['waypoint_latitude']=None;vector['waypoint_longitude']=None
        result=compose([leg('2','RW07','FIRST'),vector,leg('2','RW07','LAST',30)],'SID','07')[0]
        self.assertIsNone(result['legs'][1]['point'])
        self.assertEqual(result['legs'][1]['path'],'VA')

    def test_ddm_input_converts_without_changing_cdu_format(self):
        self.assertAlmostEqual(parse_coordinate('S42° 30.00′',True),-42.5)
        self.assertEqual(coordinate('E04143.00',False),'E04143.00')
        self.assertEqual(coordinate(42.5,True),'N4230.00')
        for v in ['N4260.00','N9000.01','E04130.00']:
            with self.assertRaises(ValueError):parse_coordinate(v,True)

    def test_metric_csv_and_ipra_produce_native_cdu_values(self):
        rows=waypoint_rows('ident,lat,lon,elevation_m\nTEST,N4230.00,E04143.00,304.8')
        self.assertEqual(rows[1]['value'],'N4230.00E04143.00')
        self.assertEqual(rows[2]['value'],'1000')
        result=CduApi().prepare_ipra({'rpi':'TEST','elevation':'304.8','faf':'18.52'},'metric')
        self.assertEqual([r['value'] for r in result['rows']],['TEST','10','1000'])


if __name__=='__main__':unittest.main()
