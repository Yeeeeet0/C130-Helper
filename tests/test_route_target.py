import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner,indication,legs_rows
from test_route_runner import display
from test_discontinuities import legs_values


class Routes:
    def __init__(self, stale_legs=False, retain_destination=False):
        self.routes={n:dict(origin='OLD'+str(n),dest='END'+str(n),legs=['OLD'+str(n),'KEEP'+str(n),'END'+str(n)]) for n in (1,2)}
        self.page='INDEX';self.number=1;self.scratch='';self.keys=[]
        self.stale_legs=stale_legs;self.retain_destination=retain_destination

    def exchange(self,command):
        r=self.routes[self.number]
        if command=='READ':
            if self.page=='INDEX':return display('INDEX',['1/2'],self.scratch)
            if self.page=='RTE':return display('RTE '+str(self.number),['1/1','ORIGIN',r['origin'],'DEST',r['dest'],'<LEGS '+str(self.number)],self.scratch)
            return display('LEGS '+str(self.number),[v.replace('ROUTE 1>','ROUTE '+str(self.number)+'>') for v in legs_values(r['legs'],1,1)],self.scratch)
        key=command[4:];self.keys.append((self.number,self.page,key))
        if key=='INDEX':self.page='INDEX'
        elif self.page=='INDEX' and key in ('SELECT_7','SELECT_8'):self.number=int(key[-1])-6;self.page='RTE'
        elif key=='SELECT_12' and self.page=='LEGS':self.page='RTE'
        elif key=='SELECT_6' and self.page=='RTE':self.page='LEGS'
        elif key=='DEL':self.scratch='*DELETE*'
        elif key.startswith('KBD_'):self.scratch+=key[4:]
        elif key in ('SELECT_1','SELECT_7') and self.page=='RTE':
            label='origin' if key=='SELECT_1' else 'dest'
            if self.scratch=='*DELETE*':
                r[label]=''
                if label=='origin':
                    if not self.retain_destination:r['dest']=''
                    if not self.stale_legs:r['legs']=[]
            else:
                r[label]=self.scratch
                r['legs']=[v for v in [r['origin'],r['dest']] if v]
            self.scratch=''
        return 'OK KEY'


