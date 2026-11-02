"""Simulated CDU contract tests; scratchpad grammar still needs cockpit validation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner,constraint_fixes,match_constraint_fixes,route_input_count,indication,legs_rows,verify_constraint_rows
from test_discontinuities import display


class ConstraintCdu:
    def __init__(self,names,route=1):
        self.rows=[dict(name=n,speed='---',altitude='-----') for n in names]
        self.route=route;self.page=1;self.scratch='';self.keys=[];self.writes=[]
        self.reject=False;self.corrupt=None;self.delayed=False;self.pending=None
        self.propagate_altitude=False

    def exchange(self,command):
        if command=='READ':
            values=[f'{self.page}/{(len(self.rows)+4)//5}']
            for r in self.rows[(self.page-1)*5:self.page*5]:
                values+=['090^','12.4NM','----:--',r['name'],'DIR',r['speed']+'/',r['altitude']]
            values+=['ROUTE '+str(self.route)+'>','<ERASE']
            result=display('MOD LEGS '+str(self.route),values,self.scratch)
            if self.pending is not None:self.page=self.pending;self.pending=None
            return result
        key=command[4:];self.keys.append(key)
        if key=='NEXT':
            if self.delayed:self.pending=self.page+1
            else:self.page+=1
        elif key=='PREV':self.page-=1
        elif key.startswith('KBD_'):self.scratch+='/' if key=='KBD_SLASH' else key[4:]
        elif key.startswith('SELECT_'):
            index=(self.page-1)*5+int(key[7:])-7
            self.writes.append((index,self.scratch))
            if self.reject:self.scratch='INVALID ENTRY';return 'OK KEY'
            speed,alt=self.scratch.split('/')
            if speed:self.rows[index]['speed']=f'{int(speed):03d}'
            if alt:self.rows[index]['altitude']=f'{int(alt):05d}'
            if alt and self.propagate_altitude:
                for following in self.rows[index+1:]:following['altitude']=f'FL{int(alt)//100:03d}' if int(alt)%100==0 else f'{int(alt):05d}'
            self.scratch=''
            if self.corrupt:self.corrupt(self,index)
        else:raise AssertionError('Unexpected constraint key '+key)
        return 'OK KEY'


def target(ident,**constraint):return dict(ident=ident,constraint={k:str(v) for k,v in constraint.items()})


class AutoConstraintTests(unittest.TestCase):
    def runner(self,cdu):
        runner=RouteRunner(cdu.exchange,lambda _:False,lambda _:None)
        runner.route_number=cdu.route
        return runner

    def test_both_and_partial_fields_across_pages_preserve_companions(self):
        cdu=ConstraintCdu(['SID','A','B','C','D','A','DEST'],2)
        cdu.rows[2].update(altitude='FL180A')
        cdu.rows[5].update(speed='210B')
        runner=self.runner(cdu);runner.set_speed('accelerated');cdu.delayed=True
        planned=[target('A',speed=250,altitude=10000),target('B',speed=220),target('C'),target('D'),target('A',altitude=15000)]
        progress=[];runner._total=4;runner.progress=lambda n,total,label:progress.append(n)
        runner.load_constraints({'constraint_fixes':planned})
        self.assertEqual(cdu.writes,[(1,'250/10000'),(2,'220/'),(5,'/15000')])
        self.assertEqual(cdu.rows[2]['altitude'],'FL180A')
        self.assertEqual(cdu.rows[5]['speed'],'210B')
        self.assertEqual(progress,[1,2,3,4])
        self.assertFalse(any(k in ('INDEX','EXEC','DEL') for k in cdu.keys))

    def test_already_correct_fl_and_values_need_no_typing(self):
        cdu=ConstraintCdu(['A']);cdu.rows[0].update(speed='250',altitude='FL180')
        runner=self.runner(cdu);runner._total=2
        runner.load_constraints({'constraint_fixes':[target('A',speed=250,altitude=18000)]})
        self.assertEqual(cdu.writes,[]);self.assertEqual(runner._completed,2)

    def test_ambiguous_and_missing_occurrences_stop_before_any_write(self):
        for names in (['A','A'],['B']):
            cdu=ConstraintCdu(names)
            with self.assertRaisesRegex(RuntimeError,'Ambiguous|not found'):
                self.runner(cdu).load_constraints({'constraint_fixes':[target('A',speed=250)]})
            self.assertEqual(cdu.writes,[])

    def test_unconstrained_context_resolves_intentional_return(self):
        p=[target('A'),target('B'),target('A',speed=250)]
        self.assertEqual(match_constraint_fixes(p,['SID','A','B','A','DEST']),{3:p[2]})

    def test_rejection_stops_without_retry(self):
        cdu=ConstraintCdu(['A','B']);cdu.reject=True
        with self.assertRaisesRegex(RuntimeError,'0/2.*INVALID ENTRY'):
            self.runner(cdu).load_constraints({'constraint_fixes':[target('A',speed=250),target('B',speed=200)]})
        self.assertEqual(len(cdu.writes),1)

    def test_failed_readback_or_changed_companion_or_other_row_stops(self):
        for corrupt in (lambda c,i:c.rows[i].update(speed='200'),
                        lambda c,i:c.rows[i].update(altitude='09000'),
                        lambda c,i:c.rows[1].update(speed='200')):
            cdu=ConstraintCdu(['A','B']);cdu.corrupt=corrupt
            runner=self.runner(cdu)
            with self.assertRaisesRegex(RuntimeError,'Constraint entry stopped'):
                runner.load_constraints({'constraint_fixes':[target('A',speed=250),target('B',speed=220)]})
            self.assertEqual(len(cdu.writes),1);self.assertEqual(runner._completed,0)

    def test_exact_value_replaces_qualified_value(self):
        cdu=ConstraintCdu(['A']);cdu.rows[0]['speed']='250B'
        self.runner(cdu).load_constraints({'constraint_fixes':[target('A',speed=250)]})
        self.assertEqual(cdu.writes,[(0,'250/')])

    def test_no_constraints_do_not_open_cdu_and_stop_is_honoured(self):
        runner=RouteRunner(Mock(side_effect=AssertionError('Unexpected CDU access')),lambda _:False,lambda _:None)
        runner.load_constraints({'constraint_fixes':[target('A')]})
        cdu=ConstraintCdu(['A']);runner=self.runner(cdu);runner.wait=lambda _:True
        with self.assertRaisesRegex(RuntimeError,'stopped'):
            runner.load_constraints({'constraint_fixes':[target('A',speed=250)]})
        self.assertEqual(cdu.writes,[])

    def test_handover_rounding_context_negative_guard_and_progress(self):
        rows=[dict(value='A',position={'lat':1,'lon':2},constraint={'speed_kt':250.6,'altitude_ft':10000.4}),
              dict(value='B',position={'lat':2,'lon':3}),dict(value='ABC',page='RTE')]
        fixes=constraint_fixes(rows)
        self.assertEqual(fixes,[target('A',speed=251,altitude=10000),target('B')])
        self.assertEqual(route_input_count({'constraint_fixes':fixes}),5)
        rows[0]['constraint']={'altitude_ft':-100}
        with self.assertRaisesRegex(ValueError,'negative altitude'):constraint_fixes(rows)

    def test_run_orders_constraint_pass_before_radios(self):
        runner=RouteRunner(lambda _:display('RTE 1',[]),lambda _:False,lambda _:None)
        order=[]
        for name in ('clear_start_scratchpad','route','prepare_route','airport_entry','terminal'):
            setattr(runner,name,Mock())
        runner.clear_discontinuities=lambda plan:order.append('cleanup') or 0
        runner.load_constraints=lambda plan:order.append('constraints')
        runner.tune_arrival=lambda aids:order.append('radios')
        runner.run(dict(origin='AAA',destination='BBB',fixes=[],departure={},arrival={}))
        self.assertEqual(order,['cleanup','constraints','radios'])

    def test_arm_passes_ordered_constraints_to_worker(self):
        from cdu_helper import CduApi
        api=CduApi();api._navigation=Mock();api._navigation.points={};api._state['connected']=True
        api.prepare_database_route=Mock(return_value=dict(rows=[
            dict(value='A',position={'lat':1,'lon':2},constraint={'speed_kt':250}),
            dict(value='B',position={'lat':2,'lon':3})],arrival_radios={}))
        terminals=dict(departure={},arrival={})
        with patch('cdu_helper.validate_plan',return_value=terminals),patch('cdu_helper.threading.Thread') as thread:
            response=api.arm_route(dict(workflow=2,origin={'ident':'AAAA'},destination={'ident':'BBBB'}),'pilot')
        self.assertNotIn('error',response)
        route=thread.call_args.kwargs['args'][0]
        self.assertEqual(route['constraint_fixes'],[target('A',speed=250),target('B')])
        self.assertEqual(route['fixes'],['A','B'])

    def test_matching_detects_page_changes_before_writes(self):
        cdu=ConstraintCdu(['A','B']);runner=self.runner(cdu)
        original=runner.legs;calls=[]
        def legs():
            original();calls.append(True)
            if len(calls)==2:cdu.rows[0]['name']='OTHER'
        runner.legs=legs
        with self.assertRaisesRegex(RuntimeError,'changed after constraint matching'):
            runner.load_constraints({'constraint_fixes':[target('A',speed=250)]})
        self.assertEqual(cdu.writes,[])

    def test_captured_asc_banut_entry_has_valid_forward_altitude_propagation(self):
        fixtures=Path(__file__).parent/'fixtures'
        before=legs_rows(indication((fixtures/'constraint-banut-before.txt').read_text())[1],via_names=('TABA2A','ALIK1C'),constraints=True)
        after=legs_rows(indication((fixtures/'constraint-banut-after.txt').read_text())[1],via_names=('TABA2A','ALIK1C'),constraints=True)
        self.assertEqual(before[1]['name'],'BANUT')
        self.assertEqual((after[1]['speed_raw'],after[1]['altitude_raw']),('324','FL200'))
        self.assertEqual(before[3]['altitude_raw'],'10000A')
        self.assertEqual(after[3]['altitude_raw'],'FL200')
        verify_constraint_rows(before[:1],after[:1])
        verify_constraint_rows(before[2:],after[2:],'20000')

    def test_forward_propagation_continues_to_next_target_and_across_pages(self):
        cdu=ConstraintCdu(['SID','BANUT','CW001','ALIKA','N','NEXT','DEST'])
        cdu.propagate_altitude=True;cdu.rows[3]['altitude']='10000A'
        runner=self.runner(cdu);runner._total=5
        runner.load_constraints({'constraint_fixes':[target('BANUT',speed=324,altitude=20000),
            target('CW001',speed=250,altitude=15000),target('NEXT',speed=200)]})
        self.assertEqual(cdu.writes,[(1,'324/20000'),(2,'250/15000'),(5,'200/')])
        self.assertEqual(cdu.rows[3]['altitude'],'FL150')
        self.assertEqual(runner._completed,5)

    def test_forward_propagation_does_not_allow_wrong_altitude_or_speed(self):
        for corrupt in (lambda c,i:c.rows[i+1].update(altitude='FL999'),
                        lambda c,i:c.rows[i+1].update(speed='210')):
            cdu=ConstraintCdu(['A','B']);cdu.propagate_altitude=True;cdu.corrupt=corrupt
            with self.assertRaisesRegex(RuntimeError,'Constraint entry stopped'):
                self.runner(cdu).load_constraints({'constraint_fixes':[target('A',altitude=20000),target('B',speed=200)]})
            self.assertEqual(len(cdu.writes),1)

    def test_altitude_entry_cannot_change_previous_row(self):
        cdu=ConstraintCdu(['A','B']);cdu.propagate_altitude=True
        cdu.corrupt=lambda c,i:c.rows[0].update(altitude='FL200')
        with self.assertRaisesRegex(RuntimeError,'Unexpected downstream'):
            self.runner(cdu).load_constraints({'constraint_fixes':[target('B',altitude=20000)]})

    def test_combined_target_keeps_combined_syntax_after_propagation(self):
        cdu=ConstraintCdu(['A','B']);cdu.propagate_altitude=True
        self.runner(cdu).load_constraints({'constraint_fixes':[
            target('A',speed=324,altitude=20000),target('B',speed=250,altitude=20000)]})
        self.assertEqual(cdu.writes,[(0,'324/20000'),(1,'250/20000')])
