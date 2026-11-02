"""Local instrument evidence for the Tang latency display."""
import hashlib
import html
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from urllib.parse import urlsplit

from audio_web import send

ROOT = Path(__file__).resolve().parents[2]
HOST = Path(__file__).resolve().parent
STORE = ROOT / 'output' / 'latency'
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'realtime_synth' / 'control_meter_l8'))
from analyze_onset_csv import Settings, TIME_TO_MS, measure_samples, read_capture

SEGMENTS = {'mark-headphone': 'FPGA 接受琴键 → 耳机口模拟起音',
            'hall-headphone': '霍尔越阈 → 耳机口模拟起音',
            'hall-mark': '霍尔越阈 → FPGA 接受琴键'}
UPLOAD_LIMIT = 24 * 1024 * 1024


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf8') as temp:
        json.dump(data, temp, ensure_ascii=False, allow_nan=False)
    Path(temp.name).replace(path)


def result_list(store=STORE):
    archived = json.loads((ROOT/'tests/contest_board/onset_board.json').read_text(encoding='utf8'))
    digital = [dict(name='已归档的单键实测', key=archived['key'], version=archived['code'],
                    us=archived['value'], count=1, sequence=archived['after']['measurements'],
                    source='完整版 · 实板 · 单次 H15 按下和松开，各 1 次')]
    scope = []
    audio = []
    for part, target in [('digital', digital), ('scope', scope), ('audio', audio)]:
        for path in sorted((store/part).glob('*/record.json')):
            data = json.loads(path.read_text(encoding='utf8'))
            if part=='audio':
                view = dict(data['display'])
                wav = Path(data['raw_wav']).name
                if (path.parent/wav).is_file():
                    view['wav_url'] = '/api/latency/wav/'+path.parent.name
                view['kind'] = data.get('source_kind','')
                target.append(view)
            else:
                target.append(data)
    return dict(digital=digital, scope=scope, audio=audio)


