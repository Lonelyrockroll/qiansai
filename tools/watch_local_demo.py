"""Observe the FPGA while the operator uses the local keys and knobs."""
import argparse
import json
import sys
import time
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board


def watch_single_key(folder, seconds):
    """Measure exactly one real H15 press; UART is used only to arm and read back."""
    b=Board()
    armed=False
    try:
        key=b.call(9)
        assert key['mode']==2 and key['calibrated'] and not key['fault'] and key['pressed_mask']==0,key
        assert not b.call(34)['monitor'] and not b.call(4)['active']
        jtag=(folder/'after_jtag.log').read_text(encoding='utf8')
        code=re.search(r'User Code is:\s*(0x[0-9a-f]+)',jtag,re.I)[1]
        b.call(6)
        armed=True
        for _ in range(160):
            if b.call(4)['amp_ready']:break
            time.sleep(.01)
        assert b.call(4)['amp_ready']
        b.call(10,bytes([5,12]))
        baseline=b.call(34)
        assert baseline['monitor'] and baseline['demo']==0
        print('READY: physical H15 / C4, press and release once',flush=True)
        deadline=time.monotonic()+seconds
        stable_since=None
        saw_h15=False
        other_keys=0
        while time.monotonic()<deadline:
            key=b.call(9)
            saw_h15|=bool(key['pressed_mask'] & (1<<14))
            other_keys|=key['pressed_mask'] & ~(1<<14)
            after=b.call(34)
            ons=(after['physical_ons']-baseline['physical_ons']) & 0xffffff
            offs=(after['physical_offs']-baseline['physical_offs']) & 0xffffff
            measured=(after['measurements']-baseline['measurements']) & 0xffff
            if offs and key['pressed_mask']==0 and not b.call(17)['live_held']:
                if stable_since is None:stable_since=time.monotonic()
                if time.monotonic()-stable_since>=.4:break
            else:stable_since=None
            time.sleep(.025)
        else:raise TimeoutError(f'No settled key release within {seconds} seconds')
        repairs=(after['release_repairs']-baseline['release_repairs']) & 0xffff
        passed=(saw_h15 and not other_keys and ons==offs==measured==1 and repairs==0 and
                after['monitor'] and after['demo']==0 and after['onset_valid'] and after['measured_key']==14)
        result=dict(result='passed' if passed else 'unexpected physical events',code=code,key='H15 / C4',
                    unit='microseconds',endpoints='accepted physical Note On to completed first nonzero standard I2S left word',
                    value=after['onset_us'],physical_ons_delta=ons,physical_offs_delta=offs,measurement_delta=measured,
                    repairs_delta=repairs,observed_h15=saw_h15,other_key_mask=other_keys,
                    baseline=baseline,after=after,full_chain_measurement=False)
        (folder/'onset_board.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result),flush=True)
        if not passed:raise RuntimeError('H15 did not produce one isolated measured ON/OFF pair')
    finally:
        try:
            if armed:
                b.call(3)
                b.call(10,b'\x03')
                b.call(10,bytes([6,12]))
        finally:b.device.close()

def watch(folder,seconds):
    b=Board()
    folder.mkdir(parents=True,exist_ok=True)
    changes=[]
    previous=None
    seen=set()
    initial_measurements=b.call(34)['measurements']
    start=time.monotonic()
    try:
        while time.monotonic()-start<seconds:
            m=b.call(34); key=b.call(9); u=b.call(12)
            state=(m['monitor'],m['demo'],m['peak_count'],m['missing'],m['onset_valid'],m['onset_us'],m['measurements'],m['release_repairs'],m['physical_ons'],m['physical_offs'],key['pressed_mask'],u['event_count'])
            if state!=previous:
                router=b.call(17)
                changes.append(dict(seconds=round(time.monotonic()-start,3),monitor=m,pressed=key['pressed_mask'],
                                    native_events=u['event_count'],native_event=u['last_event'],live_held=router['live_held'],notes_applied=router['notes_applied']))
                previous=state
                (folder/'local_controls.json').write_text(json.dumps(changes,indent=2)+'\n')
            if m['monitor'] and m['demo']==0 and m['onset_valid'] and m['measured_key']==14 and m['measurements']!=initial_measurements:seen.add('onset')
            if m['demo']==1 and m['peak_count']==32:seen.add('32')
            if m['demo']==2 and m['peak_count']==31:seen.add('31')
            if seen=={'onset','32','31'} and not m['monitor']:break
            time.sleep(.08)
    finally:b.device.close()
    print('Observed',sorted(seen))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('folder',type=Path);ap.add_argument('--seconds',type=int,default=180)
    ap.add_argument('--single-key',action='store_true',help='Arm LIVE and verify one physical H15 gate pair')
    args=ap.parse_args();(watch_single_key if args.single_key else watch)(args.folder,args.seconds)
