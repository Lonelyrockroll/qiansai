"""Keep invalid or repeated imports out of the latency evidence lists."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from latency_web import result_list,scope_upload


class DisplayImportTests(unittest.TestCase):
    def test_pulse_requires_both_edges_and_deduplicates(self):
        form=dict(csv='us,marker\n0,0\n1,0\n2,3.2\n3,3.1\n4,0\n5,0',
                  segment='mark-i2s',time_column='us',trigger_column='marker',
                  time_unit='us',trigger_threshold=1.5)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            row=scope_upload(form,root)
            self.assertAlmostEqual(row['us'],2)
            self.assertEqual(scope_upload(form,root),row)
            for bad in ('0,0\n1,3\n2,3\n3,3','0,0\n1,3\n2,3\n3,0\n4,3\n5,0'):
                with self.assertRaises(ValueError):scope_upload(dict(form,csv='us,marker\n'+bad),root)
            self.assertEqual(len(list((root/'digital').glob('*/record.json'))),1)

    def test_same_csv_is_one_trial_with_full_resolution_onsets(self):
        fixture=(ROOT/'tests/contest_latency/csv_examples/synthetic_rise.csv').read_text()
        form=dict(csv=fixture,segment='hall-headphone',time_unit='us',time_column='TIME_US',
                  trigger_column='HALL_V',audio_column='OUT_V',baseline_from=-30,baseline_to=0,
                  trigger_threshold=.15,audio_threshold=.1,direction='rising')
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            row=scope_upload(form,root)
            self.assertAlmostEqual(row['delay_ms'],.030)
            self.assertIn(row['t0_ms'],row['time_ms'])
            self.assertIn(row['t1_ms'],row['time_ms'])
            scope_upload(dict(form,name='同次记录换一个名称'),root)
            self.assertEqual(len(result_list(root)['scope']),1)
            self.assertEqual(len(result_list(root)['audio']),0)


if __name__=='__main__':unittest.main()
