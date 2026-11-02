"""Publish qualified, same-acquisition U1 fixed-key and amplifier-leg measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from statistics import median
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from latency_web import STORE, write_json
from analyze_onset_csv import Settings, measure_samples

SEGMENT='fixed-adc-speaker-leg'
ENDPOINTS='固定 H15 · U1 ADC_OUT 越阈 → 喇叭功放单端起音'


def publish(folder, label, criteria, config):
    raw=folder/(label+'.csv')
    assoc=json.loads((folder/(label+'_association.json')).read_text())
    capture=json.loads((folder/(label+'.json')).read_text())
    assert assoc['delta']==[1,1,1] and assoc['after']['onset_valid'] and assoc['after']['measured_key']==14
    a=np.genfromtxt(raw,delimiter=',',names=True)
    dt=capture['channels'][0]['x_increment_s']
    assert len(a)==capture['record_length'] and np.allclose(np.diff(a['time_s']),dt,rtol=1e-6,atol=1e-13)
    assert capture['channels'][1]['x_increment_s']==dt and capture['channels'][1]['x_zero_s']==capture['channels'][0]['x_zero_s']
    window=round(40.96e-6/dt)
    confirm=round(criteria['confirm_us']*1e-6/dt)
    weights=np.ones(window)/window
    times=a['time_s'][window-1:]*1000
    hall=np.convolve(a['ch1_v'],weights,mode='valid')
    output=np.convolve(a['ch2_v'],weights,mode='valid')
    cutoff=criteria['falling_threshold_v']
    audio_cutoff=criteria['speaker_deviation_v']
    def measure(quiet_start_ms,quiet_end_ms,audio_v,hall_cutoff=cutoff):
        base=(times[0]+quiet_start_ms,times[0]+quiet_end_ms)
        hall_zero=float(np.median(hall[(times>=base[0])&(times<=base[1])]))
        settings=Settings('time_s','ch1_v','ch2_v','ms',base,hall_zero-hall_cutoff,'falling',
                          audio_v,confirm,confirm,50,'comma')
        result=measure_samples(raw,settings,times,hall,output)
        result['strict_order_resolved']=bool(result['strict_order_resolved'])
        return result
    result=measure(.1,5,audio_cutoff)
    result.pop('file')
    t0,t1=result['trigger_time_ms'],result['audio_time_ms']
    if t0<times[0]+15 or t1+16>times[-1]:
        raise ValueError('记录中缺少完整的音前参考或音后的持续波形')
    alt_base=measure(.1,20,audio_cutoff)['latency_ms']
    sensitivity={str(v):measure(.1,5,v)['latency_ms'] for v in (.0075,.010,.015)}
    # Verify the output includes the musical note, independently of detection.
    fit=(times>=t1)&(times<t1+4*1000/261.6256)
    phase=2*np.pi*261.6256*times[fit]/1000
    terms=[np.ones(len(phase)),*[fn(h*phase) for h in range(1,6) for fn in (np.sin,np.cos)]]
    design=np.column_stack(terms)
    fitted=design@np.linalg.lstsq(design,output[fit],rcond=None)[0]
    fraction=1-float(np.sum((output[fit]-fitted)**2)/np.sum((output[fit]-np.mean(output[fit]))**2))
    if fraction<.8:raise ValueError('CH2 未能确认 C4 基频及其谐波')
    keep={0,len(times)-1,int(np.searchsorted(times,t0)),int(np.searchsorted(times,t1))}
    for g in np.array_split(np.arange(len(times)),600):
        for v in (hall,output):keep.update((int(g[np.argmin(v[g])]),int(g[np.argmax(v[g])])))
    ix=np.array(sorted(keep))
    digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    dest=STORE/'scope'/digest
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(raw,dest/'capture.csv')
    settings=dict(time_column='time_s',trigger_column='ch1_v',audio_column='ch2_v',time_unit='ms',
                  baseline=[round(times[0]+.1,6),round(times[0]+5,6)],direction='falling',
                  trigger_reference='absolute',trigger_threshold=cutoff,audio_threshold=audio_cutoff,
                  trigger_points=confirm,audio_points=confirm,smoothing_samples=window)
    original=assoc['after']
    condition=f'H15 固定单通道 · 敲击钢琴 {config["display"]["volume"]}% · 功放预热 · 双路 1× · {window} 点尾随平均'
    trial=dict(name=f'H15 / C4 · 击键 {label[-2:]}',segment=SEGMENT,endpoints=ENDPOINTS,
               source='TBS2202B 同次 CH1/CH2。图中两路均作等长尾随平均，CSV 为原始未滤波示值。',
               condition=condition,settings=settings,delay_ms=result['latency_ms'],t0_ms=t0,t1_ms=t1,
               bounds_ms=result['sampling_bounds_ms'],measurement=result,raw_url='/api/latency/csv/'+digest,
               time_ms=times[ix].tolist(),trigger_v=hall[ix].tolist(),audio_v=output[ix].tolist(),
               csv_sha256=digest,raw_samples=len(a),sequence=original['measurements'],board_us=original['onset_us'],
               c4_harmonic_fit_fraction=fraction,alternate_baseline_ms=alt_base,sensitivity_ms=sensitivity)
    write_json(dest/'record.json',trial)
    summary={k:trial[k] for k in ('name','delay_ms','csv_sha256','sequence','board_us','c4_harmonic_fit_fraction','alternate_baseline_ms','sensitivity_ms')}
    summary['capture']=label
    # The midpoint illustrates an earlier electrical start; it does not replace the gate criterion.
    sensitivity_levels=(0.140,cutoff,0.160,(criteria['idle_v']+criteria['held_v'])/2)
    summary['hall_threshold_checks']=[]
    for voltage in sensitivity_levels:
        try:
            check=measure(.1,5,audio_cutoff,voltage)
            entry={'threshold_v':voltage,'delay_ms':check['latency_ms']}
        except ValueError as exc:
            entry={'threshold_v':voltage,'reason':str(exc)}
        summary['hall_threshold_checks'].append(entry)
    return summary


def report(folder, labels):
    criteria=json.loads((folder/'criteria.json').read_text())
    config=json.loads((folder/'fixed_config.json').read_text())
    trials=[publish(folder,label,criteria,config) for label in labels]
    assert len({r['csv_sha256'] for r in trials})==len(trials)
    values=[r['delay_ms'] for r in trials]
    summary=dict(segment=SEGMENT,criteria=criteria,trials=trials,count=len(trials),
                 min_ms=min(values),median_ms=median(values),max_ms=max(values),span_ms=max(values)-min(values),
                 note='Fixed H15 single ADC channel; speaker single-leg vs board GND. Not an ordinary 32-key scan or acoustic measurement.')
    write_json(folder/'speaker_summary.json',summary)
    print(json.dumps(summary,indent=2,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('labels',nargs='+')
    args=parser.parse_args()
    report(args.folder.resolve(),args.labels)
