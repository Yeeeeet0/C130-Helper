import math
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner,indication,legs_rows
from cdu_helper import CduApi


def display(title,values,scratch=''):
    pairs=[('cni_title',title),('cni_scratchpad',scratch)]+[(str(i),v) for i,v in enumerate(values)]
    return 'OK DISPLAY\n'+''.join('-----------------------------------------\n'+k+'\n'+v+'\n' for k,v in pairs)


def legs_values(items,page,total):
    values=[str(page)+'/'+str(total)]
    for item in items:
        values+=['090^','12.4NM','----:--',item or '-----']
        if item is None:values+=['>> DISCONTINUITY <<']
        values+=['DIR','---/','-----']
    if len(items)<5:values+=['---^','---NM','----:--','-----','','---/','-----']
    return values+['ROUTE 1>','<PROGRESS']


class CniRoute:
    def __init__(self,items,no_delete=False,lose_waypoint=False,alternate_prompt=False,collapse_last=False):
        self.items=items.copy();self.leg_page=1;self.title='RTE 1';self.scratch='';self.keys=[];self.events=[]
        self.no_delete=no_delete;self.lose_waypoint=lose_waypoint
        self.alternate_prompt=alternate_prompt;self.collapse_last=collapse_last

    @property
    def total(self):return max(1,math.ceil((len(self.items)+(0 if self.collapse_last else 1))/5))

    def exchange(self,command):
        if command=='READ':
            if self.title=='INDEX':return display('INDEX',['1/2'],self.scratch)
            if self.title=='RTE 1':return display('RTE 1',['1/6','ORIGIN','UGKO','DEST','URMO','<LEGS 1'],self.scratch)
            offset=5*(self.leg_page-1)
            result=display('LEGS 1',legs_values(self.items[offset:offset+5],self.leg_page,self.total),'' if self.alternate_prompt else self.scratch)
            if self.alternate_prompt and self.scratch:
                result+='-----------------------------------------\n{SCRATCH-ERROR-GUID}\n'+self.scratch+'\n'
            return result
        key=command[4:];self.keys.append(key);self.events.append((self.title,key))
        if key=='INDEX':self.title='INDEX'
        elif key=='SELECT_7' and self.title=='INDEX':self.title='RTE 1'
        elif key=='SELECT_6' and self.title=='RTE 1':self.title='LEGS 1'
        elif key in ('NEXT','PREV'):
            if self.title!='LEGS 1':raise AssertionError('Cleanup paged through RTE / alternate instead of LEGS')
            self.leg_page=min(self.total,max(1,self.leg_page+(1 if key=='NEXT' else -1)))
        elif key=='DEL':
            if self.title!='LEGS 1':raise AssertionError('DEL was sent outside LEGS')
            self.scratch='*DELETE*'
        elif key.startswith('SELECT_') and self.scratch=='*DELETE*':
            row=int(key.split('_')[1])
            if self.title!='LEGS 1' or not 1<=row<=5:raise AssertionError('Deletion did not use a LEGS left line-select key')
            index=5*(self.leg_page-1)+row-1
            if index>=len(self.items) or self.items[index] is not None:
                raise AssertionError('Attempted to delete a named waypoint / trailing empty entry')
            if not self.no_delete:
                self.items.pop(index)
                if self.lose_waypoint and index<len(self.items):self.items.pop(index)
            self.leg_page=min(self.leg_page,self.total);self.scratch=''
        return 'OK KEY'


