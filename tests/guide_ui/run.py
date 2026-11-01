"""Run renderer BCD/menu regression and/or reproduce both full-frame RTL previews."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image
from verify import verify_font, verify_frames

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FPGA = ROOT / 'fpga'


def executable(value, name):
    candidate = value or os.environ.get(name.upper()) or name
    found = shutil.which(candidate)
    if found:
        return found
    path = Path(candidate).expanduser()
    if path.is_file():
        return str(path.resolve())
    raise SystemExit(f'{name} not found. Add Icarus Verilog to PATH or pass --{name} /path/to/{name}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group()
    select.add_argument('--check-only', action='store_true', help='Run fast BCD, menu, colors, feedback, and font checks only')
    select.add_argument('--render-only', action='store_true', help='Render both full frames and compare golden pixels only')
    parser.add_argument('--output-dir', type=Path, default=HERE / '.work', help='Generated results, default: tests/guide_ui/.work (gitignored)')
    parser.add_argument('--iverilog', help='Icarus compiler, otherwise IVERILOG environment variable or PATH')
    parser.add_argument('--vvp', help='Icarus runtime, otherwise VVP environment variable or PATH')
    parser.add_argument('--keep-ppm', action='store_true', help='Retain intermediate PPM frames (normally removed)')
    args = parser.parse_args()
    iv = executable(args.iverilog, 'iverilog')
    vv = executable(args.vvp, 'vvp')
    output = args.output_dir.resolve()
    if output == (HERE / 'results').resolve():
        raise SystemExit('Choose a separate output directory; results/ contains the accepted golden images.')
    output.mkdir(parents=True, exist_ok=True)

    def compile_tb(name):
        compiled = output / f'{name}.vvp'
        subprocess.run([iv, '-g2012', '-s', f'guide_ui_{name}', '-o', str(compiled),
                        str(HERE / f'{name}_tb.v'), str(FPGA / 'panel_renderer.v')], check=True, cwd=FPGA)
        return compiled

    if not args.render_only:
        print(json.dumps(verify_font(), indent=2))
        subprocess.run([vv, str(compile_tb('check'))], check=True, cwd=FPGA, timeout=60)
    if not args.check_only:
        compiled = compile_tb('render')
        for drum, name in enumerate(('guide', 'drums')):
            ppm = output / f'{name}.ppm'
            subprocess.run([vv, str(compiled), f'+DRUMS={drum}', f'+OUTPUT={ppm.as_posix()}'],
                           check=True, cwd=FPGA, timeout=180)
            with Image.open(ppm) as frame:
                frame.save(output / f'{name}.png')
            if not args.keep_ppm:
                ppm.unlink()
        print(json.dumps(verify_frames(output, output / 'verification.json'), indent=2))
    print(f'PASS: guide UI outputs in {output}')


if __name__ == '__main__':
    main()
