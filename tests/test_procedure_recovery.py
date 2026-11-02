import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner, MenuItemNotFound
from test_route_runner import display


class ProcedureRecoveryTests(unittest.TestCase):
    def model(self, confirm=None, mutate=False):
        state=dict(page=1,scratch='',selected=None)
        keys=[]
        def exchange(command):
            if command=='READ':
                return display('SID REVIEW' if state['selected'] else 'DEPARTURE SIDS',
                               [str(state['page'])+'/2','RW28 URMO','<ODRI5R' if state['page']==1 else '<OTHER1','<ROUTE 1','REVIEW>'],state['scratch'])
            key=command[4:];keys.append(key)
            if key=='NEXT':state['page']=2
            elif key=='PREV':state['page']=1
            elif key=='CLR':state['scratch']=state['scratch'][:-1]
            elif key.startswith('KBD_') and key!='KBD_SPACE':state['scratch']+=key[4:]
            elif key=='SELECT_2':state['selected']='ODRI5R' if state['page']==1 else 'OTHER1'
            return 'OK KEY'
        def approval(requested,suggested):
            self.assertEqual((requested,suggested),('ODRI5U','ODRI5R'))
            self.assertEqual(state['scratch'],'')
            self.assertFalse(any(k.startswith('KBD_') or k=='CLR' for k in keys))
            self.assertIsNone(state['selected'])
            if mutate:state['scratch']='PILOT INPUT'
            if confirm:return confirm()
            return True
        return state,keys,RouteRunner(exchange,lambda _:False,lambda _:None,approval)

    def recover(self,runner):
        try:runner.menu('ODRI5U','SIDS|STARS')
        except MenuItemNotFound as ex:return runner.suggest_procedure('ODRI5U',ex,'SIDS|STARS')
        self.fail('Expected missing procedure')

    def test_accept_after_scanning_all_pages_returns_to_candidate(self):
        state,keys,runner=self.model()
        self.assertEqual(self.recover(runner),'ODRI5R')
        self.assertEqual(state['selected'],'ODRI5R')
        self.assertEqual(state['scratch'],'')
        self.assertIn('PREV',keys)
        self.assertEqual(keys.count('SELECT_2'),1)
        self.assertFalse(any(k.startswith('KBD_') or k=='CLR' for k in keys))

    def test_cancelling_does_not_select_or_clear_prompt(self):
        def cancel():raise RuntimeError('cancelled')
        state,keys,runner=self.model(confirm=cancel)
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.recover(runner)
        self.assertIsNone(state['selected'])
        self.assertNotIn('CLR',keys)

    def test_no_explicit_acceptance_cannot_resume(self):
        state,keys,runner=self.model(confirm=lambda:None)
        with self.assertRaisesRegex(RuntimeError,'not explicitly accepted'):self.recover(runner)
        self.assertIsNone(state['selected'])
        self.assertNotIn('CLR',keys)

    def test_pending_confirmation_keeps_polling_without_sending_keys(self):
        from cdu_helper import CduApi
        api=CduApi();count=[0];polls=[0];keys=[]
        def transport(sock,command):
            if command.startswith('ARM|'):return 'OK ARMED '+str(count[0])
            if command=='TRIGGER':
                polls[0]+=1
                count[0]=2 if polls[0]>=9 else 1
                if 2<=polls[0]<=9:
                    self.assertTrue(api.status()['awaiting_confirmation'])
                    self.assertFalse(api.status()['executing'])
                    self.assertEqual(keys,[])
                return 'OK '+str(count[0])
            if command.startswith('READ|'):
                return display('CAPS',[],'')
            if command.startswith('KEY|'):keys.append(command)
            return 'OK'
        class Runner:
            def __init__(self,exchange,wait,report,confirm):self.exchange,self.confirm=exchange,confirm
            def run(self,route):
                if self.confirm('ODRI5U','ODRI5R') is True:self.exchange('KEY|SELECT_2')
        with patch.object(api,'prepare_database_route',return_value={'arrival_radios':{}}), \
             patch.object(api,'_exchange',side_effect=transport), \
             patch.object(api._stop,'wait',return_value=False), \
             patch('route_runner.RouteRunner',Runner):
            api._run_route({},'pilot',{})
        self.assertEqual(keys,['KEY|pilot|SELECT_2'])
        self.assertGreaterEqual(polls[0],10)

    def test_pilot_scratchpad_input_stops_without_resuming(self):
        from cdu_helper import CduApi
        api=CduApi();count=[0];keys=[]
        def transport(sock,command):
            if command.startswith('ARM|'):return 'OK ARMED '+str(count[0])
            if command=='TRIGGER':count[0]=1;return 'OK 1'
            if command.startswith('READ|'):return display('ARRIVAL STARS',['<ODRI5R'],'PILOT INPUT')
            if command.startswith('KEY|'):keys.append(command)
            return 'OK'
        class Runner:
            def __init__(self,exchange,wait,report,confirm):self.exchange,self.confirm=exchange,confirm
            def run(self,route):
                if self.confirm('ODRI5U','ODRI5R') is True:self.exchange('KEY|SELECT_2')
        with patch.object(api,'prepare_database_route',return_value={'arrival_radios':{}}), \
             patch.object(api,'_exchange',side_effect=transport), \
             patch.object(api._stop,'wait',return_value=False), \
             patch('route_runner.RouteRunner',Runner):
            api._run_route({},'pilot',{})
        self.assertIn('denied',api.status()['message'])
        self.assertEqual(keys,[])
        self.assertFalse(api.status()['running'])

    def test_changed_scratchpad_stops_without_erasing_pilot_text(self):
        state,keys,runner=self.model(mutate=True)
        with self.assertRaisesRegex(RuntimeError,'scratchpad needs attention'):self.recover(runner)
        self.assertEqual(state['scratch'],'PILOT INPUT')
        self.assertNotIn('CLR',keys)

    def test_exact_match_never_requests_confirmation(self):
        state,keys,runner=self.model(confirm=lambda:self.fail('Unexpected confirmation'))
        runner.menu('ODRI5R','SIDS|STARS')
        self.assertEqual(state['selected'],'ODRI5R')
        self.assertFalse(any(k.startswith('KBD_') for k in keys))

    def test_empty_list_does_not_invent_procedure(self):
        _,keys,runner=self.model()
        with self.assertRaises(MenuItemNotFound):
            runner.suggest_procedure('ODRI5U',MenuItemNotFound('missing',[]),'SIDS|STARS')
        self.assertEqual(keys,[])

    def test_review_and_route_verify_replacement_name(self):
        runner=RouteRunner(lambda _:None,lambda _:False,lambda _:None,lambda *_:None)
        calls=[]
        runner.route=lambda:None
        runner.press=lambda key:calls.append(key)
        def menu(target,title):
            if title=='SIDS|STARS':raise MenuItemNotFound('missing',['ODRI5R'])
        runner.menu=menu
        runner.suggest_procedure=lambda *_:'ODRI5R'
        pages=iter([({'cni_title':'DEP/ARR INDEX'},[]),
                    ({'cni_title':'SID REVIEW'},[]),
                    ({'cni_title':'SID REVIEW'},['ODRI5R','END OF PROCEDURE','DEP SIDS>']),
                    ({'cni_title':'RTE 1'},['ODRI5R'])])
        runner.read=lambda title=None:next(pages)
        runner.procedure_list=lambda *_:None
        next(pages)
        terminal=dict(runway='28',mode='procedure',procedure=dict(name='ODRI5U',transition=''))
        runner.terminal(terminal,True)
        self.assertEqual(terminal['procedure']['name'],'ODRI5R')

    def test_caps_confirmation_is_consumed_and_execution_rearmed(self):
        from cdu_helper import CduApi
        api=CduApi()
        counts=iter([1,2,2])
        count=[0];commands=[]
        def transport(sock,command):
            commands.append(command)
            if command.startswith('READ|'):return display('CAPS', [], '')
            if command.startswith('ARM|'):return 'OK ARMED '+str(count[0])
            if command=='TRIGGER':
                count[0]=next(counts)
                return 'OK '+str(count[0])
            return 'OK'
        class Runner:
            def __init__(self,exchange,wait,report,confirm):self.exchange,self.confirm=exchange,confirm
            def run(self,route):
                self.confirm('ODRI5U','ODRI5R')
                self.exchange('READ')  # Accepted CAPS must not become Stop.
        with patch.object(api,'prepare_database_route',return_value={'arrival_radios':{}}), \
             patch.object(api,'_exchange',side_effect=transport), \
             patch.object(api._stop,'wait',return_value=False), \
             patch('route_runner.RouteRunner',Runner):
            api._run_route({},'pilot',{})
        self.assertIn('READ|pilot',commands)
        self.assertEqual([c for c in commands if c.startswith('ARM|')],['ARM|pilot|DOUBLE','ARM|pilot|DOUBLE','ARM|pilot|HOLD','ARM|pilot|DOUBLE'])
        self.assertFalse(api.status()['awaiting_confirmation'])

    def test_stop_cancels_pending_caps_approval(self):
        from cdu_helper import CduApi
        api=CduApi();count=[0]
        def transport(sock,command):
            if command.startswith('READ|'):return display('CAPS', [], '')
            if command.startswith('ARM|'):return 'OK ARMED '+str(count[0])
            if command=='TRIGGER':count[0]+=1;return 'OK '+str(count[0])
            return 'OK'
        class Runner:
            def __init__(self,exchange,wait,report,confirm):self.confirm=confirm
            def run(self,route):self.confirm('ODRI5U','ODRI5R')
        with patch.object(api,'prepare_database_route',return_value={'arrival_radios':{}}), \
             patch.object(api,'_exchange',side_effect=transport), \
             patch.object(api._stop,'wait',side_effect=[False,True]), \
             patch('route_runner.RouteRunner',Runner):
            api._run_route({},'pilot',{})
        self.assertIn('cancelled',api.status()['message'])
        self.assertFalse(api.status()['running'])

    def test_acceptance_returns_from_caps_to_correct_runway_procedure_list(self):
        for departure in (True,False):
            with self.subTest(departure=departure):
                menu_title='DEPARTURE SIDS' if departure else 'ARRIVAL STARS'
                review_title='SID REVIEW' if departure else 'STAR REVIEW'
                state=dict(page='RTE 1',accepted=False,selected=False)
                actions=[]
                def exchange(command):
                    page=state['page']
                    if command=='READ':
                        values=['1/1']
                        if page.endswith('RWYS'):values+=['<28','<ROUTE 1']
                        elif page==menu_title:values+=['RW28 TEST','<ODRI5R','<ROUTE 1','REVIEW>']
                        elif page==review_title:values+=['ODRI5R','END OF PROCEDURE','DEP SIDS>' if departure else 'ARR STARS>']
                        elif page=='RTE 1' and state['selected']:values+=['ODRI5R']
                        return display(page,values)
                    key=command[4:];actions.append((page,key))
                    if key=='SELECT_5':state['page']='DEP/ARR INDEX'
                    elif page=='DEP/ARR INDEX' and key==('SELECT_1' if departure else 'SELECT_8'):
                        state['page']='DEPARTURE RWYS' if departure else 'ARRIVAL RWYS'
                    elif page.endswith('RWYS') and key=='SELECT_2':state['page']=menu_title
                    elif page==menu_title and key=='SELECT_2':
                        self.assertTrue(state['accepted'])
                        state['selected']=True;state['page']=review_title
                    return 'OK KEY'
                def confirm(*_):
                    self.assertEqual(state['page'],menu_title)
                    state['page']='CAPS';state['accepted']=True
                    return True
                runner=RouteRunner(exchange,lambda _:False,lambda _:None,confirm)
                runner.route=lambda:state.update(page='RTE 1')
                terminal=dict(runway='27',cdu_runway='28',mode='procedure',procedure=dict(name='ODRI5U',transition=''))
                runner.terminal(terminal,departure)
                self.assertEqual(terminal['procedure']['name'],'ODRI5R')
                self.assertEqual(actions.count(('DEP/ARR INDEX','SELECT_1' if departure else 'SELECT_8')),2)
                self.assertEqual(sum(key=='SELECT_2' and page.endswith('RWYS') for page,key in actions),2)
                self.assertEqual(actions.count((menu_title,'SELECT_2')),1)
                self.assertFalse(any(key.startswith('KBD_') or key=='CLR' for _,key in actions))


if __name__=='__main__':unittest.main()
