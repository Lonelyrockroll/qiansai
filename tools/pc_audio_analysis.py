"""PC snapshot analyzer for Tang's final mono PCM, with a separate capture-safe board path."""
import argparse
import csv
import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import time
import zlib

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from protocol import FS,PCM_CONTROL,PCM_STATUS
from pcm_tools import read_frozen,reference_pcm

DELAY=16
LIMIT=32768
FLOOR_DBFS=-120.0


def analyze(raw,rate,relative_db=40):
    if len(raw)%2 or not DELAY< len(raw)//2 <=LIMIT:
        raise ValueError('请选择单段 17～32768 点的 16 位小端单声道 PCM 文件')
    if not math.isfinite(rate) or rate<=0 or not math.isfinite(relative_db) or not 0<relative_db<=120:
        raise ValueError('采样率须为正有限数，峰阈值须在 (0,120] dB 范围内')
    samples=np.frombuffer(raw,dtype='<i2').astype(np.float64)
    n=len(samples);window=np.hanning(n)
    shape=np.abs(np.fft.rfft((samples-samples.mean())*window))/window.sum();amplitudes=shape.copy()
    # One-sided peak-amplitude spectrum. DC and even-N Nyquist have no mirror counterpart.
    amplitudes[1:(-1 if n%2==0 else None)]*=2
    hz=np.fft.rfftfreq(n,1/rate)
    cutoff=max(1.0,float(amplitudes[1:].max())*10**(-relative_db/20))
    peaks=np.flatnonzero((shape[1:-1]>shape[:-2])&(shape[1:-1]>=shape[2:]))+1
    if shape[-1]>shape[-2]:peaks=np.append(peaks,len(amplitudes)-1)
    peaks=peaks[amplitudes[peaks]>=cutoff]
    with np.errstate(divide='ignore'):
        levels=20*np.log10(amplitudes/32768)
    meta=dict(sample_rate_hz=rate,samples=n,duration_ms=1000*n/rate,nyquist_hz=rate/2,
              fft_points=n,bin_spacing_hz=rate/n,window='symmetric Hann; mean removed before FFT',
              unit='one-sided peak amplitude dBFS; full scale = 32768 PCM codes',
              peak_rule=f'positive-frequency local maxima at least 1 PCM code and within {relative_db:g} dB of strongest non-DC bin',
              cutoff_pcm=cutoff,peak_count=len(peaks),peak_bins=peaks.tolist(),display_floor_dbfs=FLOOR_DBFS,
              mean_pcm=float(samples.mean()),peak_abs_pcm=int(np.max(np.abs(samples))),
              rms_pcm=float(np.sqrt(np.mean(samples*samples))),xy_delay_samples=DELAY,xy_delay_ms=1000*DELAY/rate,
              crc32=f'{zlib.crc32(raw):08X}',sha256=hashlib.sha256(raw).hexdigest())
    return samples,hz,amplitudes,levels,peaks,meta


