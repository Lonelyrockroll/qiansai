"""Verify the expanded limits and compare gain using real final PCM."""
import argparse
import copy
import json
from pathlib import Path
import struct
import sys
import time
import zlib

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board
from fx_tools import PRESETS
from protocol import voice_payload


def wait(fn,test,seconds=3):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        value=fn()
        if test(value):return value
        time.sleep(.005)
    raise RuntimeError(value)


def check(out):
    out.mkdir(parents=True,exist_ok=True)
    board=Board();before=board.state();report={}
    assert before['27']['keyboard_limit']==26214 and before['9']['mode']==2 and not before['9']['pressed_mask']
    assert not before['4']['active'] and not before['16']['length_set']
    assert not any(before['22'][k] for k in ('armed','recording','ready'))
    (out/'before.json').write_text(json.dumps(before,indent=2))
    def level(value):return board.call(10,bytes([7])+value.to_bytes(2,'little'))
    def capture(label):
        board.call(21,struct.pack('<BBHI',1,0,2048,0))
        meta=wait(lambda:board.call(22),lambda v:v['ready'])
        raw=bytearray()
        for start in range(0,2048,6):
            packet=board.call(23,struct.pack('<HHB',meta['capture_id'],start,min(6,2048-start)))
            raw.extend(bytes.fromhex(packet['data']))
        assert zlib.crc32(raw)==meta['crc32']
        (out/(label+'.pcm')).write_bytes(raw)
        board.call(21,b'\0')
        x=np.frombuffer(raw,dtype='<i2').astype(float)
        fx=board.call(25);audio=board.call(4)
        assert not fx['clipped'] and not fx['overrun'] and not audio['overrun'] and not audio['clipped']
        report[label]={'meta':meta,'peak':float(np.max(abs(x))),'rms':float(np.sqrt(np.mean(x*x))),
                       'fx':fx,'audio':audio,'limiter':board.call(27)}
    try:
        board.call(3)
        configured=copy.deepcopy(before)
        configured['16']['keyboard_level']=26214
        configured['11']['level']=26214
        board.restore(configured)
        assert board.call(11)['level']==26214
        level(26214);assert board.call(11)['level']==26214
        try:level(26215)
        except RuntimeError:pass
        else:raise AssertionError('Keyboard limit not enforced')
        assert board.call(11)['level']==26214
        board.call(10,b'\x0e');assert board.call(11)['drum_mode']
        level(16384)
        try:level(16385)
        except RuntimeError:pass
        else:raise AssertionError('Drum limit not enforced')
        board.call(10,b'\x0e');assert not board.call(11)['drum_mode']
        board.call(10,b'\x0b');assert board.call(9)['mode']==0
        for value in (.25,.32,.40):
            board.call(3);board.fx(dict(PRESETS['off'],monitor_mute=1));board.call(6)
            wait(lambda:board.call(4),lambda v:v['amp_ready'])
            board.call(2,voice_payload(0,1,1000,timbre=0,level=value,attack_ms=1,decay_ms=1,sustain=1,release_ms=4))
            time.sleep(.06);capture('level'+str(round(value*100)))
        ratio=report['level32']['rms']/report['level25']['rms']
        assert abs(ratio-1.28)<.01,ratio
        report['ratio_32_to_25']=ratio
        board.call(3);board.fx(dict(PRESETS['reverb'],monitor_mute=1));board.call(6)
        wait(lambda:board.call(4),lambda v:v['amp_ready'])
        for i,freq in enumerate((261.6256,329.6276,391.9954,523.2511)):
            board.call(2,voice_payload(i,1,freq,timbre=before['11']['timbre'],level=.4,attack_ms=2,decay_ms=1,sustain=1,release_ms=4))
        time.sleep(.2);capture('reverb_four_note_chord_at_40')
        board.call(3);board.fx(dict(PRESETS['combined'],monitor_mute=1));board.call(6)
        wait(lambda:board.call(4),lambda v:v['amp_ready'])
        for i in range(32):
            board.call(2,voice_payload(i,1,65.4063913*2**(i/12),timbre=0,level=.4,attack_ms=2,decay_ms=1,sustain=1,release_ms=4))
        stop=time.monotonic()+3
        while time.monotonic()<stop:
            s=board.call(4);assert s['active']==32 and not s['overrun'];time.sleep(.03)
        capture('combined_32_at_40')
        board.call(5,b'\x02')
        stop=time.monotonic()+3
        while time.monotonic()<stop:
            s=board.call(4);assert s['active']==32 and not s['overrun'];time.sleep(.03)
        capture('combined_32_at_40_high_gain')
        board.call(3);time.sleep(.04);capture('muted');assert report['muted']['peak']==0
        report['passed']=True
    finally:
        board.call(3);board.call(21,b'\0');board.restore(before)
        level(20971);board.call(10,bytes([6,0]))
        after=board.state();assert after['9']['mode']==2 and after['9']['calibrated'] and after['4']['amp_muted']
        assert after['11']['level']==20971
        (out/'after.json').write_text(json.dumps(after,indent=2));board.device.close()
        (out/'results.json').write_text(json.dumps(report,indent=2))
    print('PASS limits, 32%/25% gain, 32-voice FX pressure and mute')


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('out',type=Path)
    check(cli.parse_args().out)
