"""Capture one physical H15 strike using an already configured, edge-triggered TBS2000B."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from latency_web import STORE, import_marker, jtag_code, scope_upload, write_json
from verify_board import Board


def capture(args):
    run=Path.home()/'.codex/skills/control-tektronix-tbs2000b/scripts/run.ps1'
    if not run.exists():raise RuntimeError('需要本机 TBS2000B 示波器控制技能的 run.ps1')
    out=STORE/'acquisitions'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True)
    csv_path=out/'scope.csv'
    ps=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(run)]
    scope=json.loads(subprocess.check_output([*ps,'status'],encoding='utf8'))
    trigger=scope['trigger']
    if trigger['source']!='CH1' or trigger['mode']!='NORMAL' or trigger['slope']!='RISE':
        raise ValueError('请先设置 CH1 上升沿、Normal 触发')
    channels=['1'] if args.audio_threshold_v is None else ['1','2']
    if any(not scope['channels'][int(c)-1]['displayed'] for c in channels):
        raise ValueError('请先启用要采集的通道')
    code=jtag_code()
    if not code:raise ValueError('未读到 Tang 的 JTAG User Code')
    write_json(out/'setup.json',dict(scope=scope,code=code))
    board=Board()
    try:
        before=board.call(34)
        key=board.call(9)
        amp=board.call(4)
        if not (before['monitor'] and before['demo']==0 and amp['amp_ready'] and not amp['active']
                and key['mode']==2 and key['calibrated'] and not key['fault'] and not key['pressed_mask']):
            raise ValueError('需要 32 键校准、功放就绪、LIVE 页且只有静音基线')
        print('Waiting for one physical C4. Scope data:',out,flush=True)
        subprocess.run([*ps,'capture','--channels',*channels,'--single','--single-timeout-s',str(args.seconds),
                        '--max-points','0','--output',str(csv_path)],check=True,timeout=args.seconds+45)
        limit=time.monotonic()+8
        while True:
            after=board.call(34)
            if after['physical_offs']!=before['physical_offs'] or time.monotonic()>limit:break
            time.sleep(.08)
        write_json(out/'board.json',dict(before=before,after=after))
        changes=[(after[name]-before[name])%mod for name,mod in
                 [('physical_ons',1<<24),('physical_offs',1<<24),('measurements',1<<16)]]
        if changes!=[1,1,1] or not after['onset_valid'] or after['measured_key']!=14:
            raise ValueError(f'该波形未关联到一次孤立的 H15 按下及松开：计数差 {changes}，原始采集已保留')
    finally:board.device.close()
    raw=csv_path.read_bytes()
    form=dict(name='H15 / C4 · 示波器与板内同次对照',time_column='time_s',trigger_column='ch1_v',
              time_unit='s',trigger_threshold=trigger['level_v'],key='H15 / C4',version=code,
              sequence=after['measurements'])
    # Check the independent width before publishing a trace as a paired trial.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(dir=out) as temp:
        preview=import_marker(form,raw,Path(temp))
    sampling_us=1e6/float(scope['horizontal']['sample_rate_sps'])
    transfer=json.loads(csv_path.with_suffix('.json').read_text(encoding='utf8'))
    ch1=transfer['channels'][0]
    top=(127-ch1['y_offset_levels'])*ch1['y_multiplier_v_per_level']+ch1['y_zero_v']
    quality=''
    if max(preview['trigger_v'])>=top-.5*ch1['y_multiplier_v_per_level']:
        quality='CH1 高平台到达采集量程上沿。此记录用于门限交越脉宽，高电平幅值未测准。'
    difference=abs(preview['us']-after['onset_us'])
    if difference>1.1+2*sampling_us:
        raise ValueError(f'MARK {preview["us"]:.3f} µs 与板内 {after["onset_us"]} µs 不一致，原始采集已保留')
    marker=import_marker(form,raw,STORE)
    if quality:
        marker['quality_note']=quality
        write_json(STORE/'digital'/marker['raw_url'].split('/')[-1]/'record.json',marker)
    write_json(out/'agreement.json',dict(code=code,key='H15',board_us=after['onset_us'],scope_us=marker['us'],
                                         sample_period_us=sampling_us,measurement_count=after['measurements'],
                                         quality_note=quality))
    print('PASS MARK %.3f us, LAST I2S %d us, sample period %.3f us'%(marker['us'],after['onset_us'],sampling_us))
    if args.audio_threshold_v is not None:
        with csv_path.open(encoding='utf8') as f:first=float(next(csv.DictReader(f))['time_s'])
        start=marker['t0_ms']/1000
        form.update(segment='mark-headphone',name='H15 / C4 · MARK 至 J25',csv=raw.decode('utf8'),
                    audio_column='ch2_v',baseline_from=first,baseline_to=(first+start)/2,
                    audio_threshold=args.audio_threshold_v,direction='rising',condition=args.condition)
        result=scope_upload(form)
        print('MARK to J25 threshold onset: %.6f ms'%result['delay_ms'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=150)
    parser.add_argument('--audio-threshold-v',type=float,help='If supplied, collect CH2 connected to J25 tip')
    parser.add_argument('--condition',default='',help='Timbre, level, FX and output load for a paired trial')
    args=parser.parse_args()
    if not 1<=args.seconds<=900:parser.error('等待时间须为 1～900 秒')
    capture(args)
