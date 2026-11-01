"""Load a validated musical patch into Tang SRAM and retain the pre-load playing settings."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from verify32 import Board, require, save_json, status, wait_for

PROGRAMMER = Path('E:/Gowin_edu/Gowin_V1.9.11.03_Education_x64/Programmer/bin/programmer_cli.exe')


def check_inactive(s,discard_loop_frames=None):
    require(all(item['firmware'] == 26 for item in s.values()), 'Unrecognized control protocol')
    require(s['16']['key_mode'] in (0,2), 'Cannot restore a single-key calibration')
    loop=s['14']
    require(not (loop['playing'] or loop['recording'] or loop['pending_record']), 'Loop is running')
    if s['16']['length_set'] or loop['present'] or loop['layers'] or any(loop['layer_counts']):
        require(discard_loop_frames == s['16']['actual_frames'] and loop['layer_counts']==[1,0,0,0]
                and loop['layers']==1, 'A different or unapproved Loop is present')
    require(not any(s['22'][f] for f in ('recording','armed','ready')), 'A PCM capture is in use')
    require(not (s['4']['gated'] or s['4']['active'] or s['9']['pressed_mask'] or s['17']['held']
                 or s['13']['active_voices'] or s['25']['pending'] or s['25']['tail']), 'A note or effect is in use')


def program(args,log):
    proc = subprocess.run([str(PROGRAMMER),*args],stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,check=False)
    data = proc.stdout.decode(errors='replace')
    log.write_text(data,encoding='utf8')
    require(proc.returncode == 0, f'Programmer failed. See {log}')
    return data


def load(option,folder,discard_loop_frames=None):
    routed = HERE.parents[4]/'tmp/modal32_fit_20261101/musical'/f'font_place{option}'
    image = routed/'impl/pnr/synth_display.fs'
    record = json.loads((HERE/f'font_place{option}_report.json').read_text())
    require(record['validated'] and hashlib.sha256(image.read_bytes()).hexdigest() == record['sha256'],
            'Build and validated image differ')
    folder.mkdir(exist_ok=False)
    cables = program(['--scan-cables','F'],folder/'cables.log')
    matches = re.findall(r'USB Debugger A/0/(\d+)/',cables)
    require(len(matches)==1 and int(matches[0])>0,'Expected one ready first JTAG channel')
    cable_args = ['--device','GW5AT-60B','--cable-index','4','--location',matches[0]]
    previous = program([*cable_args,'--run','0'],folder/'old_jtag.log')
    require(re.search(r'ID Code is:\s*0x0001481B\b',previous,re.I), 'Unexpected FPGA ID')
    board = Board()
    try:
        s=status(board)
        check_inactive(s,discard_loop_frames)
        time.sleep(.2)
        s=status(board)
        check_inactive(s,discard_loop_frames)
        save_json(folder/'before_program.json',s)
        board.call(3)
        wait_for(lambda: board.call(4),lambda a:a['amp_muted'] and not a['amp_ready'] and not a['amp_hold'],
                 'Amplifier did not enter mute')
    finally:
        board.device.close()
    output = program([*cable_args,'--run','2','--fsFile',str(image)],folder/'sram_program.log')
    require('SRAM Program' in output and 'Finished.' in output,'SRAM transfer did not finish')
    result = program([*cable_args,'--run','0'],folder/'candidate_jtag.log')
    code = re.search(r'User Code is:\s*(0x[0-9a-f]+)\b',result,re.I)
    require(code and int(code[1],16) == int(record['user_code'],16),'JTAG code mismatch')
    print(f"Verified SRAM user code {record['user_code']}",flush=True)


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('option',type=int,choices=(1,2))
    cli.add_argument('folder',type=Path)
    cli.add_argument('--discard-one-event-loop', type=int, metavar='FRAMES',
                     help='only when explicitly authorized, discard one stopped single-event Loop of exactly this length')
    args=cli.parse_args()
    load(args.option,args.folder.resolve(),args.discard_one_event_loop)
