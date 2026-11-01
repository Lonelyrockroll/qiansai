"""Compare real phone-independent PC keyboard packets, FPGA panel mask and captured PCM."""
import argparse,json,struct,sys,time,zlib
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'control_meter_l8'))
from verify_board import Board
from protocol import FS,KEY_CONFIG,KEY_STATUS,PCM_CONTROL,PCM_STATUS,PCM_READ,WHITE_KEYS
from fx_tools import PRESETS
from server import Controller

def capture_frequency(b,controller,index):
    note=WHITE_KEYS[index];expected=440*2**((note-69)/12)
    controller.note_on(note)
    try:
        time.sleep(.06)
        assert b.call(KEY_STATUS)['pressed_mask']==1<<index
        n=3072
        b.call(PCM_CONTROL,bytes([1,0])+struct.pack('<HI',n,0))
        for _ in range(100):
            info=b.call(PCM_STATUS)
            if info['ready']:break
            time.sleep(.003)
        assert info['ready'] and info['count']==n and not info['error'],info
    finally:controller.note_off(note)
    assert b.call(KEY_STATUS)['pressed_mask']==0
    data=bytearray()
    for address in range(0,n,6):
        count=min(6,n-address)
        read=b.call(PCM_READ,struct.pack('<HHB',info['capture_id'],address,count))
        assert read['offset']==address and read['count']==count
        data.extend(bytes.fromhex(read['data']))
    assert zlib.crc32(data)==info['crc32']
    pcm=struct.unpack(f'<{n}h',data)
    edges=[i-a/(v-a) for i,(a,v) in enumerate(zip(pcm,pcm[1:])) if a<=0<v]
    assert len(edges)>=3 and max(pcm)>0>min(pcm)
    hz=FS*(len(edges)-1)/(edges[-1]-edges[0])
    assert abs(hz/expected-1)<.005,(index,hz,expected)
    print(f'H{index+1} mask={1<<index:08X} expected={expected:.3f} Hz captured={hz:.3f} Hz',flush=True)
    return dict(key=index+1,midi=note,expected_hz=expected,measured_hz=hz,panel_mask=1<<index,crc32=info['crc32'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',action='store_true')
    parser.add_argument('--restore-only',action='store_true')
    args=parser.parse_args()
    b=Board();state_path=R/'before_v26.json'
    try:
        if args.before:
            s=b.state()
            if s['16']['length_set'] or s['22']['ready'] or s['22']['armed'] or s['22']['recording'] or s['4']['active']:
                raise RuntimeError('A live voice, recorded loop or capture is present; postpone loading.')
            assert s['4']['firmware']==25
            state_path.write_text(json.dumps(s,indent=2));print('Captured v25 settings. No active notes, Loop or PCM capture.')
            return
        s=json.loads(state_path.read_text())
        assert b.call(1)['firmware']==26
        report={}
        try:
            if not args.restore_only:
                b.call(3)
                b.call(KEY_CONFIG,struct.pack('<BBB8H',0,14,0,16384,256,128,269,6,40000,5,64))
                b.fx(dict(PRESETS['off'],monitor_mute=1))
                b.call(6)
                for _ in range(100):
                    status=b.call(4)
                    if status['amp_ready']:break
                    time.sleep(.006)
                assert status['amp_ready'] and status['amp_muted']
                # Use the production host note allocator and packet encoder. Slot 19 is deliberately not H1.
                c=Controller.__new__(Controller);c.exchange=b.call;c.keyboard={'mode':0};c.feedback=status
                c.next_voice=19;c.notes={};c.release_until={}
                c.params=dict(timbre=0,level=.12,attack_ms=2,decay_ms=10,sustain=1,release_ms=3)
                report['pcm_pitches']=[capture_frequency(b,c,i) for i in (0,14,31)]
                for i in (14,16,18):c.note_on(WHITE_KEYS[i])
                report['chord_mask']=b.call(KEY_STATUS)['pressed_mask']
                assert report['chord_mask']==0x54000
                c.note_off(WHITE_KEYS[16])
                assert b.call(KEY_STATUS)['pressed_mask']==0x44000
                b.call(3);assert b.call(KEY_STATUS)['pressed_mask']==0
                b.call(PCM_CONTROL)
        finally:b.restore(s)
        final=b.state()
        assert final['4']['amp_muted'] and final['11']['locked'] and final['29']['lamps']==0
        assert all(final['16'][k]==s['16'][k] for k in ('timbre','key_mode','drum_level','keyboard_level'))
        assert final['25']['mask']==s['25']['mask']
        report['restored']=final
        if not args.restore_only:(R/'hardware_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PASS restored settings, muted; HDMI locked, scan calibration:',final['9']['calibrated'])
    finally:b.device.close()
if __name__=='__main__':main()
