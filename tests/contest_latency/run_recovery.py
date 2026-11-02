"""Regression for retained LAST result, source-0 reconciliation and key event ownership."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
FPGA=HERE.parents[1]/'fpga'
SOURCES=('synth_display_top','keyboard_input','white_key_map','note_rom','performance_looper',
         'performance_router','bt_console','guide_transport','key_layout','key_release_guard','onset_meter','audio_tx')


def main():
    work=HERE/'.work'/'recovery';work.mkdir(parents=True,exist_ok=True)
    results=HERE/'results';results.mkdir(exist_ok=True)
    hashes={}
    for module in SOURCES:
        filename=module+'.v';data=(FPGA/filename).read_bytes()
        (work/filename).write_bytes(data);hashes[filename]=hashlib.sha256(data).hexdigest()
    binary=work/'recovery.vvp'
    subprocess.run([shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe','-g2012','-i','-s','tb_release_recovery',
                    '-o',str(binary),str(HERE/'tb_release_recovery.v'),*[m+'.v' for m in SOURCES]],cwd=work,check=True)
    test=subprocess.run([shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe',str(binary)],cwd=work,
                        text=True,capture_output=True,timeout=240)
    log=test.stdout+test.stderr
    (results/'recovery.log').write_text(log,encoding='utf8');print(log)
    test.check_returncode()
    if 'PASS recovery:' not in log:raise RuntimeError('No passing recovery result')
    report={'result':'passed','scope':'RTL only. Hall codes, PCM, injected orphan events and engine stalls are fixture inputs.',
            'source_sha256':hashes,'testbench_sha256':hashlib.sha256((HERE/'tb_release_recovery.v').read_bytes()).hexdigest(),
            'result_line':next(line for line in log.splitlines() if line.startswith('PASS recovery:'))}
    (results/'recovery.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
