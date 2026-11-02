"""Run menu actions through the real guide player and performance looper."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from run import BASE, HERE, ROOT, fixture


def main():
    names = ('uart_control_display.v', 'uart_rx.v', 'uart_tx.v',
             'guide_player.v', 'performance_looper.v')
    sources = {name: (ROOT / 'fpga' / name).read_bytes() for name in names}
    prefix = (BASE / 'tb_score_controller.v').read_text().split(' task enter_live;')[0]
    prefix = prefix.replace(',loop_playing=0,loop_recording=0,loop_pending=0', '')
    prefix = prefix.replace('reg [2:0] loop_layers=0;', 'wire [2:0] loop_layers;')
    prefix = prefix.replace('reg [35:0] loop_counts=0;', 'wire [35:0] loop_counts;')
    fixture.CONTROLLED.update('guide_valid guide_playing guide_loading guide_demo guide_time_cs '
                              'guide_duration_cs guide_count guide_index guide_speed guide_current '
                              'loop_duration loop_notice'.split())
    helpers = (HERE / 'scenarios.vh').read_text().split(' integer page, row,')[0]
    body = (HERE / 'integration.vh').read_text()
    iv = shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    vvp = shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    with tempfile.TemporaryDirectory(prefix='navigation-integration-') as folder:
        work = Path(folder)
        for name, data in sources.items():
            (work / name).write_bytes(data)
        (work / 'controller_instance.vh').write_text(
            fixture.instance(sources['uart_control_display.v'].decode()), encoding='ascii')
        (work / 'tb.v').write_text(prefix + helpers + body, encoding='ascii')
        compiled = subprocess.run([iv, '-g2012', '-I', str(work), '-s', 'tb_score_controller',
                                   '-o', str(work / 'test.vvp'), str(work / 'tb.v'),
                                   *[str(work / name) for name in sources]], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout + compiled.stderr)
        result = subprocess.run([vvp, str(work / 'test.vvp')], capture_output=True, text=True, timeout=60)
    results = HERE / 'results'
    results.mkdir(exist_ok=True)
    (results / 'integration.log').write_text(result.stdout + result.stderr, encoding='utf8')
    (results / 'integration.json').write_text(json.dumps({
        'passed': result.returncode == 0,
        'scope': 'UART navigation controller connected to production guide_player and performance_looper RTL',
        'stdout': result.stdout,
        'source_sha256': {n: hashlib.sha256(b).hexdigest() for n, b in sources.items()},
    }, indent=2) + '\n', encoding='utf8')
    print(result.stdout)
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
