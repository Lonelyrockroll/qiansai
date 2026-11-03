"""Load the validated display bitstream into SRAM and restore silent piano settings."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board
from validate_guide_build import validate

PROGRAMMER = Path('E:/Gowin_edu/Gowin_V1.9.11.03_Education_x64/Programmer/bin/programmer_cli.exe')


def load(build, folder, replace_example=False, after_repower=False, profile='full'):
    verified = validate(build,profile)
    assert verified['firmware'] in (30,31,32,33)
    image = build/'impl/pnr/synth_display.fs'
    folder.mkdir(parents=True, exist_ok=True)
    def programmer(args, name):
        p = subprocess.run([str(PROGRAMMER), *args], capture_output=True, timeout=90)
        raw = p.stdout.decode(errors='replace')+p.stderr.decode(errors='replace')
        # Turn terminal progress carriage returns into readable transcript lines.
        output = '\n'.join(line.rstrip() for line in raw.splitlines() if line.strip())+'\n'
        (folder/name).write_text(output, encoding='utf8')
        assert p.returncode == 0, output
        return output
    cables = programmer(['--scan-cables','F'], 'cables.log')
    match = re.findall(r'USB Debugger A/0/(\d+)/', cables)
    assert len(match) == 1, cables
    options = ['--device','GW5AT-60B','--cable-index','4','--location',match[0]]
    old = programmer([*options, '--run','0'], 'before_jtag.log')
    assert re.search(r'ID Code is:\s*0x0001481B\b', old, re.I), old
    before = None
    if after_repower:
        # Only for a known repowered target, explicitly requested by its operator.
        usercode=re.search(r'User Code is:\s*(0x[0-9a-f]+)',old,re.I)
        assert usercode and int(usercode[1],16)==0, 'Target contains another bitstream; use normal state checks'
    else:
        board = Board()
        try:
            before = board.state()
            loop = board.call(14)
            assert before['4']['firmware'] in (29,30,31,32,33), before['4']
            assert not before['4']['active'] and not before['4']['gated'] and not before['9']['pressed_mask']
            assert not before['16']['length_set'] and not any(loop[k] for k in ('playing','recording','pending_record','present','layers'))
            assert not any(before['22'][k] for k in ('recording','armed','ready'))
            assert before['9']['mode'] in (0,2,3)
            if before['4']['firmware'] >= 30:
                guide = board.call(31)
                known_example=(replace_example and guide['guide_count']==84 and guide['guide_duration_cs']==2400 and guide['guide_time_cs']==0)
                assert not guide['guide_loading'] and not guide['guide_playing'] and (guide['guide_demo'] or known_example), 'Preserve live or unrecognized MIDI'
                before['guide']=guide
            if before['4']['firmware'] >= 31:
                pdf=board.call(32)
                assert not pdf['score_reserved'] and not pdf['score_loading'], 'Preserve the uploaded PDF page'
            (folder/'before_download.json').write_text(json.dumps(before,indent=2)+'\n')
            board.call(3)
            time.sleep(.1)
            assert board.call(4)['amp_muted']
        finally:
            board.device.close()
    assert hashlib.sha256(image.read_bytes()).hexdigest() == verified['sha256']
    output = programmer([*options,'--run','2','--fsFile',str(image)], 'sram_program.log')
    assert 'SRAM Program' in output and 'Finished.' in output, output
    output = programmer([*options,'--run','0'], 'after_jtag.log')
    assert int(re.search(r'User Code is:\s*(0x[0-9a-f]+)',output,re.I)[1],16) == int(verified['user_code'],16)
    time.sleep(1)
    board = Board()
    try:
        assert board.call(4)['firmware'] == verified['firmware']
        if before:
            board.restore(before)
            if before['9']['mode'] in (1,2):
                board.call(8)
                time.sleep(.8)
            board.call(10,bytes([6,before['11']['focus']]))
        else:
            board.call(3)
            if board.call(11)['drum_mode']:board.call(10,bytes([14]))
            if verified['firmware']==32:board.call(10,bytes([6,12]))
        after = board.state()
        assert after['4']['amp_muted'] and after['11']['locked']
        assert not after['9']['fault'] and not after['9']['pressed_mask']
        (folder/'after_download.json').write_text(json.dumps(after,indent=2)+'\n')
    finally:
        board.device.close()
    print('SRAM verified', verified['user_code'], 'firmware',verified['firmware'],'local settings restored, muted')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--replace-example-midi',action='store_true',help='replace the previously identified 84-event, 24-second Android example')
    parser.add_argument('--after-repower',action='store_true',help='operator-confirmed repower, JTAG must return User Code zero')
    parser.add_argument('--profile',choices=('full','spectrum-only'),default='full')
    args=parser.parse_args()
    load(args.build.resolve(),args.folder.resolve(),args.replace_example_midi,args.after_repower,args.profile)
