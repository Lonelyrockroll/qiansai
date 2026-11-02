"""Audit the published PC ZIP, independently tying all example reports to one board capture."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from pcm_tools import reference_pcm


def capture_key(case):
    pcm=case['pcm'];capture=pcm['capture']
    return (capture['capture_id'],capture['first_frame'],pcm['sha256'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kit',type=Path,default=ROOT/'output/Tang-PC-Audio-Tools.zip')
    ap.add_argument('--expected-code',help='require this physical User Code in the JTAG readback')
    ap.add_argument('--newer-than',type=Path,help='require all three capture identities to differ from this older spectrum.json')
    args=ap.parse_args();board=ROOT/'tests/contest_board';manifest=board/'spectrum.json'
    current=json.loads(manifest.read_bytes());previous=json.loads(args.newer_than.read_bytes()) if args.newer_than else None
    code=re.search(r'User Code is:\s*(0x[0-9A-Fa-f]+)',(board/'after_jtag.log').read_text())[1]
    if args.expected_code and int(args.expected_code,16)!=int(code,16):raise ValueError(f'Board readback is {code}; expected {args.expected_code}')
    kit_hash=hashlib.sha256(args.kit.read_bytes()).hexdigest()
    browser=json.loads((HERE/'results/browser-validation.json').read_bytes())
    assert browser['passed'] and browser['kit_sha256']==kit_hash and browser['served_from']=='extracted stand-alone kit'
    validation=json.loads((HERE/'results/validation.json').read_bytes());assert validation['passed']
    cases={};source_hashes={}
    with zipfile.ZipFile(args.kit) as z:
        assert z.testzip() is None
        assert z.read('tests/contest_board/spectrum.json')==manifest.read_bytes()
        for name in ('all32','off16','off17'):
            if previous and capture_key(current['cases'][name])==capture_key(previous['cases'][name]):
                raise ValueError(f'{name} is still from the preceding capture')
            raw,rate,source=reference_pcm(name)
            assert source['path']==f'tests/contest_board/{name}.pcm' and z.read(source['path'])==raw
            prefix=f'tests/pc_analysis/results/{name}/'
            for filename in ('analysis.json','analysis.png','analysis.html','peaks.csv','spectrum.csv'):
                assert z.read(prefix+filename)==(ROOT/prefix/filename).read_bytes(),prefix+filename
            report=json.loads(z.read(prefix+'analysis.json'));crc=f'{zlib.crc32(raw):08X}'
            assert report['source']==source and report['crc32']==crc and report['sha256']==hashlib.sha256(raw).hexdigest()
            v=validation['cases'][name]
            assert v['source']==source['path'] and v['crc32']==crc and v['bins']==report['peak_bins']==source['reference_bins']
            table=list(csv.DictReader(io.StringIO(z.read(prefix+'peaks.csv').decode('utf8'))))
            assert [int(row['fft_bin']) for row in table]==v['bins']
            assert all(abs(float(row['frequency_hz'])-int(row['fft_bin'])*rate/report['samples'])<1e-6 for row in table)
            replay=browser['archived_board_browser_replays'][name]
            assert int(replay['peaks'])==len(table) and abs(float(replay['xyDelayMs'])-16000/float(replay['rate']))<1e-9
            cases[name]=dict(capture_id=source['capture_id'],first_frame=source['first_frame'],pcm_sha256=report['sha256'],crc32=crc,peak_count=len(table))
        for name in ('realtime_synth/host/audio_web.py','realtime_synth/host/audio-monitor.html','realtime_synth/host/audio-monitor.js','tools/pc_audio_analysis.py'):
            assert z.read(name)==(ROOT/name).read_bytes()
            source_hashes[name]=hashlib.sha256(z.read(name)).hexdigest()
        entries=len(z.namelist())
    result=dict(passed=True,archive=args.kit.name,bytes=args.kit.stat().st_size,sha256=kit_hash,entries=entries,
        board_user_code=code,source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),cases=cases,source_hashes=source_hashes,
        browser_from=browser['served_from'],scope='ZIP bytes, source PCM, capture metadata, peak CSVs and the browser validation all match. External sound card was not exercised.')
    (HERE/'results/package-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(f'PASS final kit {kit_hash} with board {code} and 32/31/31 matching analysis reports')


if __name__=='__main__':main()
