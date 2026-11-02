"""Use normal menu and UART effect commands, then verify final PCM snapshots."""
import argparse
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
from fx_tools import FIELDS,PRESETS,configure
from protocol import FS,voice_payload


def wait(fn,condition,timeout=3):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=fn()
        if condition(value):return value
        time.sleep(.005)
    raise TimeoutError(value)


def check(out):
    out.mkdir(parents=True,exist_ok=True)
    b=Board()
    before=b.state()
    assert b.call(25)['effect_profile']==2
    assert not before['4']['active'] and not before['9']['pressed_mask']
    assert not before['16']['length_set'] and not b.call(14)['playing']
    assert not any(before['22'][v] for v in ('ready','armed','recording'))
    (out/'before.json').write_text(json.dumps(before,indent=2))
    results={}
    def preset(name):
        b.call(3)
        b.fx(dict(PRESETS[name],monitor_mute=1))
        b.call(6)
        wait(lambda:b.call(4),lambda v:v['amp_ready'])
        return b.call(25)
    def arm(n,delay=0,trigger=1):
        b.call(21,struct.pack('<BBHI',1,trigger,n,delay))
    def read(name):
        m=wait(lambda:b.call(22),lambda v:v['ready'],5)
        data=bytearray()
        for addr in range(0,m['count'],6):
            packet=b.call(23,struct.pack('<HHB',m['capture_id'],addr,min(6,m['count']-addr)))
            assert packet['offset']==addr
            data.extend(bytes.fromhex(packet['data']))
        assert zlib.crc32(data)==m['crc32']
        (out/(name+'.pcm')).write_bytes(data)
        b.call(21,b'\0')
        x=np.frombuffer(data,dtype='<i2').astype(float)
        fx=b.call(25);s=b.call(4)
        assert not fx['overrun'] and not fx['clipped'] and not s['overrun']
        results[name]={'capture':m,'fx':fx,'peak':float(np.max(abs(x))),'rms':float(np.sqrt(np.mean(x*x)))}
        return x
    try:
        b.call(3)
        if before['9']['mode']==2:b.call(10,b'\x0b')
        b.fx(dict(PRESETS['off'],monitor_mute=1))
        # Exercise the exact action behind local menu item 9.
        cycle=[]
        for name in ('reverb','delay','chorus','combined','off'):
            b.call(10,bytes([5,8]))
            fx=wait(lambda:b.call(25),lambda x:x['mask']==PRESETS[name]['mask'] and not x['pending'])
            assert all(fx[k]==PRESETS[name][k] for k in FIELDS if k!='monitor_mute'),(name,fx)
            assert fx['monitor_mute']
            cycle.append(fx)
        results['local_menu']=cycle
        class HostFacade:
            transport=True
            feedback={'firmware':32}
            fx_feedback=b.call(25)
            def exchange(self,op,payload=b''):
                return b.call(op,payload)
        host=HostFacade()
        api=[]
        for name in PRESETS:
            host.fx_feedback=b.call(25)
            configure(host,{'preset':name})
            fx=wait(lambda:b.call(25),lambda x:not x['pending'] and x['mask']==PRESETS[name]['mask'])
            assert all(fx[k]==PRESETS[name][k] for k in FIELDS if k!='monitor_mute')
            api.append(fx)
        results['host_presets']=api
        preset('delay');arm(32768)
        b.call(26,struct.pack('<H',12000));x=read('delay_impulse')
        echoes=[]
        for at in (15626,31252):
            segment=x[at-3:at+4];i=int(np.argmax(abs(segment)))+at-3;echoes.append([i,float(x[i])])
        assert abs(echoes[0][1])>1000 and 0<abs(echoes[1][1])<abs(echoes[0][1])
        results['delay_impulse']['echo_peaks']=echoes
        preset('reverb');arm(4096,round(.9*FS))
        b.call(2,voice_payload(0,1,261.6256,timbre=1,level=.2,attack_ms=1,decay_ms=1,sustain=1,release_ms=4))
        time.sleep(.3)
        b.call(2,voice_payload(0,0,261.6256,timbre=1,level=.2,attack_ms=1,decay_ms=1,sustain=1,release_ms=4))
        x=read('reverb_late')
        assert np.sqrt(np.mean(x*x))>2
        for name in ('off','chorus'):
            preset(name)
            b.call(2,voice_payload(0,1,1000,timbre=0,level=.15,attack_ms=1,decay_ms=1,sustain=1,release_ms=4))
            time.sleep(.12);arm(16384,trigger=0);read(name+'_sine')
        preset('combined')
        for voice in range(32):
            frequency=65.4063913*2**(voice/12)
            b.call(2,voice_payload(voice,1,frequency,timbre=0,level=.2,attack_ms=2,decay_ms=2,sustain=1,release_ms=10))
        until=time.monotonic()+3
        while time.monotonic()<until:
            state=b.call(4)
            assert state['active']==32 and not state['overrun']
            time.sleep(.025)
        arm(4096,trigger=0);read('combined_32_voices')
        results['polyphony_stress']={'voices':32,'seconds':3,'fx':b.call(25),'audio':b.call(4),'limiter':b.call(27)}
        b.call(3)
        time.sleep(.05);arm(4096,trigger=0);x=read('muted')
        assert not np.any(x)
        results['passed']=True
    finally:
        b.call(3)
        b.call(21,b'\0')
        b.restore(before)
        b.fx(dict(PRESETS['reverb'],monitor_mute=0))
        b.call(10,bytes([6,0]))
        (out/'after.json').write_text(json.dumps(b.state(),indent=2))
        b.device.close()
        (out/'results.json').write_text(json.dumps(results,indent=2))
    print('PASS local presets, host presets, delayed impulses, late reverb, chorus source, and hard mute')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('out',type=Path)
    check(parser.parse_args().out)
