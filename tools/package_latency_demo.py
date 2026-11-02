"""Build the portable latency demo; verify its unpacked server and CSV import in isolation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'output/Tang-延迟实测展示.zip'


def members():
    files = set()
    def add(path):
        path = (ROOT/path).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'Missing or external kit resource: {path}')
        files.add(path.relative_to(ROOT).as_posix())
    for name in ('启动延迟实测.cmd','延迟展示包使用说明.md','延迟测试接线.md','AMPERO-LATENCY.md',
                 'OUTPUT-CALIBRATION.md','OUTPUT-HARMONICS.md','赛题二问答与验收测量.md',
                 'tools/analyze_onset_csv.py','tools/capture_latency_ampero.py','tools/measure_live_mark.py','tools/report_fixed_key_latency.py','tools/load_guide_sram.py',
                 'tools/validate_guide_build.py','fpga/check_sources.py','fpga/display.cst','fpga/audio_tx.v',
                 'fpga/keyboard_input.v','fpga/onset_meter.v','realtime_synth/control_meter_l8/verify_board.py',
                 'hardware/pcb/ProPrj_nos_pico_32key_TypeC5V_1LED_ADC_2026-09-26.epro2',
                 'realtime_synth/control_white_keys/tb_white_keys.v','tests/output_trim/tb_quad.v',
                 'tests/contest_board/onset_board.json','tests/contest_latency/README.md',
                 'tests/contest_latency/results/recovery.json','tests/contest_latency/results/gate_hold/validation.json',
                 'tests/contest_latency/test_latency_display.py','tests/contest_latency/test_scope_csv.py',
                 'tests/contest_latency/csv_examples/synthetic_rise.csv','tests/contest_latency/csv_examples/synthetic_fall.csv'):
        add(name)
    for name in ('server.py','latency_web.py','latency-monitor.html','latency-monitor.css','latency-monitor.js',
                 'audio_web.py','audio-monitor.html','audio-monitor.js','pcm_tools.py','fx_tools.py','protocol.py',
                 'transports.py','keypad_config.py','control_keypad_mapping.json','index.html','keypad.html',
                 'keypad_input.py','touch_bridge.py','touch_hid.py','touch_logic.py'):
        add(Path('realtime_synth/host')/name)
    for name in ('all32','off16','off17'):
        for folder in ('tests/contest_board','tests/contest_board/intermediate-F939'):
            pcm = Path(folder)/(name+'.pcm')
            if (ROOT/pcm).exists() and (ROOT/folder/'spectrum.json').exists():
                add(pcm)
                add(Path(folder)/'spectrum.json')
                break
        else:
            raise FileNotFoundError('Missing PCM evidence: '+name)
    found_history = False
    for path in sorted((ROOT/'output/latency').glob('*/*/record.json')):
        row = json.loads(path.read_text(encoding='utf8'))
        if path.parents[1].name=='audio':
            original = path.parent/row['raw_wav']
            if not original.resolve().is_relative_to(path.parent) or hashlib.sha256(original.read_bytes()).hexdigest()!=row['wav_sha256']:
                raise ValueError(f'{path}: WAV has changed')
            if row['source_kind']=='historical_ampero':
                found_history = True
                add(path.parent/'original_metadata.json')
            add(original)
            add(path.parent/row['timeseries'])
        if (path.parent/'capture.csv').is_file():
            add(path.parent/'capture.csv')
        add(path)
    if not found_history:
        raise FileNotFoundError('Missing historical Ampero evidence')
    for trial in (ROOT/'output/latency/acquisitions').glob('*/agreement.json'):
        for name in ('agreement.json','board.json','setup.json','scope.json'):
            add(trial.parent/name)
    for summary in (ROOT/'output/latency/acquisitions').glob('*/speaker_summary.json'):
        add(summary)
        for name in ('criteria.json','fixed_config.json','cal_points.json','restored.json','idle.csv','held.csv','idle.json','held.json','quiet_1x.csv','quiet_1x.json'):
            add(summary.parent/name)
        for trial in json.loads(summary.read_text(encoding='utf8'))['trials']:
            capture=trial['capture']
            for suffix in ('.csv','.json','_association.json'):
                add(summary.parent/(capture+suffix))
    return sorted(files)


def isolated_check(archive):
    with tempfile.TemporaryDirectory(prefix='tang-latency-demo-') as tmp:
        folder=Path(tmp)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError('ZIP CRC error')
            z.extractall(folder)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        host=folder/'realtime_synth/host/server.py'
        log=folder/'test-server.log'
        with log.open('wb') as sink:
            server=subprocess.Popen([sys.executable,'-E','-s','-B','-X','utf8',str(host),'--no-browser',
                                     '--latency-page','--port',str(port)],cwd=folder,stdout=sink,stderr=sink,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for _ in range(120):
                    if server.poll() is not None:
                        raise RuntimeError(log.read_text(encoding='utf8',errors='replace'))
                    try:
                        with urlopen(origin+'/latency-monitor',timeout=1) as response:
                            page=response.read().decode('utf8')
                        break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError('Isolated latency server did not start')
                token=re.search(r'<meta name="session-token" content="([^"]+)">', page)[1]
                headers={'X-Synth-Token':token,'Origin':origin,'Content-Type':'application/json'}
                def read(url, data=None):
                    request=Request(origin+url,headers=headers,data=data)
                    with urlopen(request,timeout=10) as response:
                        return response.read()
                for url in ('/latency-monitor.js','/latency-monitor.css','/latency-wiring','/audio-monitor','/audio-monitor.js'):
                    assert len(read(url))>500,url
                before=json.loads(read('/api/latency/results'))
                assert before['digital'], 'Missing archived FPGA evidence'
                entry=next(e for e in before['audio'] if e.get('kind')=='historical_ampero')
                with (folder/'output/latency/audio'/entry['wav_url'].split('/')[-1]/'record.json').open(encoding='utf8') as source:
                    record=json.load(source)
                assert hashlib.sha256(read(entry['wav_url'])).hexdigest()==record['wav_sha256']
                example=folder/'tests/contest_latency/csv_examples/synthetic_rise.csv'
                form=dict(name='隔离包装验收用合成样例',csv=example.read_text(encoding='utf8'),segment='hall-headphone',
                          time_unit='us',time_column='TIME_US',trigger_column='HALL_V',audio_column='OUT_V',baseline_from=-30,
                          baseline_to=0,trigger_threshold=.15,audio_threshold=.1,direction='rising')
                answer=json.loads(read('/api/latency/scope-csv',json.dumps(form).encode()))
                assert abs(answer['delay_ms']-.030)<1e-9, answer
                updated=json.loads(read('/api/latency/results'))
                assert any(row['name']==form['name'] and row['delay_ms']==answer['delay_ms'] for row in updated['scope'])
                print(f'Isolated GET /latency-monitor, wav + CSV POST passed on port {port}. Synthetic fixture: {answer["delay_ms"]} ms.')
            finally:
                server.terminate()
                try:
                    server.wait(5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEST)
    args=parser.parse_args()
    dest=args.output.resolve()
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.latency-kit-') as staging:
        archive=Path(staging)/dest.name
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            hashes=[]
            for name in members():
                content=(ROOT/name).read_bytes()
                hashes.append(f'{hashlib.sha256(content).hexdigest()}  {name}')
                z.writestr(name,content)
            z.writestr('SHA256SUMS.txt','\n'.join(hashes)+'\n')
        isolated_check(archive)
        archive.replace(dest)
    print(f'{dest} ({dest.stat().st_size:,} bytes), SHA256 {hashlib.sha256(dest.read_bytes()).hexdigest()}')


if __name__=='__main__':
    main()
