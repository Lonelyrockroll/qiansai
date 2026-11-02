"""Hierarchical navigation regression using the production UART controller."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'tests' / 'score_controller'
spec = importlib.util.spec_from_file_location('controller_fixture', BASE / 'run.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def main():
    sources = {name: (ROOT / 'fpga' / name).read_bytes()
               for name in ('uart_control_display.v', 'uart_rx.v', 'uart_tx.v')}
    # Reuse just the independent serial decoder and input fixture, not its tests.
    prefix = (BASE / 'tb_score_controller.v').read_text().split(' task enter_live;')[0]
    body = (HERE / 'scenarios.vh').read_text()
    iv = shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    vvp = shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    with tempfile.TemporaryDirectory(prefix='navigation-controller-') as folder:
        work = Path(folder)
        for name, data in sources.items():
            (work / name).write_bytes(data)
        (work / 'controller_instance.vh').write_text(
            fixture.instance(sources['uart_control_display.v'].decode()), encoding='ascii')
        (work / 'tb.v').write_text(prefix + body, encoding='ascii')
        compiled = subprocess.run([iv, '-g2012', '-I', str(work), '-s', 'tb_score_controller',
                                   '-o', str(work / 'test.vvp'), str(work / 'tb.v'),
                                   *[str(work / name) for name in sources]], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout + compiled.stderr)
        result = subprocess.run([vvp, str(work / 'test.vvp')], capture_output=True, text=True, timeout=60)
    results = HERE / 'results'
    results.mkdir(exist_ok=True)
    (results / 'controller.log').write_text(result.stdout + result.stderr, encoding='utf8')
    (results / 'validation.json').write_text(json.dumps({
        'passed': result.returncode == 0,
        'scope': 'Production RTL, injected UART receive bytes, independently decoded physical TX pin',
        'stdout': result.stdout,
        'source_sha256': {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
    }, indent=2) + '\n', encoding='utf8')
    print(result.stdout)
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
