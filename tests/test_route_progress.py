import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner,route_input_count
from test_route_target import Routes
from cdu_helper import CduApi


class ProgressTests(unittest.TestCase):
    def plan(self):return dict(route_number=2,origin='UGKO',destination='UGSB',fixes=[],departure={},arrival={})

    def model(self):
        model=Routes();model.routes[2]=dict(origin='',dest='',legs=[])
        return model

    def test_all_required_fields_selections_radios_and_cleanup_are_counted(self):
        plan=self.plan();plan.update(overwrite=True,fixes=['A','B'],
            departure=dict(runway='13',mode='procedure',procedure={'transition':'FIX'}),
            arrival=dict(runway='31',mode='procedure',procedure={}),
            arrival_radios=dict(ils={'ident':'ILU'},tacan={'channel':'16X'}))
        self.assertEqual(route_input_count(plan),14)

    def test_verified_inputs_advance_to_complete(self):
        model=self.model();updates=[];runner=RouteRunner(model.exchange,lambda _:False,lambda _:None)
        runner.progress=lambda done,total,label:updates.append((done,total,label))
        runner.run(self.plan())
        self.assertEqual([(d,t) for d,t,_ in updates],[(0,3),(1,3),(2,3),(3,3)])
        self.assertEqual(updates[-1][2],'LEGS verified')

    def test_rejected_destination_is_not_counted_and_never_reaches_100(self):
        model=self.model();updates=[]
        def exchange(command):
            response=model.exchange(command)
            if command=='READ' and model.page=='RTE':return response.replace('UGSB','REJECTED')
            return response
        runner=RouteRunner(exchange,lambda _:False,lambda _:None)
        runner.progress=lambda d,t,label:updates.append((d,t))
        with self.assertRaisesRegex(RuntimeError,'did not confirm'):runner.run(self.plan())
        self.assertEqual(updates,[(0,3),(1,3)])

    def test_api_status_receives_real_runner_progress(self):
        model=self.model();count=[0];api=CduApi()
        def transport(sock,command):
            if command.startswith('ARM|'):return 'OK ARMED '+str(count[0])
            if command=='TRIGGER':count[0]=1;return 'OK 1'
            if command=='DISARM':return 'OK'
            if command.startswith('READ|'):return model.exchange('READ')
            if command.startswith('KEY|'):return model.exchange('KEY|'+command.split('|')[2])
            raise AssertionError(command)
        with patch.object(api,'prepare_database_route',return_value={'arrival_radios':{}}), \
             patch.object(api,'_exchange',side_effect=transport),patch.object(api._stop,'wait',return_value=False):
            api._run_route(self.plan(),'pilot',{})
        self.assertEqual((api.status()['sent'],api.status()['total'],api.status()['percent']),(3,3,100))


if __name__=='__main__':unittest.main()
