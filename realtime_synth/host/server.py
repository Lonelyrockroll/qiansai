"""Local browser control panel. All sound synthesis remains on the FPGA."""
import argparse
import audio_web
import json
from pathlib import Path
import secrets
import socket
import threading
import time
import subprocess
import sys
import webbrowser
from urllib.parse import urlparse,parse_qs
import pcm_tools
import fx_tools
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from protocol import WHITE_KEYS, CONFIG, PING, PANIC, STATUS, GAIN, ARM, Decoder, packet, voice_payload, FS, KEY_CONFIG, KEY_CALIBRATE, KEY_STATUS, keyboard_payload
from transports import list_devices, open_device
from protocol import DISPLAY_ACTION, DISPLAY_STATUS, LED_CONTROL, LED_STATUS, LED_PIN_CONTROL, PCM_CONTROL, PCM_STATUS, PCM_READ, FX_CONTROL, FX_STATUS, FX_IMPULSE
from protocol import OUTPUT_GAIN_STATUS, PMOD_TEST, PMOD_STATUS
from keypad_config import MappingStore,INPUTS,CATALOG,LABELS,defaults,BY_ACTION,DRUM_NAMES

ROOT=Path(__file__).resolve().parent


class Controller:
    def __init__(self):
        self.lock=threading.RLock();self.transport=None;self.seq=0;self.decoder=Decoder()
        self.notes={};self.feedback={};self.error='';self.device='';self.ui_seen=time.monotonic()
        self.release_until={};self.next_voice=0
        self.last_poll=0;self.stop=threading.Event()
        self.gain_mode=1
        self.keyboard=dict(mode=0,key=12,press=256,release=128,sensitivity=64)
        self.key_feedback={}
        self.display_feedback={}
        self.led_feedback={}
        self.fx_feedback={};self.pcm_feedback={};self.pcm_job={};self.pcm_context={};self.pcm_files={}
        self.output_gain_feedback={};self.pmod_feedback={}
        self.touch=dict(enabled=False,active=False,reports=0,taps=0,last_point=None,last_menu=None,error='')
        self.touch_process=None;self.touch_seen=0;self.touch_session=''
        self.keypad=dict(enabled=False,active=False,connected=False,events=0,actions=0,last_input=None,last_action='',error='')
        self.keypad_store=MappingStore(ROOT/'control_keypad_mapping.json');self.keypad_seq=0
        self.params=dict(timbre=0,level=0.6,attack_ms=5,decay_ms=80,sustain=0.65,release_ms=100)
        self.worker=threading.Thread(target=self.monitor,daemon=True);self.worker.start()

    def exchange(self,opcode,payload=b''):
        try:return self._exchange(opcode,payload)
        except (OSError,TimeoutError) as error:
            self.error=str(error)
            if self.transport:
                try:self.transport.close()
                except OSError:pass
            self.transport=None;self.device='';self.notes.clear()
            self.touch['enabled']=False
            self.keypad['enabled']=False
            raise

    def _exchange(self,opcode,payload=b''):
        if self.transport is None:raise ValueError('请先连接板卡')
        self.seq=(self.seq+1)&255;seq=self.seq
        self.transport.write(packet(seq,opcode,payload))
        deadline=time.monotonic()+0.8
        while time.monotonic()<deadline:
            for status in self.decoder.feed(self.transport.read()):
                if status['seq']!=seq or status['opcode']!=opcode:continue
                firmware=status['firmware']
                rate_free=(opcode in (KEY_STATUS,DISPLAY_STATUS,LED_STATUS,PCM_STATUS,PCM_READ,FX_STATUS)
                           or (opcode==30 and firmware>=28) or (opcode==31 and firmware>=30) or (opcode in (32,33) and firmware>=31) or (opcode in (34,35) and firmware>=32))
                rate=status.get('sample_rate')
                if (not 6<=firmware<=32 or (opcode==30 and firmware<28) or (opcode==31 and firmware<30) or (opcode in (32,33) and firmware<31) or (opcode in (34,35) and firmware<32)
                    or (not rate_free and (rate is None or not abs(rate-FS)<=0.01))):
                    raise OSError('响应不是匹配的实时合成控制固件')
                if opcode==DISPLAY_STATUS:
                    self.display_feedback=status
                    self.keyboard.update({k:status[k] for k in ('mode','press','release','sensitivity')})
                elif opcode==KEY_STATUS:self.key_feedback=status
                elif opcode==LED_STATUS:self.led_feedback=status
                elif opcode==FX_STATUS:self.fx_feedback=status
                elif opcode==PMOD_STATUS:self.pmod_feedback=status
                elif opcode==OUTPUT_GAIN_STATUS:self.output_gain_feedback=status
                elif opcode==PCM_STATUS:self.pcm_feedback=status
                elif opcode in (PCM_READ,30,31,32,33,34,35):pass
                else:self.feedback=status
                if status['status']:
                    if opcode==PCM_CONTROL and status['status']==4:
                        raise ValueError('抓取缓存已被占用，已保留连接及现有数据')
                    raise OSError({1:'板卡拒绝了校验错误的数据帧',2:'不支持的命令',3:'板卡拒绝了超出范围的参数',4:'当前输入模式不允许此操作，或 ADC 尚未校准／故障'}.get(status['status'],'板卡命令失败'))
                self.last_poll=time.monotonic();return status
            time.sleep(0.002)
        raise TimeoutError('未收到匹配的板卡回应：请先下载 control 固件，核对串口通道，并关闭 Programmer／其他串口软件')

    def connect(self,identifier):
        self.disconnect()
        self.display_feedback={}
        self.led_feedback={}
        devices,_=list_devices()
        self.output_gain_feedback={};self.pmod_feedback={}
        if identifier not in [d['id'] for d in devices]:raise ValueError('设备已移除，请刷新端口')
        self.transport=open_device(identifier);self.device=identifier;self.decoder=Decoder()
        try:
            hello=self.exchange(PING)
            if hello['firmware']>=22:
                # Attach to a local/phone performance without overwriting its active settings.
                self.gain_mode=hello['gain_mode']
                display=self.exchange(DISPLAY_STATUS);output=self.exchange(OUTPUT_GAIN_STATUS)
                self.params.update(timbre=display['timbre'],level=output['keyboard_level']/65535)
                self.exchange(KEY_STATUS);self.exchange(FX_STATUS);self.exchange(PMOD_STATUS)
            else:
                self.exchange(PANIC);self.keyboard['mode']=0;self.set_keyboard(self.keyboard);self.set_gain(self.gain_mode)
            self.error='';self.ui_seen=time.monotonic()
        except Exception:
            if self.transport:self.transport.close()
            self.transport=None;self.device='';raise

    def disconnect(self):
        self.touch['enabled']=False;self.touch['active']=False
        self.keypad['enabled']=False;self.keypad['active']=False
        if self.transport:
            handle=self.transport
            try:self.exchange(PANIC)
            except Exception:pass
            finally:handle.close();self.transport=None
        self.notes.clear();self.release_until.clear();self.device=''

    def panic(self,keep_open=False):
        status=self.exchange(PANIC,bytes([int(keep_open)]));self.notes.clear();self.release_until.clear();return status

    def begin_performance(self):
        self.exchange(ARM)
        deadline=time.monotonic()+.4
        while not self.feedback.get('amp_ready'):
            if time.monotonic()>deadline:raise TimeoutError('功放准备超时')
            time.sleep(.005);self.exchange(STATUS)

    def set_keyboard(self,settings):
        candidate={k:settings[k] for k in ('mode','key','press','release','sensitivity')}
        payload=keyboard_payload(**candidate,params=self.params)
        candidate={k:int(v) for k,v in candidate.items()}
        self.exchange(KEY_CONFIG,payload)
        self.keyboard=candidate;self.notes.clear();self.release_until.clear()
        self.exchange(KEY_STATUS)

    def configure(self,voice,gate,frequency,note=None):
        payload=voice_payload(voice,gate,frequency,**self.params)
        if note is not None and self.feedback.get('firmware',0)>=26:
            payload+=bytes([0x80 | WHITE_KEYS.index(note)])
        self.exchange(CONFIG,payload)

    def start_touch(self):self.start_receiver('touch')

    def start_receiver(self,kind):
        version=12 if kind=='keypad' else 11
        if not self.transport or self.feedback.get('firmware',0)<version:raise ValueError(f'请先连接 v{version} 或更新的显示控制固件')
        running=(self.touch['enabled'] or self.keypad['enabled']) and self.touch_process and self.touch_process.poll() is None
        target=self.touch if kind=='touch' else self.keypad
        if target['enabled'] and running:return
        target.update(enabled=True,active=False,error='')
        self.panic()
        if running:return
        self.touch_session=secrets.token_hex(12);self.touch_seen=time.monotonic()
        self.keypad_seq=0
        self.touch.update(active=False,reports=0,taps=0,last_point=None,last_menu=None,error='')
        self.keypad.update(active=False,events=0,actions=0,last_input=None,last_action='',error='')
        try:
            with (ROOT/'touch_bridge.log').open('a',encoding='utf8') as log:
                self.touch_process=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'touch_bridge.py'),
                    '--url',self.local_origin,'--session',self.touch_session],cwd=ROOT,
                    stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception:
            self.touch['enabled']=False;self.keypad['enabled']=False;raise

    def touch_heartbeat(self,data):
        if data.get('session')!=self.touch_session:raise ValueError('触摸接收会话已失效')
        if not (self.touch['enabled'] or self.keypad['enabled']):return
        active=bool(data.get('active'))
        touch_active=active and self.touch['enabled'] and bool(data.get('touch_connected',True))
        keypad_active=active and self.keypad['enabled'] and bool(data.get('keypad_connected',False))
        if ((self.touch['active'] and not touch_active) or (self.keypad['active'] and not keypad_active)) and self.transport:self.panic()
        self.touch_seen=time.monotonic();self.touch.update(active=touch_active,
            reports=max(0,int(data.get('reports',0))),taps=max(0,int(data.get('taps',0))),
            last_point=data.get('last_point'),error=str(data.get('error',''))[:200])
        self.keypad.update(active=keypad_active,connected=bool(data.get('keypad_connected',False)),
            events=max(0,int(data.get('keypad_events',0))),error=str(data.get('keypad_error',''))[:200])

    def touch_click(self,data):
        if data.get('session')!=self.touch_session or not self.touch['enabled'] or not self.touch['active']:
            raise ValueError('触摸接收窗口未激活')
        if self.feedback.get('firmware',0)<11:raise ValueError('当前固件不支持直接触摸菜单')
        index=data.get('index')
        if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<(13 if self.feedback['firmware']>=32 else 12 if self.feedback['firmware']>=30 else 9 if self.feedback['firmware']>=22 else 8):raise ValueError('触摸菜单编号无效')
        if self.feedback['firmware']>=31:
            page=self.exchange(32)
            if page['score_show'] or page['score_visible'] or page['score_loading']:
                return  # A sheet has no synth menu hit targets.
        if self.feedback['firmware']>=32 and self.exchange(34)['monitor']:return
        self.exchange(DISPLAY_ACTION,bytes([5,index]))
        self.exchange(DISPLAY_STATUS);self.exchange(STATUS);self.exchange(KEY_STATUS)
        self.touch['last_menu']=index

    def control_function(self,action,step=1,count=1):
        """Apply existing product functions; volume is physical-key level, not PC note level."""
        if action=='none':return
        adjustable={'menu_next','menu_prev','volume_up','volume_down','tone_next','tone_prev'}
        if count>1 and action not in adjustable:
            for _ in range(count):self.control_function(action,step,1)
            return
        if action=='mute':self.panic()
        else:
            f=self.exchange(DISPLAY_STATUS)
            if f.get('drum_mode') and f.get('firmware',0)<16 and (action in ('scan_toggle','calibrate','tone_next','tone_prev') or action.startswith('tone_')):
                raise ValueError('当前为打击垫模式；请先切回控制模式，再操作琴键扫描或钢琴音色')
            amount=step*count
            if action in ('menu_next','menu_prev'):
                target=(f['focus']+(amount if action=='menu_next' else -amount))%(13 if f.get('firmware',0)>=32 else 12 if f.get('firmware',0)>=30 else 9 if f.get('firmware',0)>=22 else 8)
                self.exchange(DISPLAY_ACTION,bytes([6,target]))
            elif action.startswith('volume_'):
                delta=round(amount*65535/100)*(1 if action=='volume_up' else -1)
                level=max(0,min(16384,f['level']+delta))
                self.exchange(DISPLAY_ACTION,bytes([7])+level.to_bytes(2,'little'))
            elif action in ('tone_next','tone_prev'):
                target=(f['timbre']+(amount if action=='tone_next' else -amount))%5
                self.exchange(DISPLAY_ACTION,bytes([8,target]))
            elif action.startswith('tone_'):
                self.exchange(DISPLAY_ACTION,bytes([8,int(action[-1])]))
            elif action=='confirm':self.exchange(DISPLAY_ACTION,bytes([2]))
            elif action=='pattern':self.exchange(DISPLAY_ACTION,bytes([4]))
            elif f.get('firmware',0)>=16 and action in ('scan_toggle','calibrate'):
                self.exchange(DISPLAY_ACTION,bytes([11 if action=='scan_toggle' else 12]))
            else:
                index={'play_toggle':0,'scan_toggle':4,'calibrate':5,'pattern':7}[action]
                self.exchange(DISPLAY_ACTION,bytes([5,index]))
        self.exchange(DISPLAY_STATUS);self.exchange(STATUS)
        if self.keyboard['mode']:self.exchange(KEY_STATUS)

    def keypad_event(self,data):
        if data.get('session')!=self.touch_session or not self.keypad['enabled'] or not self.keypad['active']:
            raise ValueError('控制键盘接收窗口未激活')
        if self.feedback.get('firmware',0)<12:raise ValueError('需要 v12 控制键盘固件')
        seq=data.get('seq');count=data.get('count',1);key=data.get('input')
        if isinstance(seq,bool) or not isinstance(seq,int) or seq<1:raise ValueError('输入序号无效')
        if seq<=self.keypad_seq:return
        if key not in INPUTS or isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=64:
            raise ValueError('控制键盘输入无效')
        if count!=1 and key not in ('A_CW','A_CCW','B_CW','B_CCW'):raise ValueError('只有旋转支持多格合并')
        self.keypad_seq=seq;self.keypad['last_input']=key
        if data.get('revision')!=self.keypad_store.revision:
            self.keypad['last_action']='配置已更新，已跳过旧事件';return
        if self.feedback.get('firmware',0)>=16 and key.startswith('K'):
            if not self.feedback.get('amp_ready'):
                self.keypad['last_action']='请先开始演奏，鼓组按键当前静音';return
            pad=int(key[1:])-1
            self.exchange(15,bytes([pad]));self.exchange(STATUS);self.exchange(DISPLAY_STATUS)
            self.keypad['last_action']=DRUM_NAMES[pad]+' · 固定鼓组'
            self.keypad['actions']+=1
            return
        binding=self.keypad_store.value['bindings'][key]
        self.control_function(binding['action'],binding['step'],count)
        self.keypad['last_action']=BY_ACTION[binding['action']]['label']
        if key=='K09':self.keypad['last_action']+='（保留系统截图行为）'
        if binding['action']!='none':self.keypad['actions']+=count

    def set_gain(self,mode):
        mode=int(mode)
        if mode not in (0,1,2):raise ValueError('请选择原始、+12 dB 或 +18 dB 档')
        self.exchange(GAIN,bytes([mode]));self.gain_mode=mode

    def note_on(self,note):
        if self.keyboard['mode']:raise ValueError('请切回上位机琴键模式后再使用虚拟琴键')
        if not self.feedback.get('amp_hold') or not self.feedback.get('amp_ready'):
            raise ValueError('请先点击“开始演奏”，预热功放后再按琴键')
        note=int(note)
        if self.feedback.get('firmware',0)>=26 and note not in WHITE_KEYS:
            raise ValueError('实体琴对应 C2～F6 的 32 个白键')
        if note in self.notes:return
        now=time.monotonic()
        self.release_until={v:t for v,t in self.release_until.items() if t>now}
        used={v['voice'] for v in self.notes.values()}|set(self.release_until)
        if len(used)>=32:raise ValueError('32 个声部已用完，请先释放一些音符')
        voice=next((self.next_voice+i)%32 for i in range(32) if (self.next_voice+i)%32 not in used)
        frequency=440*2**((note-69)/12)
        self.configure(voice,1,frequency,note)
        self.next_voice=(voice+1)%32
        self.notes[note]=dict(voice=voice,frequency=frequency,note=note)

    def note_off(self,note):
        note=int(note)
        if note in self.notes:
            record=self.notes[note];self.configure(record['voice'],0,record['frequency'],note);del self.notes[note]
            # Keep release tails out of the allocator; round-robin also reduces abrupt reuse.
            release=int.from_bytes(voice_payload(record['voice'],0,record['frequency'],**self.params)[-2:],'little')
            self.release_until[record['voice']]=time.monotonic()+65535/(release*FS)+.03

    def action(self,data):
        with self.lock:
            self.ui_seen=time.monotonic()
            action=data.get('action')
            if action=='connect':self.connect(str(data['device']))
            elif action=='disconnect':self.disconnect()
            elif action=='panic':self.panic()
            elif action=='note_on':self.note_on(data['note'])
            elif action=='note_off':self.note_off(data['note'])
            elif action=='gain':self.set_gain(data['mode'])
            elif action=='arm':self.begin_performance()
            elif action=='keyboard':self.set_keyboard(data['settings'])
            elif action=='calibrate':
                self.exchange(KEY_CALIBRATE);self.notes.clear();self.release_until.clear();self.exchange(KEY_STATUS)
            elif action=='params':
                incoming=data['params']
                params={k:(int(incoming[k]) if k=='timbre' else float(incoming[k])) for k in self.params}
                voice_payload(0,0,440,**params) # validate before altering any state
                self.params=params
                if self.keyboard['mode']:self.set_keyboard(self.keyboard)
                else:
                    for record in self.notes.values():self.configure(record['voice'],1,record['frequency'],record['note'])
            elif action=='chord':
                if self.keyboard['mode']:raise ValueError('请先切回上位机琴键模式')
                self.panic(keep_open=True);self.begin_performance()
                for note in [60,64,67,72]:self.note_on(note)
            elif action=='spectrum':
                if self.keyboard['mode']:raise ValueError('请先切回上位机琴键模式')
                self.panic(keep_open=True);self.begin_performance();self.set_gain(0);old=self.params.copy()
                try:
                    self.params.update(timbre=0,level=0.6,sustain=1)
                    for voice in range(32):
                        hz=(17+7*voice)*FS/4096
                        self.configure(voice,1,hz)
                        self.notes[1000+voice]=dict(voice=voice,frequency=hz,note=None)
                finally:self.params=old
            elif action=='fx':fx_tools.configure(self,data)
            elif action=='pmod_test':
                if self.feedback.get('firmware',0)<22:raise ValueError('请先连接 v22 灯板固件')
                index=data.get('index')
                if index is not None and (type(index) is not int or not 0<=index<=7):raise ValueError('灯号应为 L1～L8')
                self.exchange(PMOD_TEST,b'\x01' if index is None else bytes([2,index]));self.exchange(PMOD_STATUS)
            elif action=='fx_status':self.exchange(FX_STATUS)
            elif action=='fx_impulse':fx_tools.impulse(self,data.get('amplitude',8192))
            elif action=='pcm_arm':pcm_tools.arm(self,data.get('length',32768),data.get('trigger','nonzero'),data.get('delay_ms',0))
            elif action=='pcm_abort':pcm_tools.abort(self)
            elif action=='pcm_release':pcm_tools.release_ready(self,data.get('capture_id'))
            elif action=='pcm_status':self.exchange(PCM_STATUS)
            elif action=='pcm_export':pcm_tools.start_export(self)
            elif action=='status':self.exchange(STATUS)
            elif action=='touch_start':self.start_touch()
            elif action=='keypad_start':self.start_receiver('keypad')
            elif action=='keypad_event':self.keypad_event(data)
            elif action=='keypad_save':self.keypad_store.save(data['config'])
            elif action=='keypad_reload':self.keypad_store.reload()
            elif action=='keypad_defaults':self.keypad_store.save(defaults())
            elif action=='keypad_stop':
                self.keypad.update(enabled=False,active=False)
                if self.transport:self.panic()
            elif action=='receiver_stop':
                if data.get('session')!=self.touch_session:raise ValueError('设备接收会话已失效')
                self.touch.update(enabled=False,active=False);self.keypad.update(enabled=False,active=False)
                if self.transport:self.panic()
            elif action=='touch_heartbeat':self.touch_heartbeat(data)
            elif action=='touch_click':self.touch_click(data)
            elif action=='touch_stop':
                if data.get('session') and data['session']!=self.touch_session:raise ValueError('触摸接收会话已失效')
                self.touch.update(enabled=False,active=False)
                if self.transport:self.panic()
            elif action=='display':
                if self.feedback.get('firmware',0)<10:raise ValueError('请先临时下载 HDMI 界面固件')
                command=int(data['command'])
                if command not in (1,2,3,4):raise ValueError('屏幕操作无效')
                self.exchange(DISPLAY_ACTION,bytes([command]));self.exchange(DISPLAY_STATUS)
                self.exchange(STATUS);self.exchange(KEY_STATUS)
            elif action=='led':
                if not self.transport or self.feedback.get('firmware',0)<17:raise ValueError('请先连接 v17 灯光固件')
                mode=data.get('mode')
                if isinstance(mode,bool) or not isinstance(mode,int) or mode not in (0,1,2,3):raise ValueError('灯光模式无效')
                if self.feedback.get('firmware',0)>=18:self.exchange(LED_PIN_CONTROL,b'\0')
                self.exchange(LED_CONTROL,bytes([mode]));self.exchange(LED_STATUS)
            elif action=='led_pin':
                if not self.transport or self.feedback.get('firmware',0)<18:raise ValueError('请先连接 v18 数据脚诊断固件')
                mode=data.get('mode')
                if isinstance(mode,bool) or not isinstance(mode,int) or mode not in (0,1,2):raise ValueError('数据脚诊断模式无效')
                self.exchange(LED_PIN_CONTROL,bytes([mode]));self.exchange(LED_STATUS)
            else:raise ValueError('未知操作')
            self.error='';return self.snapshot()

    def snapshot(self):
        return dict(connected=self.transport is not None,device=self.device,
                    notes=list(self.notes.values()),params=self.params,gain_mode=self.gain_mode,feedback=self.feedback,keyboard=self.keyboard,key_feedback=self.key_feedback,display_feedback=self.display_feedback,led_feedback=self.led_feedback,effects=self.fx_feedback,pmod=self.pmod_feedback,output_gain=self.output_gain_feedback,pcm_capture=self.pcm_feedback,pcm_export=self.pcm_job.copy(),touch=self.touch.copy(),
                    keypad=dict(self.keypad,revision=self.keypad_store.revision,config=self.keypad_store.snapshot(),config_error=self.keypad_store.error),error=self.error)

    def monitor(self):
        while not self.stop.wait(0.1):
            with self.lock:
                if self.transport is None:continue
                try:
                    if (self.touch['enabled'] or self.keypad['enabled']) and time.monotonic()-self.touch_seen>2.0:
                        self.touch.update(enabled=False,active=False,error='触摸接收中断，已静音')
                        self.keypad.update(enabled=False,active=False,error='设备接收中断，已静音')
                        self.panic()
                    if time.monotonic()-self.ui_seen>2.0:
                        self.disconnect();self.error='控制页面已离开，已静音并断开连接';continue
                    if time.monotonic()-self.last_poll>0.25:
                        self.exchange(STATUS)
                        if self.pcm_feedback.get('armed') or self.pcm_feedback.get('recording'):self.exchange(PCM_STATUS)
                        if self.feedback.get('firmware',0)>=10:self.exchange(DISPLAY_STATUS)
                        if self.feedback.get('firmware',0)>=17:self.exchange(LED_STATUS)
                        if self.feedback.get('firmware',0)>=20:self.exchange(FX_STATUS)
                        if self.feedback.get('firmware',0)>=21:self.exchange(OUTPUT_GAIN_STATUS)
                        if self.feedback.get('firmware',0)>=22:self.exchange(PMOD_STATUS)
                        if self.keyboard['mode']:self.exchange(KEY_STATUS)
                except Exception as error:
                    self.error=str(error)
                    try:
                        if self.transport:self.transport.close()
                    finally:self.transport=None;self.device='';self.notes.clear()
                    # FPGA independently resets audio after 3 s without a valid packet.


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--diagnose',action='store_true')
    args=parser.parse_args()
    if args.diagnose:
        devices,warnings=list_devices();print(json.dumps(dict(devices=devices,warnings=warnings),ensure_ascii=False,indent=2));return
    origin=f'http://127.0.0.1:{args.port}'
    try:
        with urllib.request.urlopen(origin,timeout=0.5) as response:
            existing=response.read().decode('utf-8')
        if '<title>Tang Mega 合成器控制台</title>' in existing:
            if not args.no_browser:webbrowser.open(origin)
            print('上位机已在运行，已复用现有控制页面。',flush=True)
            return
    except (OSError,ValueError):pass
    controller=Controller();token=secrets.token_hex(24)
    controller.local_origin=origin
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200,kind='application/json; charset=utf-8'):
            raw=value.encode('utf-8') if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(raw)
        def authorized(self):
            return (self.headers.get('Host')==f'127.0.0.1:{args.port}' and
                    self.headers.get('X-Synth-Token')==token and
                    self.headers.get('Origin',origin)==origin)
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{args.port}':self.send({'error':'invalid host'},403);return
            if audio_web.serve(self,token,origin):return
            pages={'/':'index.html','/keypad':'keypad.html'}
            if self.path in pages:
                self.send((ROOT/pages[self.path]).read_text(encoding='utf-8').replace('__TOKEN__',token),kind='text/html; charset=utf-8')
            elif urlparse(self.path).path=='/api/pcm/file' and self.authorized():
                query=parse_qs(urlparse(self.path).query);kind=query.get('kind',['raw'])[0]
                with controller.lock:
                    job=controller.pcm_job.copy();filename=controller.pcm_files.get(kind)
                if not job.get('done') or query.get('id',[''])[0]!=job.get('id') or not filename:
                    self.send({'error':'export not found'},404);return
                path=Path(filename);raw=path.read_bytes()
                self.send_response(200);self.send_header('Content-Type','application/octet-stream' if kind=='pcm' else 'audio/wav')
                self.send_header('Content-Length',str(len(raw)));self.send_header('Content-Disposition','attachment; filename="'+path.name+'"')
                self.end_headers();self.wfile.write(raw)
            elif self.path in ('/api/state','/api/devices','/api/keypad') and self.authorized():
                if self.path.endswith('devices'):
                    devices,warnings=list_devices();self.send(dict(devices=devices,warnings=warnings))
                elif self.path=='/api/keypad':
                    with controller.lock:self.send(dict(catalog=CATALOG,inputs=INPUTS,labels=LABELS,defaults=defaults(),state=controller.snapshot()))
                else:
                    with controller.lock:
                        controller.ui_seen=time.monotonic();self.send(controller.snapshot())
            else:self.send({'error':'not found'},404)
        def do_POST(self):
            if not self.authorized() or self.path!='/api/action':self.send({'error':'forbidden'},403);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<1 or length>8192:raise ValueError('request size')
                data=json.loads(self.rfile.read(length));self.send(controller.action(data))
            except Exception as error:self.send({'error':str(error)},400)
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    try:server=LocalServer(('127.0.0.1',args.port),Handler)
    except OSError:
        try:
            with urllib.request.urlopen(origin,timeout=1) as response:
                text=response.read().decode('utf-8')
            if '<title>Tang Mega 合成器控制台</title>' not in text:raise ValueError('port occupied')
            if not args.no_browser:webbrowser.open(origin)
            print('上位机已在运行，已复用现有控制页面。',flush=True)
            return
        except Exception:raise OSError(f'端口 {args.port} 已被占用；可用 --port 指定其他端口')
    print(f'合成器上位机：{origin}，115200 baud；关闭窗口前可先断开连接。',flush=True)
    if not args.no_browser:webbrowser.open(origin)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        controller.stop.set()
        with controller.lock:controller.disconnect()
        server.server_close()

if __name__=='__main__':main()
