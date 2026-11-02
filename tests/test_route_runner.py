import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import indication, RouteRunner, require_empty_route
from test_discontinuities import legs_values


def display(title, values=(), scratch=''):
    pairs=[('cni_title',title),('cni_scratchpad',scratch)]+[(str(i),v) for i,v in enumerate(values)]
    return 'OK DISPLAY\n'+''.join('-----------------------------------------\n'+k+'\n'+v+'\n' for k,v in pairs)


class RunnerTests(unittest.TestCase):
    def test_runway_alias_keeps_procedure_data_but_selects_cockpit_name(self):
        selected=[]
        runner=RouteRunner(lambda _:display('RTE 1'),lambda _:False,lambda _:None)
        runner.route=lambda:None;runner.press=lambda _:None
        runner.menu=lambda target,title:selected.append((target,title))
        pages=iter([({'cni_title':'DEP/ARR INDEX'},[]),({'cni_title':'STAR REVIEW'},[]),
                    ({'cni_title':'STAR REVIEW'},['1/1','URMO RW28 TEST1','END OF PROCEDURE','ARR STARS>']),
                    ({'cni_title':'RTE 1'},['1/1','TEST1'])])
        runner.read=lambda title=None:next(pages)
        runner.procedure_list=lambda terminal,departure:selected.append(('28','RWYS'))
        next(pages)
        runner.terminal(dict(runway='27',cdu_runway='28',mode='procedure',procedure=dict(name='TEST1',transition='')),False)
        self.assertEqual(selected,[('28','RWYS'),('TEST1','SIDS|STARS')])

    def test_native_sid_review_does_not_press_return_to_sids(self):
        fixture=(Path(__file__).parent/'fixtures/cni-sid-review.txt').read_text()
        state={'page':'RTE 1','number':1};keys=[]
        def exchange(command):
            if command=='READ':
                if state['page']=='SID REVIEW':return 'OK DISPLAY\n'+fixture
                return display(state['page'],['1/2' if state['number']==1 else '2/2']+(['OSNI1C'] if state['number']==2 else []))
            key=command[4:];keys.append(key)
            if key=='SELECT_5':state['page']='DEP/ARR INDEX'
            elif key=='SELECT_1':state['page']='DEPARTURE RWYS'
            elif key=='NEXT':state['number']=2
            return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None)
        def route():state.update(page='RTE 1',number=1)
        def menu(target,title):state['page']='SID REVIEW' if target=='OSNI1C' else 'DEPARTURE SIDS'
        runner.route=route;runner.menu=menu
        runner.terminal(dict(runway='01',mode='procedure',procedure=dict(name='OSNI1C',transition='')),True)
        self.assertNotIn('SELECT_12',keys)
        self.assertEqual(state['number'],2)

    def test_native_review_must_be_verified_in_route(self):
        runner=RouteRunner(lambda _:display('SID REVIEW',['1/1','URKG RW01 OSNI1C','END OF PROCEDURE','DEP SIDS>']),lambda _:False,lambda _:None)
        stage=[False]
        def read(title=None):
            if stage[0]:return {'cni_title':'RTE 1'},['1/1','OTHER1C']
            return {'cni_title':'SID REVIEW'},['1/1','URKG RW01 OSNI1C','END OF PROCEDURE','DEP SIDS>']
        calls=[0]
        def route():
            calls[0]+=1
            if calls[0]>1:stage[0]=True
        runner.route=route;runner.read=read;runner.press=lambda _:None;runner.menu=lambda *_:None
        with self.assertRaisesRegex(RuntimeError,'not found in RTE 1'):
            runner.terminal(dict(runway='01',mode='procedure',procedure=dict(name='OSNI1C',transition='')),True)

    def test_fresh_cockpit_export_is_an_empty_route(self):
        raw=(Path(__file__).parent/'fixtures/cni-fresh-route.txt').read_text(encoding='utf-8')
        _,values=indication(raw)
        self.assertEqual(values[values.index('ORIGIN')+1],']]]]')
        self.assertEqual(values[values.index('DEST')+1],'')
        require_empty_route(values)
        for header in ('ORIGIN','DEST'):
            populated=values.copy();populated[populated.index(header)+1]='UGKO'
            with self.assertRaisesRegex(RuntimeError,header+' contains'):
                require_empty_route(populated)

    def test_missing_route_fields_are_not_treated_as_empty(self):
        for values in ([],['ORIGIN','----'],['ORIGIN','----','DEST']):
            with self.assertRaisesRegex(RuntimeError,'Cannot identify'):
                require_empty_route(values)

    def test_menu_search_advances_and_checks_exact_names(self):
        state={'page':1,'selected':False};keys=[]
        def exchange(command):
            if command=='READ':
                return display('SID REVIEW') if state['selected'] else display('DEPARTURE SIDS',
                    [str(state['page'])+'/2','<NALU1C' if state['page']==1 else '<NALU3C','<ROUTE 1','REVIEW>'])
            keys.append(command)
            if command=='KEY|NEXT':state['page']=2
            if command=='KEY|SELECT_2':state['selected']=True
            return 'OK KEY'
        RouteRunner(exchange,lambda _:False,lambda _:None).menu('nalu3c','SIDS')
        self.assertEqual(keys,['KEY|NEXT','KEY|SELECT_2'])

    def test_menu_stops_when_next_does_not_advance(self):
        runner=RouteRunner(lambda _:display('DEPARTURE SIDS',['1/2','<AAA']),lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'did not advance'):
            runner.menu('BBB','SIDS')

    def test_unchanged_menu_selection_is_not_success(self):
        runner=RouteRunner(lambda _:display('DEPARTURE SIDS',['1/1','<AAA']),lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'did not confirm'):
            runner.menu('AAA','SIDS')

    def test_display_and_scratchpad_guard(self):
        named, values=indication(display('RTE 1',['ORIGIN','----']).split('\n',1)[1])
        self.assertEqual(named['cni_title'],'RTE 1')
        self.assertIn('ORIGIN',values)
        runner=RouteRunner(lambda _:display('SELECT DESIRED WPT'),lambda _:False,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'Unexpected'):
            runner.read('RTE 1$')
        runner.exchange=lambda _:display('RTE 1',scratch='INVALID ENTRY')
        with self.assertRaisesRegex(RuntimeError,'INVALID ENTRY'):
            runner.read()

    def test_menu_paging_and_selection(self):
        keys=[]
        selected=[False]
        def exchange(command):
            if command=='READ':
                return display('SID REVIEW') if selected[0] else display('DEPARTURE SIDS',['1/1','<AAA','<BBB','CCC>','<ROUTE 1','REVIEW>'])
            selected[0]=command.startswith('KEY|SELECT_')
            keys.append(command)
            return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None)
        runner.menu('BBB','SIDS')
        self.assertEqual(keys,['KEY|SELECT_3'])
        keys.clear(); selected[0]=False
        runner.menu('CCC','SIDS')
        self.assertEqual(keys,['KEY|SELECT_8'])
        selected[0]=False
        with self.assertRaisesRegex(RuntimeError,'not found'):
            runner.menu('MISSING','SIDS')

    def test_stop_and_failed_acceptance(self):
        runner=RouteRunner(lambda _:display('RTE 1'),lambda _:True,lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'stopped'):
            runner.press('INDEX')
        runner.wait=lambda _:False
        with self.assertRaisesRegex(RuntimeError,'did not confirm'):
            runner.entry('UGKO',1,'RTE 1$')

    def test_complete_empty_direct_route_sequence(self):
        state={'page':'CAPS','origin':'----','dest':'----','scratch':'','fixes':[]}
        keys=[]
        def exchange(command):
            if command=='READ':
                p=state['page']
                vals=['1/2','ORIGIN',state['origin'],'DEST',state['dest'],'<LEGS 1'] if p=='RTE' else ['2/2','VIA',*(['DIRECT']*len(state['fixes'])),*(['-----']*(4-len(state['fixes']))),'TO',*state['fixes'],*(['-----']*(4-len(state['fixes']))),'<LEGS 1'] if p=='LEGS' else legs_values(state['fixes'],1,1) if p=='PROGRESS' else []
                return display('LEGS 1' if p=='PROGRESS' else 'RTE 1' if p in ('RTE','LEGS') else p,vals,state['scratch'])
            key=command[4:]; keys.append(key)
            if key=='INDEX':state['page']='INDEX'
            elif key=='SELECT_7' and state['page']=='INDEX':state['page']='RTE'
            elif key=='SELECT_6' and state['page'] in ('RTE','LEGS'):state['page']='PROGRESS'
            elif key=='NEXT':state['page']='LEGS'
            elif key.startswith('KBD_'):state['scratch']+=key[4:]
            elif key.startswith('SELECT_'):
                if state['page']=='RTE':state['origin' if key=='SELECT_1' else 'dest']=state['scratch']
                else:state['fixes'].append(state['scratch'])
                state['scratch']=''
            return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None)
        runner.run(dict(origin='UGKO',destination='UGTB',fixes=['IBERI','KTS'],departure={},arrival={}))
        self.assertEqual(state['fixes'],['IBERI','KTS'])
        self.assertNotIn('EXEC',keys)

    def test_documented_legs_page_inserts_before_destination(self):
        state={'page':'INDEX','origin':'----','dest':'----','scratch':'','fixes':[]}
        keys=[]
        def exchange(command):
            if command=='READ':
                if state['page']=='RTE':
                    values=['1/1','ORIGIN',state['origin'],'DEST',state['dest'],'<LEGS 1'];title='RTE 1'
                elif state['page']=='LEGS':
                    values=legs_values([state['origin'],*state['fixes'],state['dest']],1,1);title='LEGS 1'
                else:values=[];title='INDEX'
                return display(title,values,state['scratch'])
            key=command[4:];keys.append(key)
            if key=='INDEX':state['page']='INDEX'
            elif key=='SELECT_7' and state['page']=='INDEX':state['page']='RTE'
            elif key=='SELECT_6' and state['page']=='RTE':state['page']='LEGS'
            elif key.startswith('KBD_'):state['scratch']+=key[4:]
            elif key.startswith('SELECT_'):
                if state['page']=='RTE':state['origin' if key=='SELECT_1' else 'dest']=state['scratch']
                else:
                    self.assertEqual(int(key.split('_')[1]),len(state['fixes'])+2)
                    state['fixes'].append(state['scratch'])
                state['scratch']=''
            return 'OK KEY'
        RouteRunner(exchange,lambda _:False,lambda _:None).run(dict(origin='UGKO',destination='UGTB',fixes=['IBERI','KTS'],departure={},arrival={}))
        self.assertEqual(state['fixes'],['IBERI','KTS'])
        self.assertIn('SELECT_6',keys)


if __name__=='__main__':unittest.main()
