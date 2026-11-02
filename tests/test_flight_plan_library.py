import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from flight_plan_library import FlightPlanLibrary,default_root
from cdu_helper import CduApi


def full_plan():
    return dict(version=1,waypoints='ident,lat,lon\nCW1,42.5,43.5',ipra={'rpi':'CW1'},
        display={'coordinates':'DDM','units':'metric'},entry={'route':'2','manualRoute':'2','mode':'manual'},
        navigation=dict(workflow=2,terrain='Caucasus',origin={'id':'A','ident':'UGKO'},destination={'id':'B','ident':'UGSB'},
            departure={'mode':'procedure','runway':'07','cdu_runway':'07','procedure_id':'SID1'},
            arrival={'mode':'procedure','runway':'13','cdu_runway':'13','procedure_id':'STAR1'},
            approach={'mode':'atc','label':'ATC'},points=[{'id':'custom:CW1','kind':'CUSTOM','ident':'CW1','lat':42.5,'lon':43.5}]))


class FlightPlanLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'plans';self.library=FlightPlanLibrary(self.root)

    def test_entire_plan_survives_a_new_library_instance(self):
        plan=full_plan();saved=self.library.save('Training route',plan)['saved']
        loaded=FlightPlanLibrary(self.root).load(saved['id'])
        self.assertEqual(loaded['plan'],plan)
        self.assertEqual(self.library.list()['plans'][0]['origin'],'UGKO')
        self.assertEqual(self.library.list()['plans'][0]['destination'],'UGSB')

    def test_update_keeps_identity_and_other_saved_plans(self):
        first=self.library.save('One',full_plan())['saved'];other=self.library.save('Two',full_plan())['saved']
        changed=full_plan();changed['entry']['route']='1'
        updated=self.library.save('One',changed,first['id'])['saved']
        self.assertEqual(updated['id'],first['id']);self.assertEqual(updated['created_utc'],first['created_utc'])
        self.assertEqual(self.library.load(other['id'])['plan'],full_plan())
        self.assertEqual(self.library.load(first['id'])['plan'],changed)

    def test_duplicate_name_requires_explicit_update(self):
        first=self.library.save('Training',full_plan())['saved']
        with self.assertRaisesRegex(ValueError,'already saved'):self.library.save('TRAINING',full_plan())
        self.assertEqual(self.library.load(first['id'])['plan'],full_plan())

    def test_names_are_not_filesystem_paths_and_ids_cannot_escape_storage(self):
        saved=self.library.save('../../route <test>',full_plan())['saved']
        self.assertEqual(len(list(self.root.glob('*.json'))),1)
        self.assertEqual(self.library.load(saved['id'])['saved']['name'],'../../route <test>')
        for key in ('../elsewhere','C:/outside','x'*32):
            with self.assertRaises(ValueError):self.library.load(key)

    def test_failed_update_preserves_previous_file(self):
        saved=self.library.save('One',full_plan())['saved'];path=self.library.path(saved['id']);before=path.read_bytes()
        with patch.object(Path,'replace',side_effect=OSError('Disk failure')):
            with self.assertRaises(OSError):self.library.save('One',full_plan(),saved['id'])
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len(list(self.root.iterdir())),1)

    def test_corrupt_plan_does_not_hide_good_plans(self):
        self.library.save('Good',full_plan());(self.root/('a'*32+'.json')).write_text('{')
        result=self.library.list();self.assertEqual(result['unavailable'],1)
        self.assertEqual([p['name'] for p in result['plans']],['Good'])

    def test_incomplete_or_nonfinite_plans_are_rejected(self):
        for value in ({},dict(version=1,navigation={}),full_plan()):
            bad=copy.deepcopy(value)
            if 'navigation' in bad and bad['navigation'].get('workflow')==2:bad['navigation']['points'][0]['lat']=float('nan')
            with self.assertRaises(ValueError):self.library.save('Bad',bad)
        self.assertFalse(self.root.exists())

    def test_api_uses_app_library_and_frozen_path_is_outside_install_directory(self):
        api=CduApi();api._plan_library=self.library
        saved=api.save_flight_plan('In app',full_plan())['saved']
        self.assertEqual(api.load_flight_plan(saved['id'])['plan'],full_plan())
        self.assertEqual(len(api.list_flight_plans()['plans']),1)
        with patch.object(sys,'frozen',True,create=True),patch.dict('os.environ',{'LOCALAPPDATA':str(Path(self.temp.name)/'user-data')}):
            self.assertEqual(default_root(),Path(self.temp.name)/'user-data/C130JCDUHelper/flight-plans')
