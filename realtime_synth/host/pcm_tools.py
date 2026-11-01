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
    if controller.feedback.get('firmware',0)>=20:controller.exchange(FX_STATUS)
    controller.exchange(PCM_CONTROL,struct.pack('<BBHI',1,int(trigger=='nonzero'),int(length),delay))
    controller.pcm_job={};controller.pcm_files={}
    controller.pcm_context=dict(params=controller.params.copy(),keyboard=controller.keyboard.copy(),
        gain_mode=controller.gain_mode,trigger=trigger,delay_frames=delay,
        effects=getattr(controller,'fx_feedback',{}).copy())
    controller.exchange(PCM_STATUS)

def abort(controller):
    check(controller);controller.exchange(PCM_CONTROL,b'\0');controller.exchange(PCM_STATUS)
    controller.pcm_job={};controller.pcm_files={}

def write_wav(path,data):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(round(FS));w.writeframes(data)

def start_export(controller):
    check(controller)
    meta=controller.exchange(PCM_STATUS)
    if not meta['ready'] or meta['error'] or not meta['count']:
        raise ValueError('尚无完成且有效的抓取')
    job_id=uuid.uuid4().hex[:12]
    job=dict(id=job_id,running=True,progress=0,count=meta['count'],error='',done=False)
    controller.pcm_job=job
    transport=controller.transport
    context=controller.pcm_context.copy()
    def worker():
        data=bytearray();reads=0
        try:
            for offset in range(0,meta['count'],6):
                count=min(6,meta['count']-offset)
                with controller.lock:
                    if controller.transport is not transport:raise RuntimeError('连接已改变，导出中止')
                    controller.ui_seen=time.monotonic()
                    packet=controller.exchange(PCM_READ,struct.pack('<HHB',meta['capture_id'],offset,count))
                if packet['capture_id']!=meta['capture_id'] or packet['offset']!=offset or packet['count']!=count:
                    raise RuntimeError('返回块编号不匹配，拒绝生成 WAV')
                block=bytes.fromhex(packet['data'])
                if len(block)!=count*2:raise RuntimeError('音频块长度错误')
                data.extend(block);reads+=1;job['progress']=offset+count
            with controller.lock:
                after=controller.exchange(PCM_STATUS)
            for key in ('capture_id','count','first_frame','crc32'):
                if after[key]!=meta[key]:raise RuntimeError('导出期间抓取发生变化')
            actual=zlib.crc32(data)&0xffffffff
            if actual!=meta['crc32']:raise RuntimeError(f'CRC32 不匹配：{actual:08x} / {meta["crc32"]:08x}')
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
            controller.pcm_files={k:str(v) for k,v in [('raw',wav),('listen',listen)] if v is not None}
            job.update(done=True,path=str(wav),metadata_path=str(info),listen_path=str(listen) if listen else None,
                       duration_seconds=len(samples)/FS,crc32=f'{actual:08x}')
        except Exception as exc:job['error']=str(exc)
        finally:job['running']=False
    threading.Thread(target=worker,name='FPGA PCM export',daemon=True).start()
