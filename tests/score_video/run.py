"""Verify actual score RTL raster, frame-latched visibility, and panel alignment."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FPGA = ROOT / 'fpga'


def tool(value, name):
    candidate = value or os.environ.get(name.upper()) or name
    result = shutil.which(candidate)
    if result:
        return result
    if Path(candidate).is_file():
        return str(Path(candidate).resolve())
    raise SystemExit(f'{name} unavailable; set PATH or --{name}.')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog')
    parser.add_argument('--vvp')
    parser.add_argument('--output-dir', type=Path, default=HERE / '.work')
    args = parser.parse_args()
    iv, vv = tool(args.iverilog, 'iverilog'), tool(args.vvp, 'vvp')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_names = ['score_renderer.v', 'score_capture_ram.v', 'video_timing.v', 'panel_renderer.v']
    before = {name: sha(FPGA / name) for name in source_names}

    def compile_tb(name, sources):
        compiled = output / f'{name}.vvp'
        subprocess.run([iv, '-g2012', '-s', f'score_{name}_tb', '-o', str(compiled),
                        str(HERE / f'{name}_tb.v')] + [str(FPGA / s) for s in sources], check=True, cwd=FPGA)
        return compiled

    raster = compile_tb('raster', source_names[:3])
    alignment = compile_tb('alignment', [source_names[0], source_names[1], source_names[3]])

    def execute(compiled, arguments, label):
        result = subprocess.run([vv, str(compiled)] + arguments, cwd=FPGA, text=True, capture_output=True, timeout=180)
        (output / f'{label}.log').write_text(result.stdout + result.stderr, encoding='utf8')
        print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
        result.check_returncode()
        return result.stdout

    pattern_log = execute(raster, ['+MODE=0', '+FRAMES=5'], 'pattern')
    page_dir = ROOT / 'output/pdf/score-demo'
    ppm = output / 'score-page-01-rtl.ppm'
    page_log = execute(raster, ['+MODE=1', '+FRAMES=2', f'+RAW={(page_dir / "page-01.bin").as_posix()}', f'+IMAGE={ppm.as_posix()}'], 'page')
    alignment_log = execute(alignment, [], 'alignment')
    png = ppm.with_suffix('.png')
    with Image.open(ppm) as image:
        image.save(png)
        actual = image.convert('RGB')
    with Image.open(page_dir / 'page-01-restored-600.png') as image:
        expected = image.convert('RGB')
    assert actual.size == expected.size == (1024, 600)
    a, b = actual.tobytes(), expected.tobytes()
    different = sum(a[i:i+3] != b[i:i+3] for i in range(0, len(a), 3))
    assert different == 0, f'Actual RTL page differs at {different} pixels'
    after = {name: sha(FPGA / name) for name in source_names}
    assert before == after, 'Production source changed during verification; rerun a stable revision'
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'production_sha256': after,
        'checks': {
            'independent_row_formula': 'floor(y*512/600)',
            'pattern_frames': 5, 'pattern_pixels': 5 * 614400,
            'demo_frames': 2, 'demo_pixels': 2 * 614400,
            'first_frame_reset': True, 'continuous_frames': True,
            'all_line_first_last_pixels': True, 'all_last_row_pixels': True,
            'async_visibility_expected_frames': [0, 1, 0, 0, 1],
            'late_request_deferred_one_more_frame': True,
            'real_ram_both_ports_synchronous': True,
            'real_panel_rgb_hs_vs_de_score_select_mux_3_stages': True,
        },
        'actual_rtl_png': png.name,
        'pixels_different_from_pdf_restored_preview': different,
        'rgb_sha256': hashlib.sha256(a).hexdigest(),
        'raw_sha256': sha(page_dir / 'page-01.bin'),
        'pass_lines': [line for log in (pattern_log, page_log, alignment_log) for line in log.splitlines() if line.startswith('PASS ')],
    }
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    ppm.unlink()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
