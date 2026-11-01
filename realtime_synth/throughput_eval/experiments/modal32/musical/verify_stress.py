"""Run the v26 PCM path at all 32 white keys, using the musical firmware's ROM."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import verify_modal32 as bench

COEFFICIENTS = HERE / 'modal32_coeffs.v'
EXPECTED_SHA256 = '858c5fbab101d0b91d8d386aeefeaa190b7e9560cc210994a527f94968376026'
EVIDENCE = HERE / 'stress_evidence'
CASES = {'full': 512, 'hot': 128}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup():
    bench.check(sha(COEFFICIENTS) == EXPECTED_SHA256, 'Musical coefficient ROM changed')
    table = {int(addr): int(word, 16) for _, addr, word in bench.TABLE.findall(COEFFICIENTS.read_text())}
    bench.check(set(table) == set(range(192)), 'Expected six complete bands')
    notes = {int(key): int(value) for key, value in re.findall(
        r"7'd(\d+):\s*step=32'd(\d+);", (bench.RTL / 'note_rom.v').read_text())}
    steps = [notes[n] for n in range(36, 90) if n % 12 in (0, 2, 4, 5, 7, 9, 11)]
    bench.check(len(steps) == 32, 'Expected 32 white pitches from C2 to F6')
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / 'white_steps.hex').write_text(''.join(f'{step:08x}\n' for step in steps))
    return steps, table


def analyze(case, masks):
    raw = EVIDENCE / (case + '.pcm')
    pcm = np.fromfile(raw, dtype='<i2').astype(float)
    frames = [l.split() for l in (EVIDENCE / (case + '.frames')).read_text().splitlines()]
    bench.check(len(pcm) == len(frames) == CASES[case], 'Unexpected capture length')
    common = [0xffffffff] * len(masks)
    counts, timings = [], []
    for frame in frames:
        bench.check(int(frame[0]) == 32 and int(frame[2], 16) == 0xffffffff, 'Missing voice')
        observed = [int(s, 16) for s in frame[3:]]
        bench.check(len(observed) == 32 and all((m & ~limit) == 0 for m, limit in zip(observed, masks)),
                    'Out-of-band component')
        counts.append(sum(m.bit_count() for m in observed))
        common = [a & b for a, b in zip(common, observed)]
        timings.append(int(frame[1]))
    stats = (EVIDENCE / (case + '.stats')).read_text().splitlines()
    terms = [int(x, 16) for x in next(l for l in stats if l.startswith('nonzero_products ')).split()[1:]]
    bench.check(common == masks, 'An in-band oscillator dropped out during the observation window')
    bench.check(terms == masks, 'Observed nonzero contributions differ from the expected in-band set')
    timing = next(l for l in stats if l.startswith('max_cycles ')).split()
    maximum, all_frames, limited = map(int, timing[1::2])
    bench.check((limited > 0) == (case == 'hot'), 'Unexpected limiter activity')
    bench.check(0 < min(timings) <= max(timings) <= maximum < 1024, 'Overran frame deadline')
    bench.check(0 < max(np.abs(pcm)) <= 28000, 'Final PCM silent or past limiter ceiling')
    return dict(captured_frames=len(frames), pcm_sha256=sha(raw), pcm_peak=int(max(np.abs(pcm))),
                pcm_rms=float(np.sqrt(np.mean(pcm ** 2))), limiter_frames_entire_run=limited,
                frames_entire_run=all_frames, captured_latency_minmax_clocks=[min(timings), max(timings)],
                max_latency_entire_run_clocks=maximum, engine_limiter_fx_deadline_faults=0,
                engine_output_fx_hardclip_flags=0, active_voices_every_frame=32,
                active_states_each_frame_minmax=[min(counts), max(counts)],
                active_in_all_frames_per_voice=[m.bit_count() for m in common],
                contributed_nonzero_at_least_once_per_voice=[m.bit_count() for m in terms])


def main():
    bench.OUT = EVIDENCE
    steps, table = setup()
    masks = [bench.active_mask(s, table) for s in steps]
    sources = [*bench.SOURCES, COEFFICIENTS, bench.RTL / 'note_rom.v']
    receipts = {str(f): sha(f) for f in sources}
    subprocess.run(['E:/iverilog/bin/iverilog.exe', '-g2012', '-s', 'tb_modal32', '-o',
                    EVIDENCE / 'musical.vvp', *bench.SOURCES, COEFFICIENTS], cwd=EVIDENCE, check=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda c: bench.sim(c, 'musical', CASES[c]), CASES))
    results = {case: analyze(case, masks) for case in CASES}
    bench.check(all(sha(f) == receipts[str(f)] for f in sources), 'A simulation input changed')
    report = dict(scope='Digital RTL simulation, baseline modal32.v and musical ROM, v26 melody core, '
                        '4x melodic bus, limiter, bypass FX, final signed16 little-endian PCM consumed by '
                        'audio_tx. 32 simultaneous keys, real note_rom C2 to F6. No board or acoustic measurement.',
                  clock_hz=50_000_000, sample_rate_hz=bench.FS, clocks_per_sample=1024,
                  cases=dict(full='25% level 16384, gain mode 1', hot='level 65535, gain mode 2'),
                  source_sha256=receipts, expected_in_band_per_voice=[m.bit_count() for m in masks],
                  expected_in_band_states=sum(m.bit_count() for m in masks), observations=results,
                  limit='Product masks count independent terms observed nonzero at least once in the capture. '
                        'This does not show each can be heard in the simultaneous 32-key chord.')
    (HERE / 'stress_validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
