"""Build and verify the small standalone PC kit. Python/runtime libraries are not bundled."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'realtime_synth/host'
sys.path.insert(0,str(HOST))
from pcm_tools import reference_pcm


def members():
    listed=['PC-AUDIO.md','启动电脑声卡观察.cmd','电脑音频分析.cmd','tools/pc_audio_analysis.py','tools/pc-analysis-requirements.txt',
            'realtime_synth/control_meter_l8/verify_board.py']
    listed+=['realtime_synth/host/'+name for name in ('audio_web.py','audio-monitor.html','audio-monitor.js','protocol.py','pcm_tools.py','transports.py','fx_tools.py')]
    for case in ('all32','off16','off17'):
        raw,rate,source=reference_pcm(case);pcm=Path(source['path']);listed.extend([pcm.as_posix(),(pcm.parent/'spectrum.json').as_posix()])
        prefix=Path('tests/pc_analysis/results')/case
        report=json.loads((ROOT/prefix/'analysis.json').read_text(encoding='utf8'))
        assert report['sha256']==hashlib.sha256(raw).hexdigest() and report['source']==source and report['sample_rate_hz']==rate, 'Regenerate example reports first'
        assert report['peak_bins']==source['reference_bins'] and report['peak_count']==source['reference_peak_count'], 'Peak evidence differs from the board manifest'
        listed += [(prefix/name).as_posix() for name in ('analysis.png','analysis.html','analysis.json','peaks.csv','spectrum.csv')]
    return sorted(set(listed))


def isolated_check(path):
    with tempfile.TemporaryDirectory(prefix='tang-pc-kit-review-') as directory:
        folder=Path(directory)
        with zipfile.ZipFile(path) as z:assert z.testzip() is None;z.extractall(folder)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        server=subprocess.Popen([sys.executable,'-S','-B',folder/'realtime_synth/host/audio_web.py','--port',str(port),'--no-browser'],cwd=folder,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            url=f'http://127.0.0.1:{port}/audio-monitor'
            for _ in range(60):
                try:
                    with urllib.request.urlopen(url,timeout=.5) as r:page=r.read().decode()
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Standalone standard-library server did not open')
            assert '电脑音频观察' in page and '打开板卡控制台' not in page
            token=page.split("MONITOR_TOKEN='",1)[1].split("'",1)[0]
            for case in ('all32','off16','off17'):
                req=urllib.request.Request(f'http://127.0.0.1:{port}/api/audio-monitor/demo?name={case}',headers={'X-Synth-Token':token})
                with urllib.request.urlopen(req,timeout=2) as response:wav=response.read()
                assert wav[:4]==b'RIFF' and wav[8:12]==b'WAVE' and len(wav)==44+8192
        finally:server.terminate();server.wait(timeout=10)
        target=folder/'independent-output'
        command=[sys.executable,'-I','-B','-X','utf8',folder/'tools/pc_audio_analysis.py','example','off17','--out',target]
        p=subprocess.run(command,cwd=folder,capture_output=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stdout.decode(errors='replace')+p.stderr.decode(errors='replace'))
        generated=next(target.glob('*/analysis.json'));meta=json.loads(generated.read_text(encoding='utf8'))
        assert meta['peak_count']==31 and 132 not in meta['peak_bins'] and (generated.parent/'analysis.png').stat().st_size>8000


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=ROOT/'output/Tang-PC-Audio-Tools.zip');args=ap.parse_args()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    files=members()
    with tempfile.TemporaryDirectory(prefix='pc-kit-',dir=args.out.parent) as staging:
        candidate=Path(staging)/args.out.name
        with zipfile.ZipFile(candidate,'w',zipfile.ZIP_DEFLATED) as z:
            for name in files:z.write(ROOT/name,name)
        isolated_check(candidate);candidate.replace(args.out)
    data=args.out.read_bytes();print('PASS isolated extraction: python -S live page, three WAVs, python -I secondary PCM render',args.out,len(data),hashlib.sha256(data).hexdigest())
