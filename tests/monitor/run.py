"""Validate actual FPGA monitor bins, waveform and delayed portrait using known PCM."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FS = 50_000_000 / 1024
CASES = [[], [(16, 2100)], [(5, 3500), (23, 2100)],
         [(k, 105) for k in range(1, 64, 2)],
         [(k, 105) for k in range(1, 64, 2) if k != 19], []]


def samples(tones):
    return [round(sum(amp*math.sin(2*math.pi*k*n/1024) for k, amp in tones)) for n in range(1024)]


def geometry(raw):
    peak = max(abs(x) for x in raw)
    gain = next((k for k in range(6) if peak >= (16384 >> k)), 6)
    normal = [max(-128, min(127, (p << gain) >> 8)) for p in raw]
    wave = [(normal[n]+128)//4 for n in range(512, 1024, 8)]
    portrait = set()
    for n, a in enumerate(normal):
        x = (a+128)//16
        y = 15-(normal[(n-16)%1024]+128)//16
        portrait.add(y*16+x)
    return wave, portrait


def check_banks(compiler, runtime, work, monitor_source, results):
    bench = work/'tb_banks.v'
    bench.write_bytes((HERE/bench.name).read_bytes())
    output = work/'banks.vvp'
    subprocess.run([compiler, '-g2012', '-s', 'tb_banks', '-o', output, monitor_source, bench], check=True)
    result = subprocess.run([runtime, output], cwd=work, capture_output=True, text=True, check=True, timeout=120)
    if 'PASS bank exchange' not in result.stdout:
        raise RuntimeError(result.stdout + result.stderr)
    (results/'bank-regression.log').write_text(result.stdout, encoding='utf8')
    document = {
        'result': 'passed',
        'scope': 'Bank ownership in 50/49 MHz domains, including stalled vertical blank, disabled capture and a pixel-only reset during write.',
        'source_sha256': {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (monitor_source,bench)
        },
        'summary': result.stdout.splitlines()[0],
    }
    (results/'bank-validation.json').write_text(json.dumps(document,indent=2)+'\n')
    print(document['summary'])


def check_status(compiler, runtime, work, monitor_source, results, render=False):
    bench = work/'tb_status.v'
    bench.write_bytes((HERE/bench.name).read_bytes())
    executable = work/'status.vvp'
    subprocess.run([compiler, '-g2012', '-s', 'tb_status', '-o', executable, monitor_source, bench], check=True)
    result = subprocess.run([runtime, executable], cwd=work, capture_output=True, text=True, check=True, timeout=120)
    if 'PASS LIVE LAST I2S' not in result.stdout:
        raise RuntimeError(result.stdout + result.stderr)
    report = {
        'result':'passed',
        'scope':'Actual renderer characters in all four header states and final RGB target/missing marker pixels.',
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (monitor_source,bench)},
        'summary':result.stdout.splitlines()[0],
    }
    if render:
        from PIL import Image
        image = Image.open(work/'loop-header.ppm').convert('RGB')
        assert image.size == (1024,66)
        preview = results/'loop-header.png'
        if preview.is_file():
            with Image.open(preview) as reference:
                assert image.tobytes() == reference.convert('RGB').tobytes()
        else:
            image.save(preview)
        report['header_rgb_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
    (results/'status-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(report['summary'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--render', action='store_true')
    ap.add_argument('--banks-only', action='store_true', help='Exercise only the dual-clock ownership boundary')
    ap.add_argument('--status-only', action='store_true', help='Exercise only LIVE/Loop/test labels and marker pixels')
    ap.add_argument('--native', action='store_true', help='Use all 1024 system clocks between audio samples')
    args = ap.parse_args()
    results = HERE/'results'
    results.mkdir(exist_ok=True)
    compiler = shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    runtime = shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    src = [ROOT/'fpga/audio_monitor.v', HERE/'tb_monitor.v']
    (ROOT/'.work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tang-monitor-',dir=ROOT/'.work') as folder:
        work = Path(folder)
        cases = [samples(c) for c in CASES]
        with (work/'stimulus.hex').open('w', newline='\n') as f:
            for raw in cases:
                for value in raw*2:
                    f.write(f'{value & 65535:04x}\n')
        fingerprints = {}
        snapshot = []
        for source in src:
            data = source.read_bytes()
            local = work/source.name
            local.write_bytes(data)
            snapshot.append(local)
            fingerprints[source.name] = hashlib.sha256(data).hexdigest()
        if args.status_only:
            check_status(compiler,runtime,work,snapshot[0],results,args.render)
            return
        check_banks(compiler,runtime,work,snapshot[0],results)
        if args.banks_only:
            return
        check_status(compiler,runtime,work,snapshot[0],results,args.render)
        subprocess.run([compiler, '-g2012', '-s', 'tb_monitor', '-o', work/'test.vvp', *snapshot], check=True)
        cmd = [runtime, work/'test.vvp']
        if args.render:cmd.append('+RENDER')
        if args.native:cmd.append('+NATIVE')
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=480)
        if proc.returncode or 'PASS' not in proc.stdout:
            raise RuntimeError(proc.stdout+proc.stderr)
        frames = []
        for line in (work/'frames.txt').read_text().splitlines():
            kind, peaks, bins, wave, phase = line.split()
            kind, peaks, bins, wave, phase = int(kind), int(peaks), int(bins,16), int(wave,16), int(phase,16)
            heights = [(bins >> (5*k)) & 31 for k in range(64)]
            expected_wave, expected_phase = geometry(cases[kind])
            assert [(wave >> (6*k)) & 63 for k in range(64)] == expected_wave, (kind,'wave')
            observed_phase = {k for k in range(256) if (phase >> k)&1}
            assert observed_phase == expected_phase, (kind,'portrait',observed_phase ^ expected_phase)
            if kind in (0,5):
                assert max(heights)==0 and peaks==0
            elif kind in (1,2):
                selected = {k for k,amp in CASES[kind]}
                ordered = sorted(range(1,65),key=lambda k:heights[k-1],reverse=True)
                assert set(ordered[:len(selected)])==selected, (kind,heights)
                assert peaks==len(selected), (kind,peaks,heights)
            else:
                strong = {k+1 for k in range(64) if heights[k]>=9 and
                          heights[k]>(heights[k-1] if k else 0) and
                          heights[k]>(heights[k+1] if k<63 else 0)}
                assert strong == {k for k,amp in CASES[kind]}, (kind,strong,heights)
                assert peaks==len(strong), (kind,peaks,strong,heights)
            frames.append(dict(case=kind,tones=[k for k,_ in CASES[kind]],peaks=peaks,
                               levels=heights,occupied_phase_cells=len(observed_phase)))
        if args.render:
            from PIL import Image
            for name in ('tone','test32','test31'):
                im=Image.open(work/(name+'.ppm'));assert im.size==(1024,600)
                golden = results/(name+'.png')
                if golden.is_file():
                    with Image.open(golden) as reference:
                        assert im.convert('RGB').tobytes()==reference.convert('RGB').tobytes(), name
                else:
                    im.save(golden)
        result=dict(result='passed',scope='RTL simulation from real PCM input port; 2 analysis windows per case, bit-exact independent wave and delay-portrait references.',
                    source_sha256=fingerprints,
                    sample_rate_hz=FS,spacing_hz=FS/1024,sample_period_sys_clocks=1024 if args.native else 160,
                    rendered=args.render, frames=frames)
        (results/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
        print(proc.stdout.strip());print([f['peaks'] for f in frames])


if __name__=='__main__':
    main()
