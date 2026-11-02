import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from procedures import cdu_runway_for,runway_alignment


class RunwayAlignmentTests(unittest.TestCase):
    def test_both_beslan_ends_and_old_saved_defaults(self):
        for source,cdu in [('09','10'),('27','28')]:
            self.assertEqual(cdu_runway_for('URMO',source),cdu)
            self.assertEqual(cdu_runway_for('URMO',source,source),cdu)
            self.assertEqual(cdu_runway_for('URMO',source,cdu),cdu)
        with self.assertRaisesRegex(ValueError,'CDU RW10'):
            cdu_runway_for('URMO','09','28')

    def test_designation_mapping_does_not_rewrite_course(self):
        rows=runway_alignment(dict(ident='URMO'),[dict(name='09',hdg='102')],
                              [dict(designator='10',true_course_deg=93.5424)])
        self.assertEqual(rows[0]['cdu_runway'],'10')
        self.assertEqual(rows[0]['asc_course'],102)
        self.assertEqual(rows[0]['dcs_true_course'],93.5424)
        self.assertEqual(rows[0]['asc_course_reference'],'unspecified')
        self.assertTrue(rows[0]['live_verified'])

    def test_large_heading_conflict_is_flagged_not_silently_corrected(self):
        row=runway_alignment(dict(ident='TEST'),[dict(name='14',hdg='140.3')],
                             [dict(designator='14',true_course_deg=312.2556)])[0]
        self.assertEqual(row['cdu_runway'],'14')
        self.assertFalse(row['live_verified'])
        self.assertIn('course sources disagree',row['status'])

    def test_unknown_airport_keeps_explicit_choice_and_missing_heading(self):
        self.assertEqual(cdu_runway_for('TEST','09'),'09')
        self.assertEqual(cdu_runway_for('TEST','09','10'),'10')
        row=runway_alignment(dict(ident='TEST'),[dict(name='09',hdg='')],[])[0]
        self.assertIsNone(row['asc_course'])
        self.assertFalse(row['live_verified'])


if __name__=='__main__':unittest.main()
