"""Measure isolated action-to-audio delay from simultaneous oscilloscope channels.

Pass one CSV per strike. Times in --baseline use the selected CSV time unit;
channel values and thresholds use volts. No instrument or network access.
"""
import argparse
from array import array
from bisect import bisect_left, bisect_right
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import median
import sys


TIME_TO_MS = {'s': 1000.0, 'ms': 1.0, 'us': 0.001, 'ns': 0.000001}
DELIMITERS = {'comma': ',', 'tab': '\t', 'semicolon': ';'}


@dataclass(frozen=True)
class Settings:
    time_column: str
    trigger_column: str
    audio_column: str
    time_unit: str
    baseline: tuple[float, float]
    trigger_threshold: float
    direction: str
    audio_threshold: float
    trigger_points: int
    audio_points: int
    max_delay_ms: float
    delimiter: str


def read_capture(path, settings):
    columns = (settings.time_column, settings.trigger_column, settings.audio_column)
    times, trigger, audio = (array('d') for _ in columns)
    factor = TIME_TO_MS[settings.time_unit]
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source, delimiter=DELIMITERS[settings.delimiter], strict=True)
        # Instruments often put model, acquisition and unit metadata first.
        for header in reader:
            header = [cell.strip() for cell in header]
            if all(name in header for name in columns):
                if any(header.count(name) != 1 for name in columns):
                    raise ValueError('选定列名在表头中不唯一')
                indices = [header.index(name) for name in columns]
                break
        else:
            raise ValueError('找不到包含这些列的表头：' + ', '.join(columns))
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            try:
                t, h, a = (float(row[i]) for i in indices)
            except (IndexError, ValueError) as exc:
                raise ValueError(f'第 {reader.line_num} 行缺值或含非数值字段') from exc
            t *= factor
            if not all(math.isfinite(x) for x in (t, h, a)):
                raise ValueError(f'第 {reader.line_num} 行含 NaN、无穷值或时间溢出')
            if times and t <= times[-1]:
                raise ValueError(f'第 {reader.line_num} 行时间未严格递增')
            if times and not math.isfinite(t-times[0]):
                raise ValueError('记录的时间跨度溢出')
            times.append(t)
            trigger.append(h)
            audio.append(a)
    if len(times) < 4:
        raise ValueError('有效采样点不足')
    return times, trigger, audio


def crossing_runs(values, begin, qualifies, needed):
    """Yield the *first* sample of each run that eventually passes confirmation."""
    count = 0
    for i in range(begin, len(values)):
        count = count + 1 if qualifies(values[i]) else 0
        if count == needed:
            yield i - needed + 1


