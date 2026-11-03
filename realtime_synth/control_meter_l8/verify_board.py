"""Check v25 J9 masks against captured DAC PCM; preserve the current panel settings."""
import argparse
import json
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'host'))
from protocol import Decoder, FS, packet, voice_payload
from fx_tools import FIELDS, PRESETS
from transports import open_device

LIMITS=(66,185,520,1037,2068,4126,8231,16423)
OPS=(4,9,11,12,16,22,25,27,29)
class Board:
    def __init__(self,identifier='com:COM6'):
        self.device=open_device(identifier)
        self.seq=0
        self.decoder=Decoder()
    def call(self,op,payload=b''):
        self.seq=(self.seq+1)&255
        self.device.write(packet(self.seq,op,payload))
        end=time.monotonic()+1.5
        while time.monotonic()<end:
            for v in self.decoder.feed(self.device.read()):
                if (v['seq'],v['opcode'])==(self.seq,op):
                    if v['status']:raise RuntimeError((op,v))
                    return v
            time.sleep(.001)
        raise TimeoutError(op)
    def state(self):
        return {str(n):self.call(n) for n in OPS}
    def fx(self,settings):
        self.call(24,bytes(int(settings[k]) for k in FIELDS))
        for _ in range(100):
            fx=self.call(25)
            if not fx['pending'] and all(fx[k]==settings[k] for k in FIELDS):return
        raise TimeoutError('FX settings did not settle')
    def note(self,gate,level):
        self.call(2,voice_payload(0,gate,FS/128,0,level,2,10,1,3))
    def check_tone(self,level,muted):
        self.note(1,level)
        try:
            time.sleep(.09)
            self.call(21,bytes([1,0])+struct.pack('<HI',256,0))
            masks=[self.call(29)['lamps'] for _ in range(4)]
            info=self.call(22)
            assert info['ready'] and info['count']==256 and not info['error'],info
        finally:
            self.note(0,level)
        raw=bytearray()
        for address in range(0,256,6):
            n=min(6,256-address)
            chunk=self.call(23,struct.pack('<HHB',info['capture_id'],address,n))
            assert chunk['offset']==address and chunk['count']==n
            raw.extend(bytes.fromhex(chunk['data']))
        assert zlib.crc32(raw)==info['crc32']
        peak=max(abs(v) for v in struct.unpack('<256h',raw))
        segments=0 if muted else sum(peak>=t for t in LIMITS)
        expected=(0xff << (8-segments)) & 0xff
        assert peak>=LIMITS[0] and masks==[expected]*4,(level,peak,masks,expected)
        time.sleep(.26)
        assert self.call(29)['lamps']==0
        return dict(voice_level=level,pcm_peak=peak,masks=masks,segments=expected.bit_count(),crc=info['crc32'])
    def restore(self,s):
        self.call(3)
        view=s['11'];loop=s['16'];key=s['9']
        self.call(5,bytes([s['27']['gain_mode']]))
        envelope=(672,2,0,8) if view['timbre']==4 else (269,6,40000,5)
        self.call(7,struct.pack('<BBB8H',loop['key_mode'],key['key'],view['timbre'],loop['keyboard_level'],
                                view['press'],view['release'],*envelope,view['sensitivity']))
        if not self.call(11)['drum_mode']:self.call(10,bytes([14]))
        self.call(10,bytes([7])+struct.pack('<H',loop['drum_level']))
        if not view['drum_mode']:self.call(10,bytes([14]))
        self.call(10,bytes([6,view['focus']]))
        self.fx(s['25'])
        for _ in range(80):
            state=self.call(9)
            if loop['key_mode'] in (0,3) or state['calibrated']:break
            time.sleep(.02)
        assert loop['key_mode'] in (0,3) or (state['calibrated'] and not state['fault']),state

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',action='store_true',help='save settings before SRAM reconfiguration')
    parser.add_argument('--restore-only',action='store_true',help='restore saved settings after a power cycle, without playing test notes')
    args=parser.parse_args()
    b=Board()
    try:
        save=ROOT/'before_v25.json'
        if args.before:
            s=b.state()
            if s['16']['length_set'] or s['22']['ready'] or s['22']['recording'] or s['22']['armed'] or s['4']['active']:
                raise RuntimeError('Live audio, a Loop or a capture is present; postpone reconfiguration.')
            assert s['4']['firmware']==24
            save.write_text(json.dumps(s,indent=2))
            print('Captured v24 settings; no active voices, Loop or pending PCM capture.');return
        s=json.loads(save.read_text())
        assert b.call(1)['firmware']==25
        if args.restore_only:
            b.restore(s)
            state=b.state()
            assert state['4']['amp_muted'] and state['29']['lamps']==0
            assert state['16']['drum_level']==s['16']['drum_level'] and state['16']['keyboard_level']==s['16']['keyboard_level']
            assert state['11']['timbre']==s['11']['timbre'] and state['25']['mask']==s['25']['mask']
            print('PASS restored v25 panel settings and scan; muted, lamps off.')
            return
        results={}
        try:
            b.call(3);time.sleep(.05)
            assert b.call(29)['lamps']==0
            b.call(7,struct.pack('<BBB8H',0,12,0,16384,256,128,269,6,40000,5,64))
            b.call(10,bytes([7])+struct.pack('<H',s['16']['drum_level']))
            assert b.call(11)['level']==s['16']['drum_level']
            # Use short, modest-level notes at the same panel volume and master gain.
            b.call(5,bytes([s['27']['gain_mode']]))
            fx=dict(PRESETS['off'],monitor_mute=0);b.fx(fx);b.call(6)
            for _ in range(100):
                if b.call(4)['amp_ready']:break
                time.sleep(.01)
            assert b.call(4)['amp_ready']
            assert b.call(29)['lamps']==0
            results['quiet']=b.check_tone(.016,False)
            results['louder']=b.check_tone(.10,False)
            assert 0<results['quiet']['segments']<results['louder']['segments']
            b.fx(dict(fx,monitor_mute=1))
            results['monitor_muted']=b.check_tone(.10,True)
            b.call(3);b.call(21);b.call(28,bytes([2,7]))
            assert b.call(29)['lamps']==0x80
            time.sleep(2.50)
            assert not b.call(29)['testing'] and b.call(29)['lamps']==0
        finally:
            b.restore(s)
        results['restored']=b.state()
        assert results['restored']['4']['amp_muted'] and results['restored']['29']['lamps']==0
        assert results['restored']['16']['drum_level']==s['16']['drum_level'] and results['restored']['16']['keyboard_level']==s['16']['keyboard_level']
        assert results['restored']['11']['timbre']==s['11']['timbre'] and results['restored']['25']['mask']==s['25']['mask']
        (ROOT/'meter_hardware.json').write_text(json.dumps(results,indent=2)+'\n')
        print('PASS J9 board tests:',{k:(v['pcm_peak'],v['segments']) for k,v in results.items() if k!='restored'})
    finally:b.device.close()

if __name__=='__main__':main()