def plot(folder,label,result,focus_hz):
    from PIL import Image, ImageDraw, ImageFont
    samples,hz,_,levels,peaks,m=result;rate=m['sample_rate_hz']
    image=Image.new('RGB',(1640,1030),'#f4f7f4');draw=ImageDraw.Draw(image)
    zh=Path('C:/Windows/Fonts/msyh.ttc');latin=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font_path=zh if zh.is_file() else latin
    def font(size):
        return ImageFont.truetype(str(font_path),size) if font_path.is_file() else ImageFont.load_default(size=size)
    ink='#183942';muted='#4e656c';grid='#dae4df';wave='#187970';blue='#386798';orange='#c26b49'
    def txt(x,y,value,size=17,colour=muted,anchor='la'):
        draw.text((x,y),str(value),font=font(size),fill=colour,anchor=anchor)
    def title(cn,en):return cn if zh.is_file() else en
    txt(80,24,title('电脑音频观察','PC PCM analysis')+'  /  '+label[:64],35,ink)
    txt(80,84,f"{rate:.3f} Hz  |  {len(samples):,} samples  |  {m['duration_ms']:.2f} ms  |  Hann  |  FFT Δf {m['bin_spacing_hz']:.3f} Hz  |  {len(peaks)} peaks",21)
    def axes(box,x_range,y_range,x_name,y_name,caption):
        left,top,right,bottom=box;lo,hi=x_range;low,high=y_range
        def x(v):return left+(right-left)*(v-lo)/(hi-lo)
        def y(v):return bottom-(bottom-top)*(np.clip(v,low,high)-low)/(high-low)
        txt(left,top-45,caption,22,ink);draw.rectangle(box,fill='white',outline=grid)
        for a in np.linspace(lo,hi,5):
            px=x(a);draw.line((px,top,px,bottom),fill=grid);txt(px,bottom+12,f'{a:.1f}' if hi-lo<120 else f'{a:.0f}',15,anchor='mt')
        for b in np.linspace(low,high,5):
            py=y(b);draw.line((left,py,right,py),fill=grid);txt(left-8,py,f'{b:.0f}',15,anchor='rm')
        txt(right,bottom+37,x_name,15,anchor='rt');txt(left-8,top-8,y_name,14,anchor='rb')
        return x,y
    def trace(axis,x_values,y_values,color,width=2):
        x,y=axis
        points=list(zip(map(float,np.asarray(x(x_values))),map(float,np.asarray(y(y_values)))))
        if len(points)>1:draw.line(points,fill=color,width=width)
        elif points:draw.point(points[0],fill=color)
    limit=max(1,m['peak_abs_pcm'])*1.05
    a=axes((115,190,930,460),(0,(len(samples)-1)*1000/rate),(-limit,limit),'ms','PCM',title('完整采集时段','Time waveform'))
    trace(a,np.arange(len(samples))*1000/rate,samples,wave)
    a=axes((1173,178,1463,468),(-limit,limit),(-limit,limit),'x[n] / PCM','x[n−16]',title('单声道延时 XY','Mono delay XY')+f"  /  {m['xy_delay_ms']:.4f} ms")
    trace(a,samples[DELAY:],samples[:-DELAY],orange)
    for box,stop,name in [((115,624,930,925),rate/2,title('宽带频谱','Full-band FFT')),
                          ((1060,624,1560,925),min(focus_hz,rate/2),title('低频细看','Low-band detail'))]:
        a=axes(box,(0,stop/1000),(FLOOR_DBFS,max(0,float(levels.max())+3)),'kHz','dBFS',name)
        mask=hz<=stop;trace(a,hz[mask]/1000,levels[mask],blue)
        for k in peaks[hz[peaks]<=stop]:
            px=a[0](hz[k]/1000);py=a[1](levels[k]);draw.ellipse((px-3,py-3,px+3,py+3),fill=orange)
    txt(80,987,title('单段数字快照。圆点为过阈值谱峰，XY 两轴来自同一段单声道输入。',
                       'Finite snapshot. Dots mark qualified peaks. Both XY axes come from the same mono input.'),16)
    image.save(folder/'analysis.png')



def write_report(folder,raw,rate,relative_db,focus_hz,label,source):
    if not math.isfinite(focus_hz) or focus_hz<=0:raise ValueError('低频视图范围须为正有限数')
    result=analyze(raw,rate,relative_db);_,hz,amplitudes,levels,peaks,meta=result
    for fname,bins in [('spectrum.csv',range(len(hz))),('peaks.csv',peaks)]:
        with (folder/fname).open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['fft_bin','frequency_hz','peak_pcm','peak_dbfs'])
            writer.writerows((int(i),f'{hz[i]:.8f}',f'{amplitudes[i]:.6f}',f'{levels[i]:.4f}') for i in bins)
    plot(folder,label,result,focus_hz)
    meta['source']=source;meta['scope']='PC analysis of one frozen PCM block. Local peaks do not by themselves count independent hardware oscillators.'
    (folder/'analysis.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    name=html.escape(label)
    (folder/'analysis.html').write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name} · Tang 音频观察</title>