def measure(path, settings):
    times, trigger, audio = read_capture(path, settings)
    factor = TIME_TO_MS[settings.time_unit]
    start, end = (v * factor for v in settings.baseline)
    if start < times[0] or end > times[-1]:
        raise ValueError('预触发基线窗口超出采集时间范围')
    i, j = bisect_left(times, start), bisect_right(times, end)
    if j - i < 3 or j >= len(times):
        raise ValueError('基线区至少需要 3 点，且后面需要保留动作记录')
    trigger_zero = median(trigger[i:j])
    audio_zero = median(audio[i:j])
    if not math.isfinite(trigger_zero) or not math.isfinite(audio_zero):
        raise ValueError('基线读数溢出')

    def triggered(value):
        displacement = value - trigger_zero
        if settings.direction == 'falling':
            displacement = -displacement
        elif settings.direction == 'either':
            displacement = abs(displacement)
        return displacement >= settings.trigger_threshold

    def sounded(value):
        return abs(value - audio_zero) >= settings.audio_threshold

    if any(triggered(trigger[k]) or sounded(audio[k]) for k in range(i, j)):
        raise ValueError('预触发基线中已有越阈采样，请核对静止基线、噪声和阈值')
    events = crossing_runs(trigger, j, triggered, settings.trigger_points)
    onset = next(events, None)
    if onset is None:
        raise ValueError('CH1 未出现满足方向、阈值及连续点数的动作')
    if next(events, None) is not None:
        raise ValueError('CH1 存在多次动作或阈值回摆，请每次动作单独导出或核对阈值')
    sound = next(crossing_runs(audio, j, sounded, settings.audio_points), None)
    if sound is None:
        raise ValueError('未发现满足阈值和连续确认点数的音频起音')
    if sound < onset:
        raise ValueError('音频已在动作之前越阈，无法归属于本次动作')
    delay = times[sound] - times[onset]
    if delay > settings.max_delay_ms:
        raise ValueError(f'音频在 {delay:.6g} ms 才越阈，超过指定关联窗口')
    # The true crossing lies between the preceding sample and the first sample
    # above threshold. Use each edge's actual local spacing, even for uneven CSVs.
    earliest = times[sound-1] - times[onset]
    latest = times[sound] - times[onset-1]
    return {
        'file': str(path), 'valid': True, 'sample_count': len(times), 'baseline_samples': j-i,
        'trigger_baseline_v': trigger_zero, 'audio_baseline_v': audio_zero,
        'baseline_observed_ms': [times[i],times[j-1]],
        'audio_baseline_peak_deviation_v': max(abs(v-audio_zero) for v in audio[i:j]),
        'trigger_time_ms': times[onset], 'audio_time_ms': times[sound],
        'trigger_edge_ms': [times[onset-1], times[onset]],
        'audio_edge_ms': [times[sound-1], times[sound]],
        'trigger_confirmed_at_ms': times[onset + settings.trigger_points-1],
        'audio_confirmed_at_ms': times[sound + settings.audio_points-1],
        'latency_ms': delay, 'sampling_bounds_ms': [earliest, latest],
        'sampling_uncertainty_minus_ms': delay-earliest,
        'sampling_uncertainty_plus_ms': latest-delay,
        'strict_order_resolved': earliest > 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path, help='one isolated action per CSV')
    parser.add_argument('--time-column', required=True)
    parser.add_argument('--trigger-column', required=True, help='Hall or MARK channel')
    parser.add_argument('--audio-column', required=True, help='audio output channel')
    parser.add_argument('--time-unit', required=True, choices=TIME_TO_MS)
    parser.add_argument('--baseline', required=True, nargs=2, type=float, metavar=('START','END'))
    parser.add_argument('--trigger-threshold-v', required=True, type=float)
    parser.add_argument('--direction', required=True, choices=('rising','falling','either'))
    parser.add_argument('--audio-threshold-v', required=True, type=float)
    parser.add_argument('--trigger-points', type=int, default=1)
    parser.add_argument('--audio-points', required=True, type=int)
    parser.add_argument('--max-delay-ms', type=float, default=50, help='event association window, not the pass threshold')
    parser.add_argument('--delimiter', choices=DELIMITERS, default='comma')
    parser.add_argument('--output', type=Path, help='optional JSON report; never overwrites an input CSV')
    args = parser.parse_args(argv)
    if len({args.time_column,args.trigger_column,args.audio_column}) != 3:
        parser.error('时间列、动作列和音频列必须不同')
    if not all(math.isfinite(v) for v in args.baseline) or args.baseline[0]>=args.baseline[1]:
        parser.error('基线窗口必须是有限数值且 START < END')
    if not all(math.isfinite(v) and v>0 for v in (args.trigger_threshold_v,args.audio_threshold_v,args.max_delay_ms)):
        parser.error('阈值和关联窗口必须是有限正数')
    if min(args.trigger_points,args.audio_points)<1:
        parser.error('连续确认点数必须至少为 1')
    inputs = [p.resolve() for p in args.files]
    if len(set(inputs))!=len(inputs):
        parser.error('同一文件不能重复计入统计')
    if args.output and args.output.resolve() in inputs:
        parser.error('JSON 输出路径不能是输入 CSV')
    settings = Settings(args.time_column,args.trigger_column,args.audio_column,args.time_unit,
                        tuple(args.baseline),args.trigger_threshold_v,args.direction,args.audio_threshold_v,
                        args.trigger_points,args.audio_points,args.max_delay_ms,args.delimiter)
    records=[]
    for path in args.files:
        try:
            records.append(measure(path, settings))
        except (OSError,UnicodeError,csv.Error,ValueError) as exc:
            records.append({'file':str(path),'valid':False,'error':str(exc)})
    valid = [r['latency_ms'] for r in records if r['valid']]
    stats = None
    if valid:
        stats = {'min_ms':min(valid),'median_ms':median(valid),'max_ms':max(valid),
                 'peak_to_peak_ms':max(valid)-min(valid) if len(valid)>=2 else None}
    report = {'settings':vars(settings),'attempted':len(records),'valid_count':len(valid),
              'invalid_count':len(records)-len(valid),'all_captures_valid':len(valid)==len(records),
              'valid_only_statistics':stats,'measurements':records}
    encoded=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        try:
            args.output.write_text(encoded,encoding='utf8')
        except OSError as exc:
            parser.exit(2,f'无法写入 JSON 报告：{exc}\n')
        print(f'有效 {len(valid)}/{len(records)}，报告 {args.output}',file=sys.stderr)
        for record in records:
            if not record['valid']:
                print(f"{record['file']}：{record['error']}",file=sys.stderr)
    else:
        sys.stdout.write(encoded)
    return 0 if report['all_captures_valid'] else 1


if __name__=='__main__':
    sys.exit(main())