class RouteTargetTests(unittest.TestCase):
    def plan(self,n=2,overwrite=True):
        return dict(route_number=n,overwrite=overwrite,origin='UGKO',destination='UGSB',fixes=[],departure={},arrival={})

    def empty_pages(self, second=None, stuck=False):
        folder=Path(__file__).parent/'fixtures'
        pages={p:'OK DISPLAY\n'+(folder/f'cni-empty-legs-2-page-{p}.txt').read_text(encoding='utf-8') for p in (1,2)}
        if second is not None:pages[2]=display('LEGS 2',[v.replace('ROUTE 1>','ROUTE 2>') for v in legs_values(second,2,2)])
        state=dict(page=0);keys=[]
        def exchange(command):
            if command=='READ':return pages[state['page']] if state['page'] else display('RTE 2',['1/3','ORIGIN',']]]]','DEST',''])
            key=command[4:];keys.append(key)
            if key=='NEXT' and not stuck:state['page']+=1
            return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None);runner.route_number=2
        runner.legs=lambda:state.update(page=1)
        runner.route=lambda:state.update(page=0)
        return runner,keys,pages

    def test_live_two_blank_pages_are_both_verified_and_accepted(self):
        runner,keys,pages=self.empty_pages()
        for response in pages.values():
            _,values=indication(response.split('\n',1)[1])
            self.assertFalse(any(r['name'] is not None or r['discontinuity'] for r in legs_rows(values,route_number=2)))
        runner.prepare_route(overwrite=True)
        self.assertEqual(keys,['NEXT'])

    def test_named_leg_on_second_page_blocks_new_input(self):
        runner,keys,_=self.empty_pages(second=['KEEP2'])
        with self.assertRaisesRegex(RuntimeError,'still contains LEGS'):runner.prepare_route(overwrite=True)
        self.assertEqual(keys,['NEXT'])

    def test_discontinuity_on_second_page_blocks_new_input(self):
        runner,keys,_=self.empty_pages(second=[None])
        with self.assertRaisesRegex(RuntimeError,'still contains LEGS'):runner.prepare_route(overwrite=True)
        self.assertEqual(keys,['NEXT'])

    def test_stuck_blank_page_is_not_assumed_to_clear_next_page(self):
        runner,keys,_=self.empty_pages(stuck=True)
        with self.assertRaisesRegex(RuntimeError,'did not advance'):runner.prepare_route(overwrite=True)
        self.assertEqual(keys,['NEXT'])

    def test_overwrite_clears_only_selected_route_then_loads_it(self):
        for n in (1,2):
            for retain in (False,True):
                with self.subTest(route=n,retain_destination=retain):
                    model=Routes(retain_destination=retain);other=copy.deepcopy(model.routes[3-n])
                    RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan(n))
                    self.assertEqual(model.routes[3-n],other)
                    self.assertEqual(model.routes[n],dict(origin='UGKO',dest='UGSB',legs=['UGKO','UGSB']))
                    self.assertIn((n,'RTE','SELECT_1'),model.keys)
                    self.assertFalse(any(key=='EXEC' for _,_,key in model.keys))

    def test_no_overwrite_keeps_occupied_route_untouched(self):
        model=Routes();before=copy.deepcopy(model.routes)
        with self.assertRaisesRegex(RuntimeError,'RTE 2 must be empty'):
            RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan(overwrite=False))
        self.assertEqual(model.routes,before)
        self.assertFalse(any(k=='DEL' or k.startswith('KBD_') for _,_,k in model.keys))

    def test_no_overwrite_loads_empty_selected_route(self):
        model=Routes();model.routes[2]=dict(origin='',dest='',legs=[])
        RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan(overwrite=False))
        self.assertEqual(model.routes[2]['origin'],'UGKO')
        self.assertFalse(any(k=='DEL' for _,_,k in model.keys))

    def test_retained_legs_stop_overwrite_before_any_new_input(self):
        model=Routes(stale_legs=True)
        with self.assertRaisesRegex(RuntimeError,'still contains LEGS'):
            RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan())
        self.assertFalse(any(k.startswith('KBD_') for _,_,k in model.keys))
        self.assertEqual(model.routes[1]['origin'],'OLD1')

    def test_wrong_route_title_prevents_deletion(self):
        model=Routes()
        def exchange(command):
            result=model.exchange(command)
            return result.replace('RTE 2','RTE 1') if command=='READ' else result
        with self.assertRaisesRegex(RuntimeError,'Unexpected CDU page'):
            RouteRunner(exchange,lambda _:False,lambda _:None).run(self.plan())
        self.assertFalse(any(k=='DEL' for _,_,k in model.keys))

    def test_invalid_route_is_rejected_before_any_commands(self):
        model=Routes()
        for invalid in (0,3,True,'2'):
            with self.assertRaisesRegex(RuntimeError,'Choose RTE'):
                RouteRunner(model.exchange,lambda _:False,lambda _:None).run(self.plan(invalid))
        self.assertEqual(model.keys,[])

    def test_api_freezes_selected_route_and_overwrite_when_arming(self):
        from cdu_helper import CduApi
        api=CduApi();api._state['connected']=True
        plan=dict(workflow=2,origin={'ident':'UGKO'},destination={'ident':'UGSB'})
        with patch.object(api,'prepare_database_route',return_value={'rows':[],'arrival_radios':{}}), \
             patch('cdu_helper.validate_plan',return_value={'departure':{},'arrival':{}}), \
             patch('cdu_helper.threading.Thread') as thread:
            result=api.arm_route(plan,'pilot',dict(route=2,overwrite=True,speed='accelerated'))
        self.assertNotIn('error',result)
        route=thread.call_args.kwargs['args'][0]
        self.assertEqual((route['route_number'],route['overwrite'],route['input_speed']),(2,True,'accelerated'))


if __name__=='__main__':unittest.main()
