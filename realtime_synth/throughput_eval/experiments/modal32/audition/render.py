"""Render a bit-exact-to-the-candidate-output C4 A/B (same fixed listening gain)."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
import numpy as np

HERE=Path(__file__).resolve().parent
CANDIDATE=HERE.parent
SYNTH=HERE.parents[3]
SAMPLE_RATE=50_000_000/1024
WAV_RATE=round(SAMPLE_RATE)
LISTENING_GAIN=4  # identical for A and B; never peak-normalize separately


def save_wave(path,values):
    assert int(np.abs(values).max())<32768
    with wave.open(str(path),'wb') as wav:
        wav.setparams((1,2,WAV_RATE,0,'NONE','not compressed'))
        wav.writeframes(values.astype('<i2').tobytes())
    with wave.open(str(path),'rb') as wav:
        assert wav.getparams()[:4]==(1,2,WAV_RATE,len(values))
        assert np.array_equal(np.frombuffer(wav.readframes(len(values)),dtype='<i2'),values)


def upper_partial_evidence(output):
    """Compare matched upper-partial windows in the two RTL takes, in raw PCM units."""
    n=8192;window=np.hanning(n)
    amplitudes=np.abs(np.fft.rfft(output[2048:2048+n]*window[:,None],axis=0))*2/window.sum()
    words=(CANDIDATE/'modal32_coeffs.v').read_text(encoding='ascii')
    peaks=[]
    for i in range(16,32):
        # Middle C is band 2. Use its programmed fixed-point bin, then measure the recorded WAV.
        ratio=int(re.search(f"8'd{64+i}: coeff=76'h([0-9a-f]+);",words).group(1),16)>>54
        center=round(((23012828*ratio)>>16)*n/2**32)
        peaks.append(amplitudes[center-1:center+2].max(axis=0))
    peaks=np.array(peaks)
    change_db=20*np.log10(peaks[:,1]/np.maximum(1e-8,peaks[:,0]))
    assert float(change_db.min())>40
    return dict(window='8192-point Hann from frame 2048, raw PCM before shared listening gain',
                partial_17_to_32_max_when_disabled=float(peaks[:,0].max()),
                partial_17_to_32_min_when_enabled=float(peaks[:,1].min()),
                smallest_enabled_over_disabled_db=float(change_db.min()))


if __name__=='__main__':
    inputs=[HERE/'tb_ab.v',CANDIDATE/'modal32.v',CANDIDATE/'modal32_coeffs.v',
            SYNTH/'control_key_gain/piano_modal_tables_compact.v']
    with tempfile.TemporaryDirectory(prefix='modal32-ab-') as name:
        work=Path(name);binary=work/'audition.vvp'
        subprocess.run([shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe','-g2012',
                        '-s','tb_ab','-o',binary,*inputs],check=True,cwd=work)
        result=subprocess.run([shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe',binary],
                              text=True,capture_output=True,check=True,timeout=240,cwd=work)
        assert 'PASS' in result.stdout,result.stdout
        output=np.loadtxt(work/'samples.txt',dtype=np.int32)
    assert output.shape==(60000,2) and not np.any(output[-1024:]) and not np.array_equal(output[:,0],output[:,1])
    listening=output*LISTENING_GAIN
    files=['C4_16_components.wav','C4_32_components.wav','C4_AB_16_then_32.wav']
    save_wave(HERE/files[0],listening[:,0]);save_wave(HERE/files[1],listening[:,1])
    gap=round(0.20*SAMPLE_RATE)
    duet=np.concatenate((listening[:,0],np.zeros(gap,dtype=np.int32),listening[:,1]))
    save_wave(HERE/files[2],duet)
    report=dict(kind='RTL module sample output on done, accelerated idle simulation; not a board or microphone recording',
                midi=60,dds_step=23012828,input_level=16384,key_down_frames=50000,frames_per_take=60000,
                exact_sample_rate=SAMPLE_RATE,wav_sample_rate=WAV_RATE,shared_linear_listening_gain=LISTENING_GAIN,
                compiled_sha256={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},
                a_peak=int(np.abs(listening[:,0]).max()),b_peak=int(np.abs(listening[:,1]).max()),
                a_rms=float(np.sqrt(np.mean(listening[:,0].astype(float)**2))),
                b_rms=float(np.sqrt(np.mean(listening[:,1].astype(float)**2))),
                a_b_difference_rms=float(np.sqrt(np.mean((listening[:,0]-listening[:,1]).astype(float)**2))),
                gap_frames=gap,combined_seconds=len(duet)/WAV_RATE,upper_partial_evidence=upper_partial_evidence(output),
                wav_sha256={f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in files})
    (HERE/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(result.stdout.strip())
    print('PASS WAV readback;',report['combined_seconds'],'s; peaks',report['a_peak'],report['b_peak'])
