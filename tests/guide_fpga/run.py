"""Byte-level regressions for the guide player and the Android-generated wire fixture."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
FPGA = PROJECT / 'fpga'
FIXTURE = PROJECT / 'realtime_synth/android_recorder/tests/fixtures'
RESULTS = HERE / 'results'


def execute(args, work):
    result = subprocess.run([str(a) for a in args], cwd=work, capture_output=True,
                            text=True, check=True, timeout=120)
    return result.stdout


def main():
    RESULTS.mkdir(exist_ok=True)
    compiler = shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    runtime = shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    source = [FPGA/'guide_player.v', FPGA/'guide_transport.v']
    reports = {}
    with tempfile.TemporaryDirectory(prefix='tang-guide-') as folder:
        work = Path(folder)
        for name in ('demo-upload.hex', 'demo-events.hex'):
            shutil.copyfile(FIXTURE/name, work/name)
        for bench in ('tb_guide', 'tb_java_upload'):
            binary = work/(bench+'.vvp')
            execute([compiler, '-g2012', '-s', bench, '-o', binary, *source, HERE/(bench+'.v')], work)
            args = [runtime, binary]
            if bench == 'tb_java_upload':
                args.append('+ACK='+(RESULTS/'demo-acks.hex').as_posix())
            log = execute(args, work)
            if 'PASS ' not in log:
                raise RuntimeError(log)
            (RESULTS/(bench+'.log')).write_text(log, encoding='utf8')
            reports[bench] = log.splitlines()[0]
    ack_bytes = bytes(int(x, 16) for x in (RESULTS/'demo-acks.hex').read_text().split())
    assert len(ack_bytes) == 24*24
    result = {
        'scope': 'Actual guide_transport and dual-bank guide_player RTL. No board or phone UI claim.',
        'result': 'passed',
        'tests': reports,
        'android_ack_bytes': len(ack_bytes),
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source},
        'wire_fixture_sha256': hashlib.sha256((FIXTURE/'demo-upload.hex').read_bytes()).hexdigest(),
    }
    (RESULTS/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
