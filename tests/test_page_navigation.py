import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner
from test_route_runner import display
from test_discontinuities import CniRoute


class NavigationTests(unittest.TestCase):
    def test_sid_star_verification_and_legs_use_current_page_links(self):
        for number in (1,2):
            with self.subTest(route=number):
                state=dict(page='RTE',number=1);keys=[]
                def exchange(command):
                    page=state['page']
                    if command=='READ':
                        if page=='RTE':
                            values=[str(state['number'])+'/3','<DEP/ARR','<LEGS '+str(number)]+(['ORIGIN','AAA','DEST','BBB'] if state['number']==1 else ['ASID1'] if state['number']==2 else ['ASTAR1'])
                            return display('RTE '+str(number),values)
                        if page=='DEP/ARR INDEX':return display(page,['RTE '+str(number)])
                        if page.endswith('RWYS'):return display(page,['1/1','<13','<ROUTE '+str(number)])
                        if page in ('DEPARTURE SIDS','ARRIVAL STARS'):return display(page,['1/1','<ASID1' if page=='DEPARTURE SIDS' else '<ASTAR1','<ROUTE '+str(number),'REVIEW>'])
                        if page in ('SID REVIEW','STAR REVIEW'):return display(page,['1/1','ASID1' if page=='SID REVIEW' else 'ASTAR1','END OF PROCEDURE','DEP SIDS>' if page=='SID REVIEW' else 'ARR STARS>','<ROUTE '+str(number)])
                        return display('LEGS '+str(number),['1/1','ROUTE '+str(number)+'>'])
                    key=command[4:];keys.append((page,state['number'],key))
                    if page=='RTE' and key=='SELECT_5':state['page']='DEP/ARR INDEX'
                    elif page=='DEP/ARR INDEX' and key in ('SELECT_1','SELECT_8'):state['page']='DEPARTURE RWYS' if key=='SELECT_1' else 'ARRIVAL RWYS'
                    elif page.endswith('RWYS') and key=='SELECT_2':state['page']='DEPARTURE SIDS' if page.startswith('DEPARTURE') else 'ARRIVAL STARS'
                    elif page in ('DEPARTURE SIDS','ARRIVAL STARS') and key=='SELECT_2':state['page']='SID REVIEW' if page=='DEPARTURE SIDS' else 'STAR REVIEW'
                    elif page.endswith('REVIEW') and key=='SELECT_6':state.update(page='RTE',number=1)
                    elif page=='RTE' and key=='NEXT':state['number']+=1
                    elif page=='RTE' and key=='SELECT_6':state['page']='LEGS'
                    else:raise AssertionError('Unnecessary or incorrect navigation: '+str((page,key)))
                    return 'OK KEY'
                runner=RouteRunner(exchange,lambda _:False,lambda _:None);runner.route_number=number
                runner.terminal(dict(runway='13',mode='procedure',procedure=dict(name='ASID1',transition='')),True)
                runner.terminal(dict(runway='13',mode='procedure',procedure=dict(name='ASTAR1',transition='')),False)
                runner.legs()
                self.assertNotIn('INDEX',[k for _,_,k in keys])
                self.assertIn(('RTE',2,'SELECT_5'),keys)
                self.assertIn(('RTE',3,'SELECT_6'),keys)
                self.assertEqual(sum(p.endswith('REVIEW') and k=='SELECT_6' for p,_,k in keys),2)

    def test_already_on_legs_does_not_reopen_route(self):
        model=CniRoute(['A','B','C','D','E','F']);model.title='LEGS 1';model.leg_page=2
        runner=RouteRunner(model.exchange,lambda _:False,lambda _:None)
        runner.legs()
        self.assertEqual(model.keys,['PREV'])

    def test_already_on_route_header_sends_no_navigation_keys(self):
        model=CniRoute(['A'])
        RouteRunner(model.exchange,lambda _:False,lambda _:None).route()
        self.assertEqual(model.keys,[])

    def test_index_route_label_uses_r1_or_r2_not_the_legs_footer_key(self):
        for number in (1,2):
            state=['INDEX'];keys=[]
            def exchange(command):
                if command=='READ':return display(state[0],['1/2','ROUTE 1>','ROUTE 2>','PROGRESS>'])
                key=command[4:];keys.append(key)
                if key=='SELECT_'+str(6+number):state[0]='RTE '+str(number)
                return 'OK KEY'
            runner=RouteRunner(exchange,lambda _:False,lambda _:None);runner.route_number=number
            runner.route()
            self.assertEqual(keys,['SELECT_'+str(6+number)])


if __name__=='__main__':unittest.main()
