"""Record one manual key strike from the Hotone ASIO inputs, or inspect a prior Ampero recording."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import wave

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'output/latency/audio'
BASELINE = (0.25, 0.75)  # seconds measured on the sound card's own sample clock


def driver():
    os.environ['SD_ENABLE_ASIO'] = '1'
    try:
        import sounddevice as sd
    except ImportError:
        cached = PROJECT.parent / 'tmp/audio_deps'
        if not (cached/'sounddevice.py').is_file():
            raise RuntimeError('请在本 Python 环境安装 sounddevice，并安装 Hotone ASIO 驱动') from None
        sys.path.insert(0, str(cached))
        import sounddevice as sd
    return sd


def interfaces(sd):
    apis = sd.query_hostapis()
    return [(i, dict(d)) for i,d in enumerate(sd.query_devices()) if apis[d['hostapi']]['name']=='ASIO'
            and d['max_input_channels']>=6 and any(n in d['name'].upper() for n in ('HOTONE','AMPERO'))]


def acquire(args):
    sd = driver()
    ports = interfaces(sd)
    if len(ports) != 1:
        raise RuntimeError(f'需要一个在场的 HOTONE/AMPERO ASIO 输入（本次发现 {len(ports)} 个）。请连接其电源和 USB。')
    index, device = ports[0]
    channels = list(dict.fromkeys([5, 6] + ([args.reference_channel] if args.reference_channel else [])))
    if max(channels) > device['max_input_channels']:
        raise ValueError('选定的通道超过当前设备输入通道数')
    fs = int(device['default_samplerate'])
    frames = round(fs*args.seconds)
    settings = sd.AsioSettings(channel_selectors=[ch-1 for ch in channels])
    started = datetime.now(timezone.utc).isoformat()
    print('开始录音，请放开琴键并保持安静。', flush=True)
    with sd.InputStream(device=index, channels=len(channels), extra_settings=settings, dtype='int32',
                        samplerate=fs, blocksize=0, latency='low') as stream:
        # Cue follows actual samples rather than a PC wall clock. Sample timestamps are always relative to the capture.
        prefix, first_overflow = stream.read(fs)
        print('现在按一次琴键，稍作停留后松开。', flush=True)
        rest, second_overflow = stream.read(frames-fs)
    data = np.concatenate((prefix, rest))
    return data, channels, fs, dict(started_utc=started, device=device['name'], sdk='ASIO', cue_after_samples=fs,
                                   input_overflow=bool(first_overflow or second_overflow))


def read_wav(path):
    with wave.open(str(path),'rb') as wav:
        width, ch, fs = wav.getsampwidth(), wav.getnchannels(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width==3:
        b = np.frombuffer(raw, np.uint8).reshape(-1,3).astype(np.int32)
        s = (b[:,0] | b[:,1]<<8 | b[:,2]<<16) << 8
    elif width==2:
        s = np.frombuffer(raw, '<i2').astype(np.int32) << 16
    elif width==4:
        s = np.frombuffer(raw,'<i4')
    else:
        raise ValueError('支持整数 PCM 16、24、32 bit WAV')
    return s.reshape(-1,ch), fs


def display_wave(samples, fs, limit=1800):
    """Preserve block minima and maxima in sample order; return aligned times."""
    indices = {0,len(samples)-1}
    for chunk in np.array_split(np.arange(len(samples)), min(len(samples),limit//2)):
        values = samples[chunk]
        indices.update((int(chunk[values.argmin()]), int(chunk[values.argmax()])))
    indices = np.array(sorted(indices))
    return (indices/fs).tolist(), samples[indices].tolist()


def onset(values, fs, threshold_db):
    start,end = (round(t*fs) for t in BASELINE)
    base = values[start:end]
    center = float(np.median(base))
    delta = np.abs(values-center)
    floor = float(np.max(delta[start:end]))
    threshold = (10**(threshold_db/20) if threshold_db is not None else
                 max(10**(-90/20), 8*np.sqrt(np.mean(delta[start:end]**2)), 1.5*floor))
    result = dict(time_s=None, sample=None, baseline_peak_fs=floor, threshold_fs=float(threshold),
                  threshold_dbfs=20*math.log10(threshold), confirmation_samples=3)
    if floor>=threshold:
        return result | dict(reason='预触发基线已越过阈值')
    mask = delta[end:] >= threshold
    hits = np.flatnonzero(mask[:-2] & mask[1:-1] & mask[2:])
    if not len(hits):
        return result | dict(reason='未发现连续三点越阈')
    i = end+int(hits[0])
    if i<fs:
        return result | dict(reason='在按键提示前已出现音频或参考信号')
    return result | dict(sample=i, time_s=i/fs, reason=None)


def write_record(args):
    history = args.command == 'history'
    if history:
        source = args.wav.resolve()
        sidecar = args.metadata.resolve()
        original = json.loads(sidecar.read_text(encoding='utf8'))
        channels = original['channels_one_based']
        if 'HOTONE' not in original['device']['name'].upper() or channels != [5,6]:
            raise ValueError('档案 metadata 必须确认 HOTONE ASIO 5/6')
        data, fs = read_wav(source)
        if data.shape[1]!=len(channels) or fs!=original['sample_rate'] or abs(len(data)/fs-original['seconds'])>1/fs:
            raise ValueError('原 WAV 的采样率、时长或通道与元数据不符')
        details = dict(source_path=str(source), metadata_path=str(sidecar), device=original['device']['name'],
                       original_label=original['label'], started_utc=original.get('started_utc'),
                       stream_errors=original.get('stream_errors', []), input_overflow=bool(original.get('stream_errors')))
        ref = None
    else:
        ref = args.reference_channel
        data, channels, fs, details = acquire(args)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    dest = OUT / (('history_' if history else 'ampero_')+stamp)
    dest.mkdir(parents=True, exist_ok=False)
    wav_path = dest/'raw.wav'
    if history:
        shutil.copyfile(source, wav_path)
        shutil.copyfile(sidecar, dest/'original_metadata.json')
    else:
        with wave.open(str(wav_path),'wb') as wav:
            wav.setnchannels(len(channels)); wav.setsampwidth(4); wav.setframerate(fs)
            wav.writeframes(data.astype('<i4',copy=False).tobytes())
    samples = data.astype(float)/2147483648
    signal = samples[:,channels.index(args.audio_channel)]
    desc = '历史 Ampero 录音 · 非本次试验' if history else '本次 Ampero ASIO 录音'
    signal_peak = float(np.max(np.abs(signal)))
    times, preview = display_wave(signal,fs)
    record = dict(source_kind='historical_ampero' if history else 'live_ampero',
                  mode='pair' if ref else 'audio_only', source=desc,
                  fs=fs, sample_count=len(data), channels=channels, audio_channel=args.audio_channel,
                  reference_channel=ref, reference_label=getattr(args,'reference_label',None),
                  capture=details, raw_wav=wav_path.name, wav_sha256=hashlib.sha256(wav_path.read_bytes()).hexdigest(),
                  timeseries='samples.csv', baseline_s=None if history else BASELINE, latency_ms=None,
                  display=dict(name=args.name, source=desc, channel=f'ASIO {args.audio_channel} · Tang 耳机输出',
                               fs=fs, time_s=times, samples=preview, duration_s=len(data)/fs,
                               peak_dbfs=20*math.log10(signal_peak) if signal_peak else None))
    with (dest/'samples.csv').open('w',encoding='utf8',newline='') as file:
        writer=csv.writer(file)
        writer.writerow(['time_s', *[f'ASIO_{ch}_FS' for ch in channels]])
        writer.writerows((f'{i/fs:.9f}', *(f'{v:.10g}' for v in row)) for i,row in enumerate(samples))
    if history:
        reason='历史 WAV 只展示声卡录音。没有与本次动作同步采集的参考。'
        record['onset']=None
        record['valid']=not details['input_overflow']
    else:
        measured=onset(signal,fs,args.audio_threshold_dbfs)
        record['onset']=measured
        reason=measured['reason']
        if ref is not None:
            reference=onset(samples[:,channels.index(ref)],fs,args.reference_threshold_dbfs)
            record['reference_onset']=reference
            reason=reason or reference['reason']
            if not reason:
                delay=(measured['sample']-reference['sample'])*1000/fs
                if not 0<=delay<=args.max_delay_ms:
                    reason='两个起点的顺序或间隔无法与同一次动作匹配'
                else:
                    record.update(latency_ms=delay, sampling_bounds_ms=[delay-1000/fs,delay+1000/fs])
        used = [args.audio_channel] + ([ref] if ref else [])
        if details['input_overflow'] or any(np.max(np.abs(samples[:,channels.index(ch)]))>=0.999 for ch in used):
            reason='输入溢出或接近满幅，请降低模拟增益／排除丢帧后重新采集'
            record['latency_ms']=None
            record.pop('sampling_bounds_ms', None)
        record['valid']=not reason
        if not reason and not ref:
            reason='只测得录音内的音频起点。没有同时采集的动作参考。'
    record['note']=reason or '差值相对于指定的模拟动作参考，仅含取样间隔界限。'
    temporary=dest/'record.tmp'
    with temporary.open('x',encoding='utf8') as file:
        json.dump(record,file,ensure_ascii=False,allow_nan=False)
    temporary.replace(dest/'record.json')
    print(dest/'record.json',flush=True)
    return 0 if record['valid'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    subs.add_parser('devices',help='只列出可用的 Hotone ASIO 输入')
    take=subs.add_parser('record',help='放开键保留约一秒基线，按提示只击键一次')
    take.add_argument('--seconds',type=float,default=5)
    take.add_argument('--reference-channel',type=int,help='同一设备上专门接独立模拟动作传感器的通道')
    take.add_argument('--reference-label',help='例如“接触麦克风触键脉冲”')
    take.add_argument('--audio-threshold-dbfs',type=float)
    take.add_argument('--reference-threshold-dbfs',type=float)
    take.add_argument('--max-delay-ms',type=float,default=50)
    prior=subs.add_parser('history',help='导入带原始 Ampero ASIO 5/6 元数据的历史 WAV')
    prior.add_argument('wav',type=Path); prior.add_argument('metadata',type=Path)
    for sub in (take,prior):
        sub.add_argument('--name',default='Ampero 耳机口录音')
        sub.add_argument('--audio-channel',type=int,default=5,choices=(5,6))
    args=parser.parse_args()
    if args.command=='devices':
        found=interfaces(driver())
        print(json.dumps([dict(index=i,name=d['name'],inputs=d['max_input_channels'],
                               default_sample_rate=d['default_samplerate']) for i,d in found],ensure_ascii=False))
        return 0 if found else 1
    if args.command=='record':
        if not 2<=args.seconds<=60 or not 0<args.max_delay_ms<=1000:
            parser.error('录音时长应为2至60秒，最大关联窗口应为0至1000毫秒')
        if args.reference_channel==args.audio_channel or bool(args.reference_label)!=bool(args.reference_channel):
            parser.error('成对测试需要不同于音频的动作通道和说明；立体声左右声道不能彼此当作动作参考')
        if args.reference_channel is not None and not 1<=args.reference_channel<=8:
            parser.error('参考通道须为 1..8')
        for threshold in (args.audio_threshold_dbfs,args.reference_threshold_dbfs):
            if threshold is not None and not -120<=threshold<=0:
                parser.error('门限有效范围为 −120 至 0 dBFS')
    return write_record(args)


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(2)
