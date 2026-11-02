"""CLI self-test only: synthetic CSV fixtures are not board measurements."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
SCRIPT=HERE.parents[1]/'tools/analyze_onset_csv.py'
RISE=HERE/'csv_examples/synthetic_rise.csv'
FALL=HERE/'csv_examples/synthetic_fall.csv'


def run(*paths, direction='either'):
    args=[sys.executable,'-X','utf8',str(SCRIPT),*map(str,paths),'--time-column','TIME_US',
          '--trigger-column','HALL_V','--audio-column','OUT_V','--time-unit','us',
          '--baseline','-30','-10','--direction',direction,'--trigger-threshold-v','0.30',
          '--audio-threshold-v','0.08','--audio-points','3']
    proc=subprocess.run(args,capture_output=True,text=True,encoding='utf8',timeout=20)
    return proc.returncode,json.loads(proc.stdout)


class ScopeCsvTests(unittest.TestCase):
    def test_two_polarities_glitch_rejection_and_statistics(self):
        code,result=run(RISE,FALL)
        self.assertEqual(code,0);self.assertTrue(result['all_captures_valid'])
        rise,fall=result['measurements']
        for measured,latency in ((rise,.030),(fall,.040)):
            self.assertAlmostEqual(measured['latency_ms'],latency)
            self.assertAlmostEqual(measured['sampling_bounds_ms'][0],latency-.010)
            self.assertAlmostEqual(measured['sampling_bounds_ms'][1],latency+.010)
            self.assertAlmostEqual(measured['audio_confirmed_at_ms']-measured['audio_edge_ms'][1],.020)
        stats=result['valid_only_statistics']
        for field,value in (('min_ms',.030),('median_ms',.035),('max_ms',.040),('peak_to_peak_ms',.010)):
            self.assertAlmostEqual(stats[field],value)

    def test_invalid_throws_no_zero_into_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            data=RISE.read_text();files=[]
            faults={'missing_column':data.replace('OUT_V','WRONG'),
                    'repeated_time':data.replace('50,1.40,0.26','40,1.40,0.26'),
                    'no_trigger':data.replace('1.40','1.00'),
                    'no_audio':data.replace('0.25','0.10').replace('0.26','0.10').replace('0.24','0.10'),
                    'multiple_actions':data.replace('50,1.40','50,1.00'),
                    'bad_baseline':data.replace('-30,1.00,0.10','-30,1.00,0.30'),
                    'early_audio':data.replace('-10,1.00,0.10\n','-10,1.00,0.10\n-9,1.00,0.25\n-8,1.00,0.25\n-7,1.00,0.25\n')}
            for key,contents in faults.items():
                path=Path(folder)/(key+'.csv');path.write_text(contents);files.append(path)
            code,r=run(RISE,*files)
            self.assertEqual(code,1);self.assertFalse(r['all_captures_valid']);self.assertEqual(r['valid_count'],1)
            self.assertEqual(r['invalid_count'],len(files));self.assertIsNone(r['valid_only_statistics']['peak_to_peak_ms'])
            for record in r['measurements'][1:]:
                self.assertFalse(record['valid']);self.assertIn('error',record);self.assertNotIn('latency_ms',record)
            code,r=run(RISE,direction='falling')
            self.assertEqual(code,1);self.assertIsNone(r['valid_only_statistics'])

    def test_nonuniform_sampling_and_coincident_onsets(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'uneven.csv'
            path.write_text('TIME_US,HALL_V,OUT_V\n-30,1,0\n-20,1,0\n-10,1,0\n0,1,0\n10,1.4,0\n33,1.4,0\n52,1.4,.2\n64,1.4,.2\n78,1.4,.2\n')
            code,r=run(path);self.assertEqual(code,0);m=r['measurements'][0]
            self.assertAlmostEqual(m['latency_ms'],.042);self.assertAlmostEqual(m['sampling_uncertainty_minus_ms'],.019)
            self.assertAlmostEqual(m['sampling_uncertainty_plus_ms'],.010)
            path.write_text(path.read_text().replace('10,1.4,0','10,1.4,.2').replace('33,1.4,0','33,1.4,.2'))
            code,r=run(path);self.assertEqual(code,0);m=r['measurements'][0]
            self.assertEqual(m['latency_ms'],0);self.assertFalse(m['strict_order_resolved'])
            self.assertLess(m['sampling_bounds_ms'][0],0);self.assertGreater(m['sampling_bounds_ms'][1],0)


if __name__=='__main__':unittest.main(verbosity=2)
