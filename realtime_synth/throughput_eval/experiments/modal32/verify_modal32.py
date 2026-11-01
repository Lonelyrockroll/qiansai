"""Offline RTL evidence; never programs hardware. Python 3 + numpy + Icarus."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'evidence'
PROJECT=ROOT.parents[2]
CORE=PROJECT/'control_key_gain'
RTL=PROJECT/'rtl'
FS=50_000_000/1024
N=2048
BASE_STEP=11*(2**32//N)
SELECTED=11                     # zero-based index, harmonic number 12
SHIFT=round(3*65536/11)         # move just that ratio +3 analysis bins at this root
SOURCES=[CORE/'synth_engine_shared.v',CORE/'piano_modal_tables_compact.v',CORE/'audio_output_limited.v',
         CORE/'pcm_peak_limiter.v',CORE/'audio_effects.v',CORE/'chorus_lfo.v',RTL/'audio_tx.v',
         RTL/'waveform_rom.v',ROOT/'modal32.v',ROOT/'tb_modal32.v']
TABLE=re.compile(r"(8'd(\d+):\s*coeff=76'h)([0-9a-fA-F]+)")


def check(condition,message):
    if not condition:raise RuntimeError(message)


def inputs():
    OUT.mkdir(exist_ok=True)
    white=[n for n in range(36,90) if n%12 in (0,2,4,5,7,9,11)]
    steps=[round((440*2**((n-69)/12))*2**32/FS) for n in white]
    (OUT/'white_steps.hex').write_text(''.join(f'{n:08x}\n' for n in steps))
    rom=(ROOT/'modal32_coeffs.v').read_text()
    table={int(addr):int(word,16) for _,addr,word in TABLE.findall(rom)}
    check(set(table)==set(range(192)),'Incomplete 6-band x 32-mode ROM')
    def alter(m):
        word=int(m[3],16)
        if int(m[2])%32==SELECTED:word+=SHIFT<<54
        return m[1]+f'{word:019x}'
    retuned=TABLE.sub(alter,rom)
    (OUT/'retuned_coeffs.v').write_text(retuned)
    modified={int(a):int(v,16) for _,a,v in TABLE.findall(retuned)}
    check(all(modified[i]-table[i]==((SHIFT<<54) if i%32==SELECTED else 0) for i in table),'Retune changed other coefficients')
    return steps,table


def build(tag):
    cmd=['E:/iverilog/bin/iverilog.exe','-g2012','-s','tb_modal32']
    if tag=='muted':cmd+=['-DMUTE_MODE_12']
    rom=OUT/'retuned_coeffs.v' if tag=='retuned' else ROOT/'modal32_coeffs.v'
    subprocess.run([*cmd,'-o',OUT/(tag+'.vvp'),*SOURCES,rom],cwd=OUT,check=True)


def sim(name,tag,n):
    cmd=['E:/iverilog/bin/vvp.exe',tag+'.vvp',f'+N={n}',f'+PREFIX={name}']
    if name in ('full','hot'):cmd+=['+FULL']
    if name=='hot':cmd+=['+HOT']
    with (OUT/(name+'.log')).open('w') as log:
        result=subprocess.run(cmd,cwd=OUT,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    check(result.returncode==0,(OUT/(name+'.log')).read_text())
    print(name,(OUT/(name+'.log')).read_text().splitlines()[0],flush=True)


def increments(step,table):
    band=sum(step>=limit for limit in (11506199,23012398,46024797,92049593,184099186))
    return [(step*(table[32*band+i]>>54))>>16 for i in range(32)]


def active_mask(step,table):
    return sum(1<<i for i,v in enumerate(increments(step,table)) if 0<v<0x70000000)


def series(name,voices,expected):
    pcm=np.fromfile(OUT/(name+'.pcm'),dtype='<i2').astype(float)
    frames=[line.split() for line in (OUT/(name+'.frames')).read_text().splitlines()]
    check(len(pcm)==len(frames) and len(frames)>0,name+' capture length')
    for line in frames:
        check(int(line[0])==voices and int(line[2],16)==(1<<voices)-1,name+' wrong voice reporting')
        check([int(s,16) for s in line[3:]]==expected,name+' mode mask differs from per-note cutoff')
        check(0<int(line[1])<1024,name+' deadline')
    stats=(OUT/(name+'.stats')).read_text().splitlines()
    nz=[int(x,16) for x in next(l for l in stats if l.startswith('nonzero_products ')).split()[1:]]
    check(nz==expected,name+' some supposedly active mode made no contribution in common capture window')
    timings=next(l for l in stats if l.startswith('max_cycles ')).split()
    maximum=int(timings[1])
    check(maximum<1024,name+' deadline across complete test')
    return pcm,dict(frame_count=len(pcm),pcm_peak=int(max(abs(pcm))),rms=float(np.sqrt(np.mean(pcm**2))),
                    max_tick_to_engine_valid_clocks=maximum,limited_frames_entire_run=int(timings[5]),steady_latency_minmax=[min(int(l[1]) for l in frames),max(int(l[1]) for l in frames)],
                    per_voice_active_count=[m.bit_count() for m in expected],active_model_states=sum(m.bit_count() for m in expected),
                    pcm_sha256=hashlib.sha256((OUT/(name+'.pcm')).read_bytes()).hexdigest())


def fft(signal):
    w=np.hanning(len(signal))
    return np.abs(np.fft.rfft(w*(signal-np.mean(signal))))*2/w.sum()


def spectral_metrics(a,hz):
    mid=int(round(hz*N/FS))
    k=mid-1+int(np.argmax(a[mid-1:mid+2]))
    # Log-parabolic interpolation compensates off-bin Hann peak bias; report both raw bin and fitted values.
    l,c,r=np.log(np.maximum(a[k-1:k+2],1e-12));x=.5*(l-r)/(l-2*c+r) if l-2*c+r else 0.
    amp=float(np.exp(c-.25*(l-r)*x))
    side=float(max(*a[mid-5:mid-2],*a[mid+3:mid+6]))
    return dict(expected_hz=float(hz),fft_bin=k,fitted_hz=float((k+x)*FS/N),amplitude_pcm=amp,
                local_contrast_db=float(20*np.log10(amp/max(side,1e-12))))


def delta_fit(signal,hz):
    x=(np.arange(len(signal))-(len(signal)-1)/2)/len(signal)
    a=2*np.pi*hz*np.arange(len(signal))/FS
    design=np.stack([np.sin(a),np.cos(a),x*np.sin(a),x*np.cos(a),np.ones_like(x)],axis=1)
    beta=np.linalg.lstsq(design,signal,rcond=None)[0]
    error=signal-design@beta
    fit_db=20*np.log10(max(np.sqrt(np.mean(signal**2)),1e-10)/max(np.sqrt(np.mean(error**2)),1e-10))
    return dict(fitted_center_amplitude_pcm=float(np.hypot(beta[0],beta[1])),residual_rejection_db=float(fit_db))


def analyze(steps,table,report_name='modal32_validation.json'):
    active=[active_mask(step,table) for step in steps]
    records={}
    full,records['32_white_keys']=series('full',32,active)
    hot,records['32_white_keys_max_pc_level_gain2']=series('hot',32,active)
    check(max(np.max(np.abs(full)),np.max(np.abs(hot)))<=28000,'Final PCM exceeded limiter ceiling')
    maxline=next(l for l in (OUT/'full.stats').read_text().splitlines() if l.startswith('max_step_mask'))
    check(int(maxline.split()[1],16)==active_mask(0x0ff00000,table),'input clamp did not apply bandlimit correctly')
    base,records['one_note']=series('single',1,[0xffffffff])
    muted,records['one_note_mode12_muted']=series('muted',1,[0xffffffff ^ (1<<SELECTED)])
    tuned,records['one_note_mode12_retuned']=series('retuned',1,[0xffffffff])
    check(len(base)==len(muted)==len(tuned)==N,'FFT length')
    freqs=[step*FS/2**32 for step in increments(BASE_STEP,table)]
    new_hz=((BASE_STEP*((table[32*2+SELECTED]>>54)+SHIFT))>>16)*FS/2**32
    base_fft,mute_fft,tune_fft=map(fft,(base,muted,tuned))
    rows=[spectral_metrics(base_fft,f) for f in freqs]
    for row in rows:
        check(abs(row['fitted_hz']-row['expected_hz'])<FS/N*.65,'mode frequency mismatch: '+str(row))
        check(row['amplitude_pcm']>=3 and row['local_contrast_db']>=10,'weak/obscured mode: '+str(row))
    old=rows[SELECTED]
    drop=20*np.log10(old['amplitude_pcm']/max(mute_fft[old['fft_bin']],1e-12))
    translated=spectral_metrics(tune_fft,new_hz)
    check(drop>=24 and abs(translated['expected_hz']-translated['fitted_hz'])<FS/N*.65,'selective mute/retune failed')
    delta_a=delta_fit(base-muted,old['expected_hz'])
    delta_b=delta_fit(tuned-muted,new_hz)
    check(min(delta_a['residual_rejection_db'],delta_b['residual_rejection_db'])>20,'A/B delta has significant energy outside tested oscillator')
    unchanged=max(abs(rows[i]['amplitude_pcm']-spectral_metrics(mute_fft,f)['amplitude_pcm']) for i,f in enumerate(freqs) if i!=SELECTED)
    check(unchanged<2.0,'other modes changed in mute comparison')
    input_incs=[inc for step in steps for inc in increments(step,table) if inc<0x70000000]
    full_fft=fft(full)
    with (OUT/'full_chord_spectrum.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['bin','Hz','final_pcm_amplitude'])
        for k,amp in enumerate(full_fft):w.writerow([k,k*FS/len(full),amp])
    with (OUT/'single_spectrum.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['bin','Hz','full32','muted12','retuned12'])
        for k in range(len(base_fft)):w.writerow([k,k*FS/N,base_fft[k],mute_fft[k],tune_fft[k]])
    report=dict(scope='Icarus RTL simulation: v26 melody engine and original output gain/limiter, bypassed effects, PCM at actual audio_tx frame ticks. No board or acoustic measurement.',
        sample_rate=FS,system_hz=50_000_000,frame_clocks=1024,single_root_hz=BASE_STEP*FS/2**32,
        single_active_modes=32,single_spectrum=rows,cases=records,
        min_single_mode_amplitude_pcm=min(r['amplitude_pcm'] for r in rows),
        min_single_mode_contrast_db=min(r['local_contrast_db'] for r in rows),
        selected={'number':SELECTED+1,'old_hz':old['expected_hz'],'new_hz':new_hz,'drop_db':float(drop),'new_peak':translated,
                  'unselected_peak_max_delta_pcm':float(unchanged),'ab_delta':delta_a,'retuned_ab_delta':delta_b},
        full_distinct_DDS_increments=len(set(input_incs)),full_active_per_frame=len(input_incs),
        full_occupied_nearest_fft_bins=len(set(round(inc*len(full)/2**32) for inc in input_incs)),
        full_fft_bin_hz=FS/len(full),full_fft_max_amplitude_pcm=float(full_fft.max()),
        full_state_updates_s=len(input_incs)*FS,
        limit='32x32 is register capacity only. Cutoff removes modes above 7Fs/16. Overlapping/very close partials from different notes are not separately demonstrated as audible by state counts.',
        source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [*SOURCES,ROOT/'modal32_coeffs.v',OUT/'retuned_coeffs.v']})
    (ROOT/report_name).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(rows),'single-note modes;',len(input_incs),'active white-key component states;',
          records['32_white_keys']['max_tick_to_engine_valid_clocks'],'clocks; selected drop',round(drop,2),'dB')


def lutram_validation(long_run=False):
    """Check the physical alternative's exact vendor primitive model against the long baseline."""
    global OUT
    baseline=OUT;variant=ROOT/'state_ram/modal32_lutram.v'
    OUT=ROOT/('evidence_state_ram_full' if long_run else 'evidence_state_ram');OUT.mkdir(exist_ok=True)
    library=Path('E:/Gowin_edu/Gowin_V1.9.11.03_Education_x64/IDE/simlib/gw5a/prim_sim.v')
    primitive=re.search(r'module RAM16SDP4\s*\(.*?endmodule',library.read_text(errors='replace'),re.S)
    check(primitive is not None,'Cannot find vendor RAM16SDP4 primitive')
    model=OUT/'ram16sdp4.v';model.write_text(primitive.group())
    SOURCES[SOURCES.index(ROOT/'modal32.v')]=variant;SOURCES.append(model)
    steps,table=inputs()
    sources=[*SOURCES,ROOT/'modal32_coeffs.v',OUT/'retuned_coeffs.v']
    signature={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
    for tag in ('base','muted','retuned'):build(tag)
    tests=[('single','base',N),('muted','muted',N),('retuned','retuned',N),('full','base',4096),('hot','base',512)] if long_run else [
           ('single','base',256),('muted','muted',256),('retuned','retuned',256),('full','base',128),('hot','base',64)]
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda c:sim(*c),tests))
    check(signature=={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},'Inputs changed during simulation')
    records={}
    for name,_,length in tests:
        full=name in ('full','hot')
        masks=[active_mask(s,table) for s in steps] if full else [0xffffffff^(1<<SELECTED) if name=='muted' else 0xffffffff]
        _,records[name]=series(name,32 if full else 1,masks)
        raw=(OUT/(name+'.pcm')).read_bytes()
        check(len(raw)==length*2 and raw==(baseline/(name+'.pcm')).read_bytes()[:length*2],name+' differs from base')
    if long_run:
        analyze(steps,table,'modal32_lutram_validation.json')
        print('PASS vendor LUTRAM full-length PCM is bit-exact in all five runs')
        return
    result={'scope':'Cycle-accurate RTL using the GW5A RAM16SDP4 vendor primitive. All five final PCM prefixes are bit-exact against baseline all-on, ablated, retuned, full and hot captures. Longer baseline FFT is not a standalone long run of this alternative.',
            'result':'passed','source_hashes':signature,'cases':records}
    (ROOT/'modal32_lutram_prefix_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS vendor LUTRAM prefixes match original final PCM in five scenarios')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyze-only',action='store_true')
    parser.add_argument('--variants-only',action='store_true',help='reuse base single/full/hot simulations for differential cases')
    variant=parser.add_mutually_exclusive_group()
    variant.add_argument('--state-ram-prefix',action='store_true',help='check vendor LUTRAM alternative against baseline output prefixes')
    variant.add_argument('--state-ram-full',action='store_true',help='check full-length vendor LUTRAM spectra, stress and bit exactness')
    args=parser.parse_args()
    if args.state_ram_prefix or args.state_ram_full:lutram_validation(args.state_ram_full);return
    steps,table=inputs()
    if not args.analyze_only:
        cases=[('muted','muted',N),('retuned','retuned',N)]
        tags=['muted','retuned']
        if not args.variants_only:tags+=['base'];cases += [('single','base',N),('full','base',4096),('hot','base',512)]
        for tag in tags:build(tag)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda c:sim(*c),cases))
    analyze(steps,table)

if __name__=='__main__':main()
