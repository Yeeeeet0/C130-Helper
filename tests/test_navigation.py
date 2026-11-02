import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from navigation import Navigation, airway_sections, project
from cdu_helper import CduApi


def record(seq, ident='TEST', desc='E', lat=42, lon=42):
    return dict(area_code='EEU',route_identifier='A1',seqno=seq,waypoint_identifier=ident,
                waypoint_latitude=lat,waypoint_longitude=lon,waypoint_description_code=desc)


class NavigationTests(unittest.TestCase):
    def test_projection_matches_published_dcs_control_point(self):
        east,north=project(42.5172,41.8622)
        self.assertAlmostEqual(east,628703.2536546878,delta=1)
        self.assertAlmostEqual(north,-252691.23432109784,delta=1)

    def test_airway_end_and_missing_coordinate_are_not_connected(self):
        records=[record(10),record(20,desc='EEC'),record(30),record(40,lat=None),record(50),record(60)]
        sections=airway_sections(records)
        self.assertEqual([[p['seqno'] for p in s] for s in sections],[[10,20],[50,60]])

    def test_airway_direction_is_enforced_in_both_orders(self):
        nav=Navigation('not-used')
        nav._data={}
        nav.points={'one':{'ident':'ONE'},'two':{'ident':'TWO'},'three':{'ident':'THREE'}}
        nav.sections={'test':{'name':'A1','legs':[{'point':'one','direction':'F'},{'point':'two','direction':''},{'point':'three','direction':''}]}}
        self.assertEqual(len(nav.airway_slice('test',0,2)['points']),3)
        with self.assertRaises(ValueError):nav.airway_slice('test',2,0)
        self.assertEqual(nav.airway_slice('test',2,1)['points'][0]['ident'],'THREE')
        with self.assertRaises(ValueError):nav.airway_slice('test',1,1)

    def test_saved_route_cannot_replace_database_coordinates(self):
        nav=Navigation('not-used');nav._data={}
        p={'id':'f:1','ident':'TEST','lat':42,'lon':41}
        nav.points={'f:1':p}
        self.assertEqual(nav.resolve(p),p)
        for lat in [43,float('nan')]:
            with self.assertRaises(ValueError):nav.resolve({**p,'lat':lat})

    def test_database_route_uses_identifiers_not_custom_waypoint_steps(self):
        api=CduApi();nav=Navigation('not-used');nav._data={}
        origin={'id':'n:1','ident':'UGKO','lat':42.17,'lon':42.48}
        fix={'id':'f:1','ident':'IBERI','lat':42.16,'lon':41.72}
        nav.points={p['id']:p for p in [origin,fix]};api._navigation=nav
        rows=api.prepare_database_route({'origin':origin,'destination':None,'points':[fix]})['rows']
        self.assertEqual([r['value'] for r in rows],['UGKO','IBERI'])
        self.assertEqual(rows[0]['key'],'L1')
        self.assertEqual(rows[1]['key'],'')
        self.assertFalse(any('CUSTOM' in r['page'] for r in rows))


if __name__=='__main__':unittest.main()
