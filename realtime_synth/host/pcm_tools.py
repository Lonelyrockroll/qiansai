"""Raw FPGA PCM capture/export. No synthesis or model-generated fallback."""
from pathlib import Path
import array,datetime,hashlib,json,struct,sys,threading,time,uuid,wave,zlib
from protocol import PCM_CONTROL,PCM_STATUS,PCM_READ,FX_STATUS,FS
OUTPUT=Path(__file__).resolve().parents[1]/'captures'

def check(controller):
    if not controller.transport or controller.feedback.get('firmware',0)<19:
        raise ValueError('请先连接包含数字抓取功能的 v19 固件')
    if controller.pcm_job.get('running'):
        raise ValueError('正在读取已冻结的音频，请等导出完成')

def arm(controller,length,trigger,delay_ms):
    check(controller)
    if isinstance(length,bool) or int(length)!=length or not 1<=length<=32768:
        raise ValueError('采样数应为 1～32768 的整数')
    if trigger not in ('nonzero','immediate'):raise ValueError('触发方式无效')
    delay_ms=float(delay_ms)
    if not 0<=delay_ms<=10000:raise ValueError('延迟范围为 0～10000 ms')
    delay=round(delay_ms*FS/1000)
    existing=controller.exchange(PCM_STATUS)
    if existing.get('armed') or existing.get('recording'):raise ValueError('已有抓取正在等待或录入')
    if existing['ready']:raise ValueError('已有冻结抓取，请先校验导出，再释放缓存')
    if controller.feedback.get('firmware',0)>=31 and controller.exchange(32)['score_reserved']:
        raise ValueError('PDF 曲谱占用缓存，已保留板上页面')
    if controller.feedback.get('firmware',0)>=20:controller.exchange(FX_STATUS)
    controller.exchange(PCM_CONTROL,struct.pack('<BBHI',1,int(trigger=='nonzero'),int(length),delay))
    controller.pcm_job={};controller.pcm_files={}
    controller.pcm_context=dict(params=controller.params.copy(),keyboard=controller.keyboard.copy(),
        gain_mode=controller.gain_mode,trigger=trigger,delay_frames=delay,
        effects=getattr(controller,'fx_feedback',{}).copy())
    controller.exchange(PCM_STATUS)

def abort(controller):
    check(controller)
    if controller.exchange(PCM_STATUS)['ready']:raise ValueError('抓取已经完成，请先校验导出，再释放缓存')
    controller.exchange(PCM_CONTROL,b'\0');controller.exchange(PCM_STATUS)
    controller.pcm_job={};controller.pcm_files={}

def release_ready(controller,ident):
    check(controller);meta=controller.exchange(PCM_STATUS)
    if isinstance(ident,bool) or not isinstance(ident,int) or not meta['ready'] or meta['capture_id']!=ident:
        raise ValueError('抓取已变化，拒绝释放旧编号')
    controller.exchange(PCM_CONTROL,b'\0');after=controller.exchange(PCM_STATUS)
    if after['ready'] or after['armed'] or after['recording']:raise RuntimeError('板卡未确认释放缓存')

