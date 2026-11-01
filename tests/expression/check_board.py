"""Measure v27 pitch gestures on a freshly loaded board. The analog monitor stays muted."""
import argparse,hashlib,json,struct,sys,time,zlib
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'realtime_synth/throughput_eval'))
from verify32 import Board, FS, PRESETS, status, wait_for, require, voice_payload, save_json
from verify import crossing_hz

def play(board,timbre):
    board.call(2,voice_payload(0,1,440*2**(-9/12),timbre=timbre,level=.25,attack_ms=2,
                              decay_ms=10,sustain=1,release_ms=8)+b'\x8e')

def adjust(board,action,count):
    for _ in range(abs(count)):
        board.call(10,bytes([action,int(count>0),0]))

def capture(board,folder,report,name,n,delay=0,piano=False):
    last=board.call(22)['capture_id']
    board.call(21,bytes([1,int(piano)])+struct.pack('<HI',n,delay))
    if piano:play(board,4)
    m=wait_for(lambda:board.call(22),lambda s:s['ready'],'capture',2)
    require(m['capture_id']==(last+1)%65536 and m['count']==m['target']==n and not m['error'],'bad PCM capture')
    health=board.call(4); gain=board.call(27)
    require(health['gated']==1 and health['active']==1 and health['amp_muted'] and
            not (health['overrun'] or health['clipped'] or health['watchdog'] or gain['limited_frames']),'unexpected mix')
    raw=bytearray()
    for idx in range(0,n,6):
        length=min(6,n-idx); r=board.call(23,struct.pack('<HHB',m['capture_id'],idx,length))
        buf=bytes.fromhex(r['data'])
        require(r['capture_id']==m['capture_id'] and r['offset']==idx and r['count']==length
                and len(buf)==2*length,'misaddressed PCM block')
        raw.extend(buf)
    require(zlib.crc32(raw)==m['crc32'],'readback CRC')
    (folder/(name+'.pcm')).write_bytes(raw)
    report['takes'][name]=dict(capture=m,health=health,sha256=hashlib.sha256(raw).hexdigest())
    save_json(folder/'result.json',report)
    print(name,'CRC',hex(m['crc32']),flush=True)
    return np.frombuffer(raw,dtype='<i2').astype(float)

def measure(folder):
    folder.mkdir(exist_ok=False,parents=True)
    b=Board()
    try:
        orig=status(b)
        require(all(s['firmware']==27 for s in orig.values()) and not orig['4']['amp_hold'] and not orig['4']['active']
                and orig['16']['key_mode']==0 and not orig['16']['length_set'] and not orig['14']['layers']
                and not any(orig['22'][k] for k in ('armed','recording','ready')), 'expected fresh idle v27')
    except BaseException:
        b.device.close();raise
    report={'scope':'Board final digital PCM with analog monitor muted; gestures injected through display actions. Physical HID checked separately.',
            'before':orig,'takes':{}}
    def warm():
        b.call(3)
        wait_for(lambda:b.call(4),lambda x:not x['active'] and not x['amp_ready'],'drain')
        b.call(6)
        wait_for(lambda:b.call(4),lambda x:x['amp_ready'] and x['amp_muted'],'warm')
    try:
        b.fx(dict(PRESETS['off'],monitor_mute=1));b.call(5,b'\1');warm();play(b,0)
        time.sleep(.06)
        base=capture(b,folder,report,'base',4096)
        adjust(b,13,4)
        require(b.call(12)['bend_cents']==200,'bend control')
        bent=capture(b,folder,report,'bent',4096,delay=3600)
        time.sleep(.40)
        require(b.call(12)['bend_cents']==0,'bend return')
        returned=capture(b,folder,report,'return',4096)
        adjust(b,15,5);require(b.call(12)['vibrato_cents']==50,'vibrato control')
        vibrato=capture(b,folder,report,'vibrato',24576,delay=1200)
        means=[float(np.mean(crossing_hz(x,0,len(x))[1])) for x in (base,bent,returned)]
        t,hz=crossing_hz(vibrato,0,len(vibrato)); cents=1200*np.log2(hz/means[0])
        k=np.flatnonzero((cents[:-1]<0)&(cents[1:]>=0))
        times=t[k]-cents[k]*(t[k+1]-t[k])/(cents[k+1]-cents[k])
        rate=(len(times)-1)/(times[-1]-times[0]);depth=(np.percentile(cents,99)-np.percentile(cents,1))/2
        report['frequency_hz']=means
        report['vibrato_hz']=rate;report['vibrato_peak_cents']=depth
        require(abs(means[0]-261.626)<.2 and abs(means[1]-293.665)<.6 and abs(means[2]-means[0])<.25,'bend frequency check')
        require(5.35<rate<5.65 and 47<depth<54,'vibrato frequency/depth check')
        warm();piano=capture(b,folder,report,'piano_plain',4096,256,piano=True)
        warm();adjust(b,15,5);adjust(b,13,4)
        altered=capture(b,folder,report,'piano_bypass',4096,256,piano=True)
        require(np.array_equal(piano,altered) and np.max(np.abs(piano))>0,'piano bypass mismatch')
        report['piano_equal_samples']=len(piano);report['result']='passed'
    finally:
        try:
            b.call(3);b.call(21);wait_for(lambda:b.call(4),lambda x:not x['amp_ready'] and not x['active'],'final drain')
            b.call(5,bytes([orig['27']['gain_mode']]));b.fx(orig['25']);report['after']=status(b)
        finally:
            b.device.close();save_json(folder/'result.json',report)
    print('Board:',means,rate,depth,'piano equal',len(piano),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    measure(p.parse_args().folder)
