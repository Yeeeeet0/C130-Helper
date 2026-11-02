import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cdu_helper import CduApi
from route_runner import RouteRunner
from test_route_target import Routes


def native(scratch='',error=''):
    pairs=[('cni_title','INDEX'),('cni_scratchpad',scratch),('{11111111-2222-3333-4444-555555555555}',error)]
    return 'OK DISPLAY\n'+''.join('-----------------------------------------\n'+name+'\n'+value+'\n' for name,value in pairs)


class InputSpeedTests(unittest.TestCase):
    def test_profiles_use_custom_typing_pace_or_bridge_acknowledgement_only(self):
        for speed in ('default','accelerated'):
            keys=[];waits=[]
            runner=RouteRunner(lambda c:keys.append(c) or 'OK KEY',lambda seconds:waits.append(seconds) or False,lambda _:None)
            runner.set_speed(speed);runner.type_text('ABC');runner.press('INDEX')
            self.assertEqual(keys,['KEY|KBD_A','KEY|KBD_B','KEY|KBD_C','KEY|INDEX'])
            self.assertEqual(waits,[0,.03,0,.03,0,.03,0,.35] if speed=='default' else [0]*8)

    def test_start_clears_text_and_native_error_or_delete_prompts(self):
        for error in ('INVALID ENTRY','*DELETE*',''):
            state=dict(text='OLD123',error=error);keys=[]
            def exchange(command):
                if command=='READ':return native(state['text'],state['error'])
                keys.append(command)
                if state['error']:state['error']=''
                else:state['text']=state['text'][:-1]
                return 'OK KEY'
            runner=RouteRunner(exchange,lambda _:False,lambda _:None)
            runner.clear_start_scratchpad()
            self.assertEqual(state,dict(text='',error=''))
            self.assertEqual(keys,['KEY|CLR']*(6+bool(error)))

    def test_failed_clear_stops_before_navigating_or_typing(self):
        keys=[]
        runner=RouteRunner(lambda c:native('STUCK') if c=='READ' else keys.append(c) or 'OK KEY',lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'did not clear'):runner.clear_start_scratchpad()
        self.assertEqual(keys,['KEY|CLR']*3)

    def test_start_clear_is_before_route_entry_in_both_speed_modes(self):
        for speed in ('default','accelerated'):
            model=Routes();model.routes[2]=dict(origin='',dest='',legs=[]);model.scratch='LEFT'
            original=model.exchange
            def exchange(command):
                if command=='KEY|CLR':model.keys.append((model.number,model.page,'CLR'));model.scratch=model.scratch[:-1];return 'OK KEY'
                return original(command)
            runner=RouteRunner(exchange,lambda _:False,lambda _:None)
            runner.run(dict(route_number=2,input_speed=speed,origin='AAA',destination='BBB',fixes=[],departure={},arrival={}))
            self.assertEqual([k for _,_,k in model.keys[:4]],['CLR']*4)
            self.assertEqual(model.routes[2]['dest'],'BBB')
            self.assertEqual((runner._completed,runner._total),(3,3))

    def test_unexpected_scratchpad_during_loading_is_not_automatically_erased(self):
        keys=[]
        runner=RouteRunner(lambda c:native('UNEXPECTED') if c=='READ' else keys.append(c) or 'OK KEY',lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'scratchpad needs attention'):runner.read()
        self.assertEqual(keys,[])

    def test_accelerated_waits_for_submitted_text_to_clear_but_not_other_errors(self):
        values=iter([native('ABC'),native()]);waits=[]
        runner=RouteRunner(lambda _:next(values),lambda delay:waits.append(delay) or False,lambda _:None);runner.set_speed('accelerated')
        runner.await_page('INDEX',submitted_scratch='ABC')
        self.assertEqual(waits,[.03])
        runner.exchange=lambda _:native('ABC','INVALID ENTRY')
        with self.assertRaisesRegex(RuntimeError,'INVALID ENTRY'):runner.await_page('INDEX',submitted_scratch='ABC')

    def test_invalid_speed_is_rejected_before_any_cdu_command(self):
        commands=[];runner=RouteRunner(lambda c:commands.append(c),lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'input speed'):runner.run(dict(input_speed='warp'))
        self.assertEqual(commands,[])
        self.assertIn('input speed',CduApi().arm_route(dict(workflow=2),'pilot',dict(speed='warp'))['error'])
