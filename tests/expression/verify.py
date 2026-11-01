"""Render actual RTL sample frames and measure the pitch of the generated C4."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json, shutil, subprocess, tempfile, wave
import numpy as np

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
FPGA=PROJECT/'fpga'
OUT=HERE/'results'
FS=50_000_000/1024
SOURCES=['pitch_expression.v','modal32.v','modal32_coeffs.v','piano_modal_tables_compact.v','waveform_rom.v']

def run(cmd, cwd):
    return subprocess.run(cmd,cwd=cwd,check=True,capture_output=True,text=True,timeout=220).stdout

def crossing_hz(pcm, start, stop):
    x=pcm[start:stop]
    k=np.flatnonzero((x[:-1]<=0)&(x[1:]>0))
    times=start+k-x[k]/(x[k+1]-x[k])
    return (times[:-1]+times[1:])/(2*FS), FS/np.diff(times)

def main():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tang-expr-') as scratch:
        w=Path(scratch)
        shutil.copyfile(HERE/'j18_gestures.hex',w/'j18_gestures.hex')
        iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
        vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
        run([iv,'-g2012','-s','tb_gestures','-o',str(w/'hid.vvp'),str(FPGA/'native_keypad_drums.v'),
             str(HERE/'tb_gestures.v')],w)
        print(run([vvp,str(w/'hid.vvp')],w).splitlines()[0])
        tb=(HERE/'tb_audio.v').read_text()
        (w/'reference.v').write_text(tb.replace('.pitch_offset(offset),.cfg_valid(cfg)', '.cfg_valid(cfg)'))
        def capture(case):
            name,tone,voices,length,legacy=case
            engine=(PROJECT/'realtime_synth/control_key_gain' if legacy else FPGA)/'synth_engine_shared.v'
            bench=w/'reference.v' if legacy else HERE/'tb_audio.v'
            binary=w/(name+'.vvp')
            run([iv,'-g2012','-s','tb_audio','-P',f'tb_audio.VOICES={voices}','-o',str(binary),
                 str(bench),str(engine),*[str(FPGA/s) for s in SOURCES]],w)
            msg=run([vvp,str(binary),f'+OUT={name}.txt',f'+TONE={tone}',f'+N={length}'],w)
            return name,(np.loadtxt(w/(name+'.txt'),dtype=int),msg.splitlines()[0])
        cases=[('sine',0,1,92000,False),('piano',4,1,40000,False),('original_piano',4,1,40000,True),
               ('mixed',1,32,192,False)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            data=dict(pool.map(capture,cases))
        pcm=data['sine'][0][:,0].astype(float)
        def mean(a,b):
            return float(np.mean(crossing_hz(pcm,a,b)[1]))
        base=mean(2000,7000); bent=mean(15500,19500); back=mean(27200,29700)
        t,hz=crossing_hz(pcm,35000,91000)
        cents=1200*np.log2(hz/base)
        crosses=np.flatnonzero((cents[:-1]<0)&(cents[1:]>=0))
        periods=t[crosses+1]-cents[crosses+1]*(t[crosses+1]-t[crosses])/(cents[crosses+1]-cents[crosses])
        rate=float((len(periods)-1)/(periods[-1]-periods[0]))
        depth=float((np.percentile(cents,99)-np.percentile(cents,1))/2)
        assert abs(base-261.626)<.15 and abs(1200*np.log2(bent/base)-200)<1.5 and abs(back-base)<.16
        assert 5.4<rate<5.6 and 47<depth<53
        assert np.array_equal(data['piano'][0][:,0],data['original_piano'][0][:,0])
        for name in ('sine','piano'):
            clip=data[name][0][:,0]*2
            assert np.max(np.abs(clip))<32768
            # Listening gain is the same throughout; avoid a click at the end of the clip.
            clip[-256:]=np.round(clip[-256:]*np.linspace(1,0,256)).astype(int)
            with wave.open(str(OUT/(name+'_C4.wav')),'wb') as stream:
                stream.setparams((1,2,round(FS),0,'NONE','not compressed'))
                stream.writeframes(clip.astype('<i2').tobytes())
        result=dict(scope='RTL simulation, melodic mix, accelerated idle clocks, no analog output',
                    base_hz=base,bent_hz=bent,returned_hz=back,vibrato_hz=rate,vibrato_cents=depth,
                    piano_samples_identical=40000,latencies={k:t for k,(_,t) in data.items()})
        (OUT/'measurements.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

if __name__=='__main__':main()