class DiscontinuityTests(unittest.TestCase):
    def test_cleanup_proceeds_when_delete_prompt_has_a_guid(self):
        cni=CniRoute(['GNV','OSNIR',None,'SM','RANIS'],alternate_prompt=True)
        count=RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities()
        self.assertEqual(count,1)
        self.assertEqual(cni.items,['GNV','OSNIR','SM','RANIS'])
        index=cni.keys.index('DEL')
        self.assertEqual(cni.keys[index+1],'SELECT_3')

    def test_live_delete_prompt_uses_an_alternate_scratch_element(self):
        folder=Path(__file__).parent/'fixtures'
        plain=(folder/'cni-legs-discontinuity.txt').read_text(encoding='utf-8')
        armed=(folder/'cni-legs-delete-armed.txt').read_text(encoding='utf-8')
        before,values=indication(plain);after,armed_values=indication(armed)
        self.assertEqual(before['cni_scratchpad'],'')
        self.assertEqual(after['cni_scratchpad'],'*DELETE*')
        rows=legs_rows(values,{'GNV','OSNIR','SM','RANIS'},{'OSNI1C'})
        self.assertEqual(rows,legs_rows(armed_values,{'GNV','OSNIR','SM','RANIS'},{'OSNI1C'}))
        self.assertTrue(rows[2]['discontinuity'])
        runner=RouteRunner(lambda _:'OK DISPLAY\n'+armed,lambda _:False,lambda _:None)
        self.assertEqual(runner.read('LEGS 1$',allow_delete=True)[0]['cni_scratchpad'],'*DELETE*')
        with self.assertRaisesRegex(RuntimeError,'scratchpad needs attention'):
            runner.read('LEGS 1$')

    def test_old_bridge_is_rejected_before_route_entry(self):
        api=CduApi()
        with patch.object(api,'_exchange',side_effect=['OK C-130J bridge connected',RuntimeError('ERROR unsupported request')]) as exchange:
            result=api.connection()
        self.assertIn('Restart DCS',result['error'])
        self.assertFalse(api.status()['connected'])
        self.assertEqual([call.args[1] for call in exchange.call_args_list],['PING','CAPABILITIES'])

    def test_legs_parser_identifies_the_left_discontinuity_row(self):
        values=legs_values(['RW01',None,'OSNIR'],1,1)
        rows=legs_rows(values)
        self.assertEqual([i+1 for i,r in enumerate(rows) if r['discontinuity']],[2])
        self.assertEqual([r['name'] for r in rows if r['name']],['RW01','OSNIR'])

    def test_virtual_leg_names_are_preserved_with_blank_time_fields(self):
        values=['1/1','---^','12.4','-----','(INTC)','SID','---/','07000A','ROUTE 1>']
        self.assertEqual(legs_rows(values),[dict(name='(INTC)',discontinuity=False)])

    def test_empty_discontinuities_without_speed_altitude_fields(self):
        values=['1/1','---^','-----','>> DISCONTINUITY <<','DIR',
                '---^','-----','>> DISCONTINUITY <<','',
                '090^','12.4NM','----:--','NEXT','DIR','---/','05000','ROUTE 1>']
        self.assertEqual(legs_rows(values),[dict(name=None,discontinuity=True),dict(name=None,discontinuity=True),dict(name='NEXT',discontinuity=False)])

    def test_trailing_empty_discontinuity_and_unused_insertion_row(self):
        values=['1/1','---^','-----','>> DISCONTINUITY <<','DIR','-----','ROUTE 1>']
        self.assertEqual(legs_rows(values),[dict(name=None,discontinuity=True)])

    def test_removes_multiple_pages_consecutive_and_final_gaps(self):
        cni=CniRoute(['A',None,'B','C',None,None,'D','E','F',None])
        count=RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities()
        self.assertEqual(count,4)
        self.assertEqual(cni.items,['A','B','C','D','E','F'])
        self.assertEqual(cni.keys.count('DEL'),4)
        self.assertNotIn('EXEC',cni.keys)
        self.assertTrue(all(title=='LEGS 1' for title,key in cni.events if key in ('DEL','NEXT','PREV')))

    def test_page_boundary_discontinuities_use_l5_then_rescan(self):
        cni=CniRoute(['A','B','C','D',None,None,'E'])
        runner=RouteRunner(cni.exchange,lambda _:False,lambda _:None)
        self.assertEqual(runner.clear_discontinuities(),2)
        self.assertEqual(cni.items,['A','B','C','D','E'])
        for i,(_,key) in enumerate(cni.events):
            if key=='DEL':self.assertEqual(cni.events[i+1],('LEGS 1','SELECT_5'))

    def test_entering_legs_never_presses_an_erase_prompt(self):
        keys=[]
        def exchange(command):
            if command=='READ':return display('RTE 1',['1/6','<ERASE'])
            keys.append(command);return 'OK KEY'
        runner=RouteRunner(exchange,lambda _:False,lambda _:None);runner.route=lambda:None
        with self.assertRaisesRegex(RuntimeError,'ERASE'):
            runner.legs()
        self.assertEqual(keys,[])

    def test_history_page_is_excluded_from_main_route_scan(self):
        class HistoryRoute(CniRoute):
            @property
            def total(self):return super().total+1
            def exchange(self,command):
                if command=='READ' and self.title=='LEGS 1' and self.leg_page==self.total:
                    return display('LEGS 1 HIST',legs_values(['OLD'],self.leg_page,self.total))
                return super().exchange(command)
        cni=HistoryRoute(['A',None])
        count=RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities()
        self.assertEqual(count,1)
        self.assertEqual(cni.items,['A'])
        self.assertEqual(cni.keys.count('INDEX'),0)

    def test_single_forward_pass_opens_legs_only_once(self):
        items=['W'+str(i) for i in range(20)]
        items.insert(2,None);items.insert(13,None)
        cni=CniRoute(items)
        self.assertEqual(RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities(),2)
        self.assertEqual(cni.items,['W'+str(i) for i in range(20)])
        self.assertEqual(cni.keys.count('INDEX'),0)
        self.assertEqual(cni.keys.count('SELECT_6'),1)
        self.assertEqual(cni.keys.count('NEXT'),4)
        self.assertEqual(cni.keys.count('PREV'),0)

    def test_final_page_collapse_rechecks_previous_page_in_place(self):
        cni=CniRoute(['A','B','C','D','E',None],collapse_last=True)
        self.assertEqual(RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities(),1)
        self.assertEqual(cni.items,['A','B','C','D','E'])
        self.assertEqual(cni.keys.count('INDEX'),0)

    def test_trailing_unused_row_is_preserved(self):
        cni=CniRoute(['A','B'])
        self.assertEqual(RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities(),0)
        self.assertNotIn('DEL',cni.keys)

    def test_failed_removal_stops_after_one_attempt(self):
        cni=CniRoute(['A',None,'B'],no_delete=True)
        with self.assertRaisesRegex(RuntimeError,'did not remove'):
            RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities()
        self.assertEqual(cni.keys.count('DEL'),1)

    def test_waypoint_sequence_change_stops_cleanup(self):
        cni=CniRoute(['A',None,'B','C'],lose_waypoint=True)
        with self.assertRaisesRegex(RuntimeError,'waypoint sequence changed'):
            RouteRunner(cni.exchange,lambda _:False,lambda _:None).clear_discontinuities()
        self.assertEqual(cni.keys.count('DEL'),1)

    def test_marker_without_an_empty_row_is_not_deleted(self):
        values=['1/1','090^','12.4NM','----:--','NAMED','>> DISCONTINUITY <<','DIR','---/','-----','ROUTE 1>']
        with self.assertRaisesRegex(RuntimeError,'empty LEGS'):
            legs_rows(values)


if __name__=='__main__':unittest.main()