def import_marker(form, raw, store):
    unit=form['time_unit']
    time_col, signal_col=form['time_column'].strip(),form['trigger_column'].strip()
    thresh=float(form['trigger_threshold'])
    if unit not in TIME_TO_MS or not math.isfinite(thresh) or not 0<thresh<3.3 or time_col==signal_col:
        raise ValueError('请选择不同的时间/CH1 列、有效单位和 0 到 3.3 V 之间的逻辑门限')
    rows=csv.reader(io.StringIO(raw.decode('utf-8-sig')),strict=True)
    for header in rows:
        header=[s.strip() for s in header]
        if header.count(time_col)==header.count(signal_col)==1:break
    else:raise ValueError('找不到唯一的时间列和 MARK 列')
    ti,si=header.index(time_col),header.index(signal_col)
    times,signal=[],[]
    for row in rows:
        if not row or all(not v.strip() for v in row):continue
        if len(row)<=max(ti,si):raise ValueError('CSV 采样行缺少列')
        t,s=float(row[ti])*TIME_TO_MS[unit],float(row[si])
        if not math.isfinite(t) or not math.isfinite(s) or times and t<=times[-1]:
            raise ValueError('采样时间或电压无效')
        times.append(t)
        signal.append(s)
    if len(times)<4 or signal[0]>=thresh or signal[-1]>=thresh:
        raise ValueError('应包含 MARK 上升前和下降后的低电平')
    edges=[i for i in range(1,len(times)) if (signal[i]>=thresh)!=(signal[i-1]>=thresh)]
    if len(edges)!=2 or edges[1]-edges[0]<2:
        raise ValueError('需一次完整的 MARK 高脉冲。请核对 LIVE 页、接线、触发和采样率')
    rise,fall=edges
    t0,t1=times[rise],times[fall]
    key=hashlib.sha256(raw).hexdigest()
    ident=hashlib.sha256(json.dumps([key,unit,thresh,time_col,signal_col]).encode()).hexdigest()
    folder=store/'digital'/ident
    folder.mkdir(parents=True,exist_ok=True)
    keep=set(range(0,len(times),max(1,len(times)//1200)))|{0,len(times)-1,rise-1,rise,fall-1,fall}
    ix=sorted(keep)
    record=dict(name=str(form.get('name') or '示波器 MARK 高脉宽')[:100],count=1,
                key=str(form.get('key') or '未标注琴键')[:40],version=str(form.get('version') or '未标注码流')[:64],
                source='示波器 CH1 · J8-10 MARK 高脉宽',segment='mark-i2s',sequence=form.get('sequence'),
                us=(t1-t0)*1000, bounds_us=[1000*(times[fall-1]-t0),1000*(t1-times[rise-1])],
                t0_ms=t0,t1_ms=t1,time_ms=[times[i] for i in ix],trigger_v=[signal[i] for i in ix],
                csv_sha256=key,raw_url='/api/latency/mark/'+ident,threshold_v=thresh)
    (folder/'capture.csv').write_bytes(raw)
    write_json(folder/'record.json',record)
    return record


def scope_upload(form, store=STORE):
    if not isinstance(form.get('csv'),str):
        raise ValueError('需要 UTF-8 CSV 文本')
    raw = form['csv'].encode('utf-8')
    if not raw or len(raw)>UPLOAD_LIMIT:raise ValueError('请选择不超过 24 MiB 的 CSV')
    segment = form['segment']
    if segment=='mark-i2s':return import_marker(form,raw,store)
    if segment not in SEGMENTS:raise ValueError('请选择测量的起点与终点')
    cols = [str(form[n]).strip() for n in ('time_column','trigger_column','audio_column')]
    if len(set(cols))!=3 or not all(cols):raise ValueError('请选择三个不同的列')
    unit = form['time_unit']
    direction = form['direction']
    if unit not in TIME_TO_MS or direction not in ('falling','rising','either'):
        raise ValueError('时间单位或边沿方向无效')
    start, end, trigger, audio = [float(form[n]) for n in ('baseline_from','baseline_to','trigger_threshold','audio_threshold')]
    if not all(map(math.isfinite,(start,end,trigger,audio))) or start>=end or min(trigger,audio)<=0:
        raise ValueError('基线起点须小于终点，两个阈值须为正数')
    confirmations = [int(form.get(n,d)) for n,d in [('trigger_points',1),('audio_points',3)]]
    if not all(1<=v<=10000 for v in confirmations):raise ValueError('连续确认点数须在 1 到 10000 之间')
    settings = Settings(*cols,unit,(start,end),trigger,direction,audio,*confirmations,50,'comma')
    condition = str(form.get('condition','')).strip()[:160]
    digest = hashlib.sha256(raw).hexdigest()
    identity = json.dumps([digest,vars(settings),segment,condition],sort_keys=True)
    key = hashlib.sha256(identity.encode()).hexdigest()
    output = store/'scope'/key
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output,delete=False) as temp:
        temp.write(raw)
    path = Path(temp.name)
    try:
        times, ch1, ch2 = read_capture(path, settings)
        measured = measure_samples(path, settings, times,ch1,ch2)
        t0,t1=measured['trigger_time_ms'],measured['audio_time_ms']
        # Retain excursions in both analog channels, even when a MARK pulse is narrow.
        keep={0,len(times)-1,times.index(t0),times.index(t1)}
        stride=max(1,(len(times)+499)//500)
        for offset in range(0,len(times),stride):
            group=range(offset,min(len(times),offset+stride))
            for values in (ch1,ch2):
                keep.update((min(group,key=values.__getitem__),max(group,key=values.__getitem__)))
        idx=sorted(keep)
        measured.pop('file')
        result=dict(name=str(form.get('name') or '单次触键')[:100], segment=segment, endpoints=SEGMENTS[segment],
                    delay_ms=measured['latency_ms'],t0_ms=t0,t1_ms=t1,bounds_ms=measured['sampling_bounds_ms'],
                    time_ms=[times[i] for i in idx],trigger_v=[ch1[i] for i in idx],audio_v=[ch2[i] for i in idx],
                    source='导入的同步双通道 CSV · 按操作者标注的接线',csv_sha256=digest,condition=condition,
                    settings=vars(settings),measurement=measured,raw_url='/api/latency/csv/'+key)
        path.replace(output/'capture.csv')
        write_json(output/'record.json',result)
        return result
    finally:path.unlink(missing_ok=True)


def jtag_code():
    from load_guide_sram import PROGRAMMER
    def run(args):
        proc=subprocess.run([str(PROGRAMMER),*args],capture_output=True,timeout=10,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        proc.check_returncode()
        return proc.stdout.decode(errors='replace')
    try:
        locs=re.findall(r'USB Debugger A/0/(\d+)/',run(['--scan-cables','F']))
        if len(locs)!=1:return None
        out=run(['--device','GW5AT-60B','--cable-index','4','--location',locs[0],'--run','0'])
        if not re.search(r'ID Code is:\s*0x0001481B\b',out,re.I):return None
        match=re.search(r'User Code is:\s*(0x[0-9A-Fa-f]+)',out)
        return match[1] if match else None
    except (OSError,subprocess.SubprocessError):return None


def board_read(controller, store=STORE):
    from verify_board import Board
    code=jtag_code()
    with controller.lock:
        handle=None
        try:
            if controller.transport:
                call=controller.exchange
            else:
                handle=Board(os.environ.get('TANG_LATENCY_PORT','com:COM6'))
                call=handle.call
            stamp=call(34)
            if not stamp['onset_valid']:
                raise ValueError('还没有已完成的计时。先预热，从 LIVE 弹一个孤立音，再读取。')
        finally:
            if handle:handle.device.close()
    row=dict(name='板内最近一次完整起音',key='H'+str(stamp['measured_key']+1),
             version=code or 'v'+str(stamp['firmware'])+'（未核实 User Code）', count=1, us=stamp['onset_us'],
             sequence=stamp['measurements'],source='实板 UART 读取 LAST I2S，计时使用 FPGA 时钟',
             physical_ons=stamp['physical_ons'],physical_offs=stamp['physical_offs'])
    ident=hashlib.sha256(json.dumps([row[k] for k in ('version','sequence','key','us')]).encode()).hexdigest()
    path=store/'digital'/ident/'record.json'
    if not path.exists():
        for file in (store/'digital').glob('*/record.json'):
            earlier=json.loads(file.read_text(encoding='utf8'))
            if earlier.get('source')==row['source'] and all(earlier.get(k)==row[k] for k in ('version','sequence','key','us')):
                return earlier
        row['read_at']=datetime.now().astimezone().isoformat(timespec='seconds')
        write_json(path,row)
    return json.loads(path.read_text(encoding='utf8'))


def serve_get(handler, token):
    url=urlsplit(handler.path).path
    files={'/latency-monitor':('latency-monitor.html','text/html'),'/latency-monitor.js':('latency-monitor.js','text/javascript'),
           '/latency-monitor.css':('latency-monitor.css','text/css')}
    if url in files:
        name,mime=files[url]
        send(handler,(HOST/name).read_text(encoding='utf8').replace('__TOKEN__',token).encode(),mime+'; charset=utf-8')
    elif url=='/latency-wiring':
        guide=html.escape((ROOT/'延迟测试接线.md').read_text(encoding='utf8'))
        page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>延迟测量接线</title><style>body{max-width:65rem;margin:2rem auto;padding:0 1rem;color:#132436}pre{font:16px/1.65 system-ui;white-space:pre-wrap}</style><a href="/latency-monitor">返回测量结果</a><pre>'+guide+'</pre></html>'
        send(handler,page.encode(),'text/html; charset=utf-8')
    elif url=='/api/latency/results':
        if not handler.authorized():handler.send({'error':'forbidden'},403)
        else:handler.send(result_list())
    elif url.startswith(('/api/latency/csv/','/api/latency/wav/','/api/latency/mark/')):
        match=re.fullmatch(r'/api/latency/(csv|wav|mark)/([A-Za-z0-9_-]{1,128})',url)
        if not match:
            handler.send({'error':'无此记录'},404);return True
        kind,key=match.groups()
        folder=STORE/{'wav':'audio','csv':'scope','mark':'digital'}[kind]/key
        if not (folder/'record.json').is_file():
            handler.send({'error':'无此记录'},404);return True
        filename='capture.csv' if kind!='wav' else Path(json.loads((folder/'record.json').read_text(encoding='utf8'))['raw_wav']).name
        if not (folder/filename).is_file():handler.send({'error':'原始文件不可用'},404)
        else:send(handler,(folder/filename).read_bytes(),'audio/wav' if kind=='wav' else 'text/csv; charset=utf-8')
    else:return False
    return True


def serve_post(handler,controller):
    if handler.path not in ('/api/latency/read-board','/api/latency/scope-csv'):return False
    if not handler.authorized():
        handler.send({'error':'forbidden'},403);return True
    try:
        size=int(handler.headers.get('Content-Length','0'))
        if not 0<size<=UPLOAD_LIMIT+1024*1024:raise ValueError('文件太大或请求为空')
        data=json.loads(handler.rfile.read(size))
        if not isinstance(data,dict):raise ValueError('请求格式无效')
        handler.send(board_read(controller) if handler.path.endswith('read-board') else scope_upload(data))
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,csv.Error) as exc:handler.send({'error':str(exc)},400)
    return True
