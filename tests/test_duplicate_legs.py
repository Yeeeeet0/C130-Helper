import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import RouteRunner
from test_discontinuities import CniRoute


class DuplicateRoute(CniRoute):
    def __init__(self,*args,leave_gap=False,**kwargs):
        super().__init__(*args,**kwargs);self.leave_gap=leave_gap

    def exchange(self,command):
        if command.startswith('KEY|SELECT_') and self.scratch=='*DELETE*':
            row=int(command.split('_')[-1]);index=(self.leg_page-1)*5+row-1
            if 0<=index<len(self.items) and self.items[index] is not None:
                if index==0 or self.items[index]!=self.items[index-1]:raise AssertionError('Deleted a non-duplicate named waypoint')
                self.keys.append(command[4:]);self.events.append((self.title,command[4:]))
                if not self.no_delete:
                    if self.leave_gap:self.items[index]=None
                    else:self.items.pop(index)
                    if self.lose_waypoint and index<len(self.items):self.items.pop(index)
                self.scratch='';self.leg_page=min(self.leg_page,self.total)
                return 'OK KEY'
        return super().exchange(command)


class DuplicateTests(unittest.TestCase):
    def cleanup(self,items,**kwargs):
        model=DuplicateRoute(items,**kwargs)
        runner=RouteRunner(model.exchange,lambda _:False,lambda _:None)
        gaps=runner.clear_discontinuities()
        self.assertEqual(model.keys.count('INDEX'),0)
        self.assertEqual(model.keys.count('SELECT_6'),1)
        return model.items,gaps,runner.duplicates_removed

    def test_consecutive_repeats_are_removed_and_later_returns_remain(self):
        self.assertEqual(self.cleanup(['A','A','B','A','C','C']),(['A','B','A','C'],0,2))

    def test_page_boundary_repeat_is_removed(self):
        self.assertEqual(self.cleanup(['A','B','C','D','JOIN','JOIN','E']),(['A','B','C','D','JOIN','E'],0,1))

    def test_discontinuity_between_repeats_is_removed_then_duplicate(self):
        self.assertEqual(self.cleanup(['A',None,'A','B']),(['A','B'],1,1))

    def test_deleting_duplicate_can_create_a_gap(self):
        self.assertEqual(self.cleanup(['A','A','B'],leave_gap=True),(['A','B'],1,1))

    def test_repeated_rows_shifted_from_next_page_are_rechecked(self):
        self.assertEqual(self.cleanup(['A','A','A','A','A','A','B']),(['A','B'],0,5))

    def test_final_page_collapse_after_duplicate_is_verified(self):
        self.assertEqual(self.cleanup(['A','B','C','D','E','E'],collapse_last=True),(['A','B','C','D','E'],0,1))

    def test_failed_duplicate_deletion_stops(self):
        with self.assertRaisesRegex(RuntimeError,'did not remove'):self.cleanup(['A','A','B'],no_delete=True)

    def test_losing_another_named_waypoint_stops(self):
        with self.assertRaisesRegex(RuntimeError,'waypoint sequence changed'):self.cleanup(['A','A','B'],lose_waypoint=True)


if __name__=='__main__':unittest.main()
