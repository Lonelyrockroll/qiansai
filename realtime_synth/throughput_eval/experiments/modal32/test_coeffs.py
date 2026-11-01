"""Check packed ports in Icarus and the amplitude/bandwidth of the proposed table.

The short frequency-domain check is a table-derived feasibility estimate using
ideal sinusoidal phases; the renderer RTL and integrated signal path need their
own spectral validation.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np

from generate_coeffs import ROOT, generate

FS = 50_000_000/1024
NFFT = 8192


def read_rtl():
    tb = """module tb;
reg [2:0] band,group; wire [75:0] a,b,c,d;
modal32_coeffs dut(band,group,a,b,c,d);
integer j; initial begin for(j=0;j<64;j=j+1)begin
  band=j/8;group=j%8;#1;$display("%d %h %h %h %h",j,a,b,c,d);
end $finish;end endmodule
"""
    with tempfile.TemporaryDirectory(prefix='modal32-coeff-') as directory:
        work = Path(directory)
        (work/'test.v').write_text(tb, encoding='ascii')
        subprocess.run([shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe',
                        '-g2012','-s','tb','-o',work/'sample.vvp',ROOT/'modal32_coeffs.v',work/'test.v'],check=True)
        run = subprocess.run([shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe',work/'sample.vvp'],
                             text=True,capture_output=True,check=True)
    packed = {}
    for line in run.stdout.splitlines():
        cells = line.split()
        if len(cells)==5 and cells[0].isdigit():
            for lane, cell in enumerate(cells[1:]):
                addr = int(cells[0])*4+lane
                packed[addr]=int(cell,16)
    assert len(packed)==256 and all(packed[n]==0 for n in range(192,256))
    def unpack(v):
        # Independent extraction by absolute bit positions, including the 22-bit ratio.
        return (v>>54,(v>>38)&0xffff,(v>>22)&0xffff,(v>>17)&31,(v>>12)&31,v&4095)
    return [[unpack(packed[32*band+i]) for i in range(32)] for band in range(6)]


def note_layout(midi,bands):
    hz=440*2**((midi-69)/12)
    step=round(hz*2**32/FS)
    band=sum(step>=t for t in (11506199,23012398,46024797,92049593,184099186))
    params=np.array(bands[band],dtype=np.int64)
    steps=step*params[:,0]>>16
    allowed=steps<0x70000000
    return params,steps,allowed


def spectrum(midi,bands,level):
    params,steps,allowed=note_layout(midi,bands)
    amps=(params[:,1]+((params[:,2]-params[:,1])*level>>16))<<8
    amps[~allowed]=0
    phases=params[:,5]<<20
    samples=[]
    for i in range(2048+NFFT):
        if i:
            loss=np.maximum(1,(amps>>params[:,3])+(amps>>params[:,4]))
            amps=np.maximum(0,amps-loss)
        wave=np.rint(np.sin(2*np.pi*(phases>>20)/4096)*32767).astype(np.int64)
        total=int(((wave*(amps>>8))>>15).sum())
        # After attack is settled this equals the candidate's unity global envelope.
        samples.append(((total*65535)>>16)*level>>16)
        phases=(phases+steps)&0xffffffff
    data=np.array(samples[-NFFT:]);win=np.hanning(NFFT)
    spectrum=2*np.abs(np.fft.rfft(data*win))/win.sum()
    bins=(steps[allowed]/2**32*NFFT).round().astype(int)
    peaks=[]
    for index in bins:
        peak=index+int(np.argmax(spectrum[index-1:index+2]))-1
        assert abs(peak-index)<=1 and spectrum[peak]>max(spectrum[peak-1],spectrum[peak+1])
        peaks.append(float(spectrum[peak]))
    assert min(peaks)>5 and len(set(bins))==len(bins)
    return dict(allowed=int(sum(allowed)),level_q16=level,
                min_target_peak_pcm=round(min(peaks),3),max_target_peak_pcm=round(max(peaks),3),
                min_relative_db=round(20*math.log10(min(peaks)/max(peaks)),3),
                max_abs_sample=int(np.abs(data).max()))


if __name__=='__main__':
    assert (ROOT/'modal32_coeffs.v').read_text(encoding='ascii')==generate()
    bands=read_rtl()
    for rows in bands:
        assert rows[0][0]==1<<16 and (32<<16)<rows[-1][0]<(64<<16)
        assert all(a[0]<b[0] for a,b in zip(rows,rows[1:]))
        assert all(0<soft<=hard and 10<=s1<=s2<=31 for _,soft,hard,s1,s2,_ in rows)
        assert sum(row[2] for row in rows)==24000
    keys=[n for n in range(36,90) if n%12 not in (1,3,6,8,10)]
    counts={n:int(sum(note_layout(n,bands)[2])) for n in keys}
    assert len(keys)==32 and counts[36]==counts[60]==counts[72]==32
    assert counts[84]==20 and counts[89]==15
    result=dict(kind='Coefficient ROM RTL readback + independent analytic spectral estimate, not hardware capture',
                hard_q15_sum_per_band=24000,first_soft=bands[0][0][1],last_soft=bands[0][-1][1],
                first_hard=bands[0][0][2],last_hard=bands[0][-1][2],limit_hz=7*FS/16,
                white_key_midi_to_bandlimited_mode_count=counts,
                estimated_C4=spectrum(60,bands,16384),estimated_F6=spectrum(89,bands,16384))
    (ROOT/'coefficient_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print('PASS 256 coefficient addresses / four packed lanes; C4, F6:',result['estimated_C4'],result['estimated_F6'])
