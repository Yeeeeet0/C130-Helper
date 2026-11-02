import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation import Navigation, discover_dcs, navaid_identity
from terrains import TERRAINS


class NavaidImportTests(unittest.TestCase):
    def test_frequency_is_not_used_as_a_cdu_identifier(self):
        self.assertEqual(navaid_identity(dict(name='113.60',channel='KT',type='VOR')),('KT','VOR'))
        self.assertEqual(navaid_identity(dict(name='59',channel='MPA',type='TACAN')),('MPA','TACAN'))
        self.assertEqual(navaid_identity(dict(name='UGKO',channel='UGKO',type='AIRPORT')),('UGKO','AIRPORT'))
        self.assertEqual(navaid_identity(dict(name='0.26',channel='ABD',type='AIRPORT')),('ABD','NAVAID'))
        self.assertIsNone(navaid_identity(dict(name='',channel='',type='AIRPORT'))[0])


@unittest.skipUnless(discover_dcs(),'Installed ASC database required')
class TerrainIntegrationTests(unittest.TestCase):
    def test_kola_overview_failure_preserves_native_charts(self):
        from unittest.mock import patch
        nav=Navigation()
        with patch('kola_charts.KolaChartPyramid',side_effect=ValueError('Changed grid')):
            data=nav.load('Kola')
        self.assertTrue(data['tiles'])
        self.assertEqual({t['scale'] for t in data['tiles']},{32})

    def test_every_terrain_loads_airports_airways_and_available_charts(self):
        nav=Navigation()
        for name in TERRAINS:
            with self.subTest(terrain=name):
                data=nav.load(name)
                self.assertEqual(data['theatre'],name)
                self.assertTrue(any(p['kind']=='AIRPORT' for p in data['points']))
                self.assertTrue(data['airways'])
                self.assertTrue(all(math.isfinite(p['x']) and math.isfinite(p['y']) for p in data['points']))
                if next(t for t in data['terrain_catalog'] if t['id']==name)['charts']:
                    self.assertTrue(data['tiles'],data['chart_error'])
                    self.assertIn('dds',nav.tile(data['tiles'][0]['id']))
                else:
                    self.assertEqual(data['tiles'],[])

    def test_cache_and_tile_ids_are_isolated_between_terrains(self):
        nav=Navigation()
        caucasus=nav.load('Caucasus');point=next(p for p in caucasus['points'] if p['ident']=='UGKO' and p['kind']=='AIRPORT')
        nav.load('Syria')
        with self.assertRaises(ValueError):nav.resolve(point)
        with self.assertRaises(ValueError):nav.tile(caucasus['tiles'][0]['id'])
        self.assertIs(nav.load('Caucasus'),caucasus)
        self.assertEqual(nav.resolve(point),point)
        with self.assertRaises(ValueError):nav.load('../Syria')


if __name__=='__main__':unittest.main()