def write_wav(destination,data,rate=FS):
    with wave.open(str(destination) if isinstance(destination,Path) else destination,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(round(rate));w.writeframes(data)

def reference_pcm(name):
    if name not in ('all32','off16','off17'):raise ValueError('未知实板归档')
    root=Path(__file__).resolve().parents[2];base=root/'tests/contest_board'
    for folder in (base,base/'intermediate-F939'):
        manifest=folder/'spectrum.json';pcm=folder/(name+'.pcm')
        if not (pcm.is_file() and manifest.is_file()):continue
        report=json.loads(manifest.read_text(encoding='utf8'))
        if report.get('result')!='passed':raise ValueError('实板频谱记录尚未通过验收')
        case=report['cases'][name];info=case['pcm']
        raw=pcm.read_bytes();cap=info['capture'];rate=float(report['fs_hz'])
        if (hashlib.sha256(raw).hexdigest()!=info['sha256'] or zlib.crc32(raw)!=cap['crc32']
            or cap['count']*2!=len(raw) or cap['sample_rate']!=rate):raise ValueError('实板 PCM 与随附采集记录不匹配')
        return raw,rate,dict(origin='archived board capture',path=pcm.relative_to(root).as_posix(),
            capture_id=cap['capture_id'],first_frame=cap['first_frame'],firmware=cap['firmware'],
            reference_peak_count=case['monitor']['peak_count'],reference_bins=case['bins'])
    raise FileNotFoundError('未找到配套实板 PCM 与 spectrum.json')

def read_frozen(meta,exchange,progress=None):
    """Read only an identified, complete capture. Check the header again after the final block."""
    if not meta['ready'] or meta['error'] or not 1<=meta['count']<=32768:
        raise ValueError('尚无完成且有效的抓取')
    data=bytearray()
    for offset in range(0,meta['count'],6):
        count=min(6,meta['count']-offset)
        item=exchange(PCM_READ,struct.pack('<HHB',meta['capture_id'],offset,count))
        if (item['capture_id'],item['offset'],item['count'])!=(meta['capture_id'],offset,count):
            raise RuntimeError('返回块编号不匹配，拒绝生成音频文件')
        block=bytes.fromhex(item['data'])
        if len(block)!=count*2:raise RuntimeError('音频块长度错误')
        data.extend(block)
        if progress:progress(offset+count)
    after=exchange(PCM_STATUS)
    if not after['ready'] or after['error'] or any(after[k]!=meta[k] for k in ('capture_id','count','first_frame','crc32')):
        raise RuntimeError('导出期间抓取发生变化')
    actual=zlib.crc32(data)&0xffffffff
    if actual!=meta['crc32']:raise RuntimeError(f'CRC32 不匹配：{actual:08x} / {meta["crc32"]:08x}')
    return bytes(data)

def start_export(controller):
    check(controller)
    meta=controller.exchange(PCM_STATUS)
    if not meta['ready'] or meta['error'] or not meta['count']:
        raise ValueError('尚无完成且有效的抓取')
    job_id=uuid.uuid4().hex[:12]
    job=dict(id=job_id,running=True,progress=0,count=meta['count'],capture_id=meta['capture_id'],error='',done=False)
    controller.pcm_job=job
    transport=controller.transport
    context=controller.pcm_context.copy()
    def worker():
        try:
            def exchange(op,payload=b''):
                with controller.lock:
                    if controller.transport is not transport:raise RuntimeError('连接已改变，导出中止')
                    controller.ui_seen=time.monotonic()
                    return controller.exchange(op,payload)
            data=read_frozen(meta,exchange,lambda value:job.update(progress=value))
            actual=meta['crc32'];reads=(len(data)//2+5)//6
            OUTPUT.mkdir(exist_ok=True)
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            stem=f'fpga_pcm_{stamp}_{job_id}'
            raw=OUTPUT/(stem+'.pcm');wav=OUTPUT/(stem+'.wav');info=OUTPUT/(stem+'.json')
            raw.write_bytes(data);write_wav(wav,data)
            samples=array.array('h');samples.frombytes(data)
            if sys.byteorder!='little':samples.byteswap()
            peak=max(abs(v) for v in samples)
            listen=None;listen_gain=1.0
            if peak:
                listen_gain=26214/peak
                scaled=array.array('h',(max(-32768,min(32767,round(v*listen_gain))) for v in samples))
                if sys.byteorder!='little':scaled.byteswap()
                listen=OUTPUT/(stem+'_listen.wav');write_wav(listen,scaled.tobytes())
            metadata=dict(origin='actual FPGA capture RAM, transferred by UART; not a software synthesis',
                tap='final mixed signed PCM loaded by audio_tx, before PT8211-only DC bias',
                channels=1,bits=16,sample_rate_exact=FS,wav_header_rate=round(FS),
                sample_count=len(samples),duration_seconds=len(samples)/FS,first_frame=meta['first_frame'],
                capture_id=meta['capture_id'],crc32=f'{actual:08x}',sha256=hashlib.sha256(data).hexdigest(),
                read_chunks=reads,verified=True,firmware=meta['firmware'],context=context,
                raw_path=str(raw),wav_path=str(wav),listen_path=str(listen) if listen else None,
                listen_gain=listen_gain,peak_code=peak)
            info.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            controller.pcm_files={k:str(v) for k,v in [('raw',wav),('listen',listen),('pcm',raw)] if v is not None}
            job.update(done=True,path=str(wav),metadata_path=str(info),listen_path=str(listen) if listen else None,
                       duration_seconds=len(samples)/FS,crc32=f'{actual:08x}')
        except Exception as exc:job['error']=str(exc)
        finally:job['running']=False
    threading.Thread(target=worker,name='FPGA PCM export',daemon=True).start()
