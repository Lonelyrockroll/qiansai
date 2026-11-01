"""Exercise the Bluetooth link pins with real UART timing and mixed guide/audio traffic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
FPGA = PROJECT/'fpga'
RESULTS = HERE/'results'
SOURCES = ['bt_console.v', 'bt_link.v', 'bt_uart_rx.v', 'bt_uart_tx.v',
           'guide_transport.v', 'guide_player.v', 'score_store.v', 'record_stream.v', 'record_filter.v', 'ima_encoder.v']


def execute(args, work, timeout=300):
    process = subprocess.run([str(value) for value in args], cwd=work, text=True,
                             capture_output=True, timeout=timeout, check=True)
    return process.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', action='store_true', help='also wait through the real 250 ms incomplete-frame discard timeout')
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    tag = 'console-timeout' if args.timeout else 'console'
    trace = RESULTS/(tag+'-wire.hex')
    files = [FPGA/name for name in SOURCES]
    iv = shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    vvp = shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    with tempfile.TemporaryDirectory(prefix='tang-guide-console-') as folder:
        work = Path(folder)
        shutil.copyfile(PROJECT/'realtime_synth/android_recorder/tests/fixtures/demo-upload.hex', work/'demo-upload.hex')
        binary = work/'console.vvp'
        execute([iv, '-g2012', '-s', 'tb_console', '-o', binary, HERE/'tb_console.v', *files], work)
        command = [vvp, binary, '+OUT='+trace.as_posix()]
        if args.timeout:
            command.append('+TIMEOUT')
        log = execute(command, work)
    if 'PASS physical 8N1' not in log:
        raise RuntimeError(log)
    counts = re.search(r'divisor\s+(\d+):\s+(\d+) TGAK,\s+(\d+) TREC data,\s+(\d+) recording end;\s+(\d+) clocks', log)
    if not counts:
        raise ValueError(log)
    report = dict(scope='RTL pin-level 8N1 receiver independently decodes bt_console TX, with auto-baud, binary guide and ADPCM recorder arbitration.',
                  result='passed', baud_divisor=int(counts[1]), guide_frames=int(counts[2]),
                  audio_frames=int(counts[3]), finish_frames=int(counts[4]), clocks=int(counts[5]),
                  tested_discard_timeout=args.timeout, wire_bytes=len(trace.read_text().split()),
                  source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (RESULTS/(tag+'.log')).write_text(log, encoding='utf8')
    (RESULTS/(tag+'-validation.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