<style>body{{background:#f5f7f5;color:#193843;font:16px system-ui;margin:24px auto;max-width:1200px;padding:0 16px}}img{{display:block;width:100%;height:auto}}a{{color:#176b67;margin-right:20px}}p{{line-height:1.7}}</style>
<main><h1>电脑 PCM 观察 · {name}</h1><p>{meta['samples']} 点 · {rate:.3f} Hz · {meta['duration_ms']:.2f} ms · Hann 窗 · {meta['bin_spacing_hz']:.4f} Hz/bin。</p>
<p><a href="analysis.png">查看原图</a><a href="peaks.csv">峰表 CSV</a><a href="spectrum.csv">全部频点 CSV</a><a href="analysis.json">参数与来源</a></p>
<img src="analysis.png" alt="时域、宽带 FFT 与单声道延时 XY"><p>局部极大值须同时达到 1 PCM 码和相对最大谱线 −{relative_db:g} dB 的门槛，本段共有 {len(peaks)} 个。频谱峰数不能单独证明振荡器数量。XY 横轴取当前样本，纵轴取此前 16 个样本。以上均为电脑对单段冻结数据的分析。</p></main></html>''',encoding='utf8')
    return meta


def state(board):
    main=board.call(4);fw=main['firmware']
    if fw not in (31,32):raise ValueError('此采集入口支持 v31/v32 固件')
    return dict(audio=main,loop=board.call(14),page=board.call(32),pcm=board.call(PCM_STATUS))


def release(board,ident):
    current=board.call(PCM_STATUS)
    if current['capture_id']!=ident or not current['ready'] or current['armed'] or current['recording']:
        raise ValueError('抓取编号或状态已变化，只能释放指定且已完成的抓取')
    board.call(PCM_CONTROL,b'\0');after=board.call(PCM_STATUS)
    if after['ready'] or after['armed'] or after['recording']:raise RuntimeError('板卡未确认释放')


def acquire(board,create,samples,trigger,timeout):
    s=state(board);old=s['pcm'];page=s['page'];loop=s['loop']
    if page['score_reserved'] or page['score_loading'] or page['score_visible'] or page['score_valid']:
        raise ValueError('PDF 曲谱正在占用缓存。已保留该页，本次没有开始采集')
    if old['armed'] or old['recording']:raise ValueError('已有采集正在等待或录入，本次未更改它')
    if create:
        if old['ready']:raise ValueError(f"已有冻结抓取 {old['capture_id']}。请用 ready 导出，或按编号 release")
        if loop['recording'] or loop['pending_record']:raise ValueError('Loop 正在录制或待录，本次未改变它')
        expected=(old['capture_id']+1)&0xffff
        board.call(PCM_CONTROL,struct.pack('<BBHI',1,int(trigger=='nonzero'),samples,0))
        try:
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                current=board.call(PCM_STATUS)
                if current['capture_id']!=expected:raise RuntimeError('采集所有者发生变化，已停止读取')
                if current['ready']:break
                if current['error'] or current['aborted']:raise RuntimeError('板端采集失败')
                time.sleep(.01)
            else:raise TimeoutError('等待触发或记录完成超时')
        except BaseException:
            # Cancel only our own unfinished job; never abort a completed or replaced capture.
            try:
                latest=board.call(PCM_STATUS)
                if latest['capture_id']==expected and not latest['ready'] and (latest['armed'] or latest['recording']):
                    board.call(PCM_CONTROL,b'\0')
            except (OSError,RuntimeError,TimeoutError):pass  # ownership could not be verified; preserve the buffer
            raise
        if current['count']!=samples:raise RuntimeError('采集长度与请求不符')
    else:
        current=old
        if not current['ready']:raise ValueError('没有已完成的抓取可供读取')
    raw=read_frozen(current,board.call)
    return raw,current,dict(origin='actual FPGA final signed PCM before DAC-only trim',capture=current,initial=s)


def board_for(device):
    sys.path.insert(0,str(ROOT/'realtime_synth/control_meter_l8'))
    from verify_board import Board
    from transports import list_devices
    devices,_=list_devices()
    if not any(d['id']==device and d.get('preferred') for d in devices):
        raise ValueError(f'{device} 不是已识别的 FPGA UART B 通道，请核对端口')
    return Board(device)


def main():
    parser=argparse.ArgumentParser(description='电脑单段 PCM 分析 / 波形、宽带 FFT、单声道延时 XY 与峰表')
    modes=parser.add_subparsers(dest='mode')
    e=modes.add_parser('example',help='经 CRC 核实的实板归档，无需连接板卡');e.add_argument('name',choices=('all32','off16','off17'))
    f=modes.add_parser('file',help='读取小端、有符号、16 位单声道裸 PCM');f.add_argument('path',type=Path);f.add_argument('--fs',type=float,default=FS)
    capture=modes.add_parser('capture',help='仅在共享缓存空闲时发起一次抓取');capture.add_argument('--samples',type=int,default=4096);capture.add_argument('--trigger',choices=('immediate','nonzero'),default='immediate');capture.add_argument('--timeout',type=float,default=12)
    ready=modes.add_parser('ready',help='只读导出已完成抓取，保留原缓存');status=modes.add_parser('status',help='只读查询占用');free=modes.add_parser('release',help='释放指定编号已完成的 PCM');free.add_argument('--capture-id',type=int,required=True)
    for p in (capture,ready,status,free):p.add_argument('--device',default='com:COM6',help='UART B，如 com:COM6 或 d2xx:546')
    for p in (e,f,capture,ready):
        p.add_argument('--out',type=Path,default=ROOT/'output/pc-audio',help='结果父目录，每次创建单独子目录')
        p.add_argument('--peak-db',type=float,default=40,help='相对最强非DC谱线的检测范围，单位dB');p.add_argument('--focus-hz',type=float,default=4000)
        p.add_argument('--open',action='store_true',help='在默认浏览器打开本地分析报告')
    args=parser.parse_args(sys.argv[1:] or ['example','all32'])
    if hasattr(args,'peak_db') and (not 0<args.peak_db<=120 or not math.isfinite(args.focus_hz) or args.focus_hz<=0):
        parser.error('峰阈值为 (0,120] dB，低频视图范围须为正有限数')
    if args.mode=='release' and not 0<=args.capture_id<=65535:parser.error('采集编号须在 0～65535 之间')
    if args.mode=='capture' and (not DELAY<args.samples<=LIMIT or not 0<args.timeout<=120):parser.error('采集点数为17～32768，超时为(0,120]秒')
    board=None;meta=None
    try:
        if args.mode=='example':raw,rate,source=reference_pcm(args.name);label=args.name
        elif args.mode=='file':
            if not 2*DELAY<args.path.stat().st_size<=2*LIMIT:raise ValueError('裸 PCM 长度超出单段范围')
            raw=args.path.read_bytes();rate=args.fs;source=dict(origin='user-supplied mono signed little-endian PCM',path=str(args.path.resolve()),sample_rate_origin='CLI setting/default');label=args.path.stem
        else:
            board=board_for(args.device)
            if args.mode=='status':print(json.dumps(state(board),ensure_ascii=False,indent=2));return
            if args.mode=='release':
                s=state(board)
                if s['page']['score_reserved']:raise ValueError('PDF 缓存不能通过本命令释放')
                release(board,args.capture_id);print('已释放 PCM',args.capture_id);return
            raw,meta,source=acquire(board,args.mode=='capture',getattr(args,'samples',0),getattr(args,'trigger','immediate'),getattr(args,'timeout',0))
            rate=meta['sample_rate'];label=f"capture-{meta['capture_id']}"
        args.out.mkdir(parents=True,exist_ok=True)
        stem=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+args.mode+'-'
        folder=Path(tempfile.mkdtemp(prefix=stem,dir=args.out));(folder/'input.pcm').write_bytes(raw)
        if args.mode=='capture':release(board,meta['capture_id'])  # CRC verified and raw file saved; original ready capture is never auto-released.
        m=write_report(folder,raw,rate,args.peak_db,args.focus_hz,label,source)
        print(f"{folder}\n{m['samples']} 点，{m['duration_ms']:.3f} ms，{m['bin_spacing_hz']:.4f} Hz/bin，{m['peak_count']} 个过阈值谱峰。")
        if args.open:
            import webbrowser
            webbrowser.open((folder/'analysis.html').resolve().as_uri())
    finally:
        if board is not None:board.device.close()


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,TimeoutError) as exc:raise SystemExit(str(exc))
