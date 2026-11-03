"""Check v33 MIDI mode and heartbeat ownership while the analog output is muted."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board


def check(folder):
    board=Board()
    saved=None
    result={}
    def settle(predicate,op=4):
        end=time.monotonic()+2
        while time.monotonic()<end:
            value=board.call(op)
            if predicate(value):return value
            time.sleep(.01)
        raise AssertionError(value)
    try:
        initial=board.state()
        assert initial['4']['firmware']==33 and not initial['4']['amp_hold'] and not initial['4']['active']
        loop=board.call(14)
        assert not any(loop[k] for k in ('recording','playing','pending_record'))
        assert not board.call(34)['monitor']
        saved=initial
        board.fx(dict(saved['25'],monitor_mute=1))
        board.call(37,bytes([1,3]));board.call(6)
        settle(lambda s:s['amp_ready'] and s['amp_hold'] and s['amp_muted'])
        board.call(3,b'\x02')
        start=time.monotonic();time.sleep(3.5)
        midi_session=board.call(4)
        assert midi_session['amp_hold'] and midi_session['amp_ready'] and not midi_session['watchdog'],midi_session
        result['midi_idle']={'seconds_without_host_packet':time.monotonic()-start,'state':midi_session}
        result['midi_status']=board.call(37)
        result['midi_detail']=board.call(37,b'\0\1')
        board.call(3)
        settle(lambda s:not s['amp_hold'] and s['amp_muted'])
        board.call(37,bytes([1,0]));board.call(6)
        settle(lambda s:s['amp_ready'] and s['amp_hold'])
        start=time.monotonic();time.sleep(3.5)
        pc_session=board.call(4)
        assert not pc_session['amp_hold'] and pc_session['watchdog'],pc_session
        result['pc_idle']={'seconds_without_host_packet':time.monotonic()-start,'state':pc_session}
        result['passed']=True
    finally:
        try:
            if saved is not None:
                board.call(3)
                board.call(37,bytes([1,saved['9']['mode']]))
                board.fx(saved['25'])
                board.call(36,bytes([1,0,0]))
                result['after']=board.state()
                folder.mkdir(parents=True,exist_ok=True)
                (folder/'midi_board.json').write_text(json.dumps(result,indent=2)+'\n')
        finally:board.device.close()
    print('PASS v33 MIDI session survives browser detach and 3.5 s without a PC packet; PC mode retains watchdog; analog output remained muted')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    check(parser.parse_args().folder)
