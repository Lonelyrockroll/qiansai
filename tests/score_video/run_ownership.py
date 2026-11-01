"""Check production system/pixel CDC ownership; no full-frame rerender required."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from run import FPGA, HERE, tool


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iverilog'); p.add_argument('--vvp')
    p.add_argument('--output-dir', type=Path, default=HERE / '.work/ownership')
    args = p.parse_args()
    iv, vv = tool(args.iverilog, 'iverilog'), tool(args.vvp, 'vvp')
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    sources = ['synth_display_top.v', 'bt_console.v', 'guide_transport.v', 'score_store.v',
               'score_renderer.v', 'pcm_capture.v', 'score_capture_ram.v']
    hashes = lambda: {name: hashlib.sha256((FPGA / name).read_bytes()).hexdigest() for name in sources}
    before = hashes()
    compiled = output / 'ownership.vvp'
    subprocess.run([iv, '-g2012', '-i', '-s', 'score_ownership_tb', '-o', str(compiled),
                    str(HERE / 'ownership_tb.v')] + [str(FPGA / s) for s in sources], cwd=FPGA, check=True)
    records = []
    for phase in range(0, 20000, 1000):
        for case in range(3):
            result = subprocess.run([vv, str(compiled), f'+PHASE_PS={phase}', f'+CASE={case}'],
                                    text=True, capture_output=True, cwd=FPGA, timeout=15)
            print(result.stdout.strip(), flush=True)
            if result.stderr: print(result.stderr.strip(), flush=True)
            result.check_returncode()
            line = next(x for x in result.stdout.splitlines() if x.startswith('PASS CDC '))
            records.append({key: int(value) for key, value in re.findall(r'(\w+)=(-?\d+)', line)})
    stale = [r for r in records if r['stale']]
    assert stale and all(r['held_by_return'] > 0 and r['ack_age'] > 32 for r in stale)
    assert all(r['actual_ram_writes'] == 1 for r in records)
    assert all(r['ack_age'] == 33 for r in records if r['case'] == 2)
    # Mutation control: intentionally suppress the guard at simulation runtime.
    # The protection assertion must fail under a phase already known to produce
    # the stale visible transition. No production files are modified.
    first = stale[0]
    negative = subprocess.run([vv, str(compiled), f'+PHASE_PS={first["phase"]}', f'+CASE={first["case"]}', '+NO_GUARD'],
                              text=True, capture_output=True, cwd=FPGA, timeout=15)
    assert negative.returncode != 0 and 'UNSAFE' in negative.stdout, negative.stdout
    assert hashes() == before, 'Production source changed during CDC sweep'
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'production_sha256': before,
        'system_period_ps': 20000, 'pixel_period_ps': 20408,
        'phase_offsets_ps': list(range(0, 20000, 1000)),
        'scenarios': {'0': 'one-cycle SHOW then BEGIN with stale frame latch',
                      '1': 'one-cycle SHOW then HIDE then BEGIN with stale frame latch',
                      '2': 'one-cycle SHOW then BEGIN without frame latch; guard alone'},
        'passed': len(records), 'stale_visible_cases': len(stale),
        'actual_ram_writes': sum(r['actual_ram_writes'] for r in records),
        'negative_control': {'guard_forced_off_only_in_tb': True, 'expected_failure': negative.stdout.strip()},
        'runs': records,
    }
    (output / 'ownership.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(f'PASS {len(records)} phase/case combinations, {len(stale)} stale visible cases, guard-off mutation caught')


if __name__ == '__main__':
    main()
