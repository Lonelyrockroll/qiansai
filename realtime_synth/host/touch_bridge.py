"""PC USB-touch -> existing local HTTP/serial controller -> FPGA menu.
The fullscreen receiver consumes Windows touch-generated clicks in its own surface.
Leaving its foreground pauses forwarding and mutes; Esc stops and mutes.
"""
import argparse,ctypes as C,json,queue,re,threading,time,tkinter as tk,urllib.request
from ctypes import wintypes as W
from pathlib import Path
from touch_hid import RawTouchReader,user32
from touch_logic import ContactFrames,TapDetector,MENU,menu_names
from keypad_input import KeypadReceiver
from keypad_config import KeypadInterpreter,INPUTS,LABELS,BY_ACTION

user32.GetForegroundWindow.argtypes=[];user32.GetForegroundWindow.restype=C.c_void_p
user32.GetAncestor.argtypes=[C.c_void_p,W.UINT];user32.GetAncestor.restype=C.c_void_p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:8765');ap.add_argument('--session',required=True);args=ap.parse_args()
    page=urllib.request.urlopen(args.url,timeout=2).read().decode('utf8')
    token=re.search(r"TOKEN='([a-f0-9]+)'",page).group(1)
    def call(action,**kwargs):
        data=json.dumps(dict(action=action,session=args.session,**kwargs)).encode()
        req=urllib.request.Request(args.url+'/api/action',data=data,headers={'X-Synth-Token':token,'Content-Type':'application/json'})
        return json.load(urllib.request.urlopen(req,timeout=2))
    inputs=queue.Queue(maxsize=512);updates=queue.Queue();stop=threading.Event();foreground=threading.Event()
    touch_requested=threading.Event();keypad_requested=threading.Event();worker_done=threading.Event()
    keypad_generation=[0]
    def incoming(e):
        try:inputs.put_nowait(e)
        except queue.Full:
            # Never interpret a partial gesture after queue overflow.
            while not inputs.empty():
                try:inputs.get_nowait()
                except queue.Empty:break
            inputs.put_nowait(dict(device_change=True,connected=False,time=time.monotonic()))
    reader=RawTouchReader(lambda e:incoming(e) if touch_requested.is_set() else None)
    app=tk.Tk();app.title('Tang 设备控制接收 — Esc 停止并静音');app.configure(bg='#0c1623');app.attributes('-fullscreen',True)
    tk.Label(app,text='USB 设备控制 · 电脑转发',fg='#55dfbd',bg='#0c1623',font=('Microsoft YaHei',30)).pack(pady=(35,14))
    tk.Label(app,text='使用已启用的小键盘或触摸屏控制。\n保持此窗口在前台；按 Esc 停止转发并静音。',fg='#e9edf2',bg='#0c1623',font=('Microsoft YaHei',20)).pack(pady=10)
    headline=tk.Label(app,text='正在连接触摸屏…',fg='#e9edf2',bg='#0c1623',font=('Microsoft YaHei',22));headline.pack(pady=20)
    canvas=tk.Canvas(app,width=820,height=480,bg='#172737',highlightthickness=0);canvas.pack()
    for i,name in enumerate(MENU+['效果切换','播放 / 暂停指引','指引下一组','指引重来']):
        y=112+i*48;canvas.create_rectangle(632*.8,y*.8,992*.8,(y+44)*.8,outline='#436176',tags=f'row{i}')
        canvas.create_text(646*.8,(y+22)*.8,text=f'{i+1}  {name}',anchor='w',fill='#e9edf2',font=('Microsoft YaHei',13),tags=f'menu_label{i}')
    for i,key in enumerate(INPUTS):
        if i<12:x=24+(i%4)*115;y=92+(i//4)*75;w=108;h=66
        else:x=24+((i-12)%3)*153;y=330+((i-12)//3)*63;w=145;h=56
        canvas.create_rectangle(x,y,x+w,y+h,fill='#172737',outline='#436176',tags='key_'+key)
        canvas.create_text(x+w/2,y+h/2,text=LABELS[key],fill='#e9edf2',width=w-6,font=('Microsoft YaHei',10),tags='label_'+key)
    details=tk.Label(app,text='',fg='#96a9ba',bg='#0c1623',font=('Microsoft YaHei',15));details.pack(pady=14)
    error_label=tk.Label(app,text='',fg='#ff9c9c',bg='#0c1623',font=('Microsoft YaHei',16));error_label.pack()
    tk.Label(app,text='K09 保留系统截图行为；截图或切换窗口时暂停，回到本窗口自动恢复。',fg='#96a9ba',bg='#0c1623',font=('Microsoft YaHei',14)).pack(pady=12)
    app.update_idletasks();hwnd=user32.GetAncestor(app.winfo_id(),2)
    frames=ContactFrames();taps=TapDetector();key_logic=KeypadInterpreter()
    def keypad_incoming(e):incoming(dict(e,source='keypad'))
    keys=KeypadReceiver(app,keypad_incoming,lambda wp:keypad_requested.is_set() and (int(wp)&255)==0,generation=lambda:keypad_generation[0])
    logdir=Path(__file__).resolve().parents[1]/'control_display/touch_validation';logdir.mkdir(exist_ok=True)
    keylog=Path(__file__).resolve().parents[1]/'keypad_control';keylog.mkdir(exist_ok=True)
    def worker():
        clicks=0;last_heartbeat=0;state={};error='';last_active=False;seq=0;revision=-1;touch_running=False
        def send_key(key,count):
            nonlocal state,seq,error
            seq+=1
            state=call('keypad_event',input=key,count=count,seq=seq,revision=revision);error=''
            record=dict(time=time.time(),input=key,count=count,action=state.get('keypad',{}).get('last_action'),
                feedback=state.get('display_feedback'),status=state.get('feedback'))
            with (keylog/'bridge_actions.jsonl').open('a',encoding='utf8') as log:log.write(json.dumps(record,ensure_ascii=False)+'\n')
        try:
            try:reader.start();touch_running=True
            except OSError:pass # Keypad mode works without a touchscreen attached.
            while not stop.is_set():
                now=time.monotonic();active=user32.GetForegroundWindow()==hwnd
                if now-last_heartbeat>.35 or active!=last_active:
                    if last_active and not active:
                        frames.reset();taps.feed([],now,allowed=False);key_logic.suspend();keypad_generation[0]+=1
                    state=call('touch_heartbeat',active=active,touch_connected=touch_running and bool(reader.devices) and not reader.error,
                        reports=reader.count,taps=clicks,last_point=taps.point,error=reader.error if touch_requested.is_set() else '',
                        keypad_connected=bool(keys.devices),keypad_events=keys.target_events)
                    k=state.get('keypad',{});t=state.get('touch',{})
                    if k.get('revision')!=revision:
                        revision=k.get('revision',0);key_logic.suspend();keypad_generation[0]+=1
                    if t.get('enabled'):touch_requested.set()
                    else:touch_requested.clear()
                    if k.get('enabled'):keypad_requested.set()
                    else:keypad_requested.clear()
                    last_heartbeat=now;last_active=active;updates.put((state,taps.point,error))
                    if not (t.get('enabled') or k.get('enabled')) or not state.get('connected'):break
                if active and keypad_requested.is_set() and inputs.empty() and not keys.events:
                    for key,count in key_logic.flush(now):send_key(key,count)
                try:event=inputs.get(timeout=.03)
                except queue.Empty:continue
                if event.get('source')=='keypad':
                    if event.get('type')=='receiver_error':
                        error=event.get('error','接收错误');call('panic');key_logic.reset();continue
                    if active and keypad_requested.is_set() and state.get('keypad',{}).get('active') and 0<=time.monotonic()-event['time']<.35 and user32.GetForegroundWindow()==hwnd:
                        for key,count in key_logic.feed(event,event['time']):send_key(key,count)
                    else:
                        key_logic.feed(event,event['time']);key_logic.suspend()
                    updates.put((state,taps.point,error));continue
                if event.get('device_change'):
                    frames.reset();taps.feed([],now,allowed=False)
                    if not event.get('connected'):call('panic');error='触摸屏已断开，请重新连接后再试'
                    continue
                contacts=frames.feed(event)
                if contacts is None:continue
                # Timestamp is from acquisition, not from delayed HTTP/UI processing.
                fresh=0<=time.monotonic()-event['time']<.25
                row=taps.feed(contacts,event['time'],rows=len(menu_names(state.get('display_feedback'))),pattern=state.get('display_feedback',{}).get('pattern',False),
                    allowed=active and touch_requested.is_set() and fresh and user32.GetForegroundWindow()==hwnd)
                if row is not None:
                    action_name=menu_names(state.get('display_feedback'))[row]
                    state=call('touch_click',index=row);clicks+=1;error=''
                    record=dict(time=time.time(),menu=row,name=action_name,point=taps.point,feedback=state.get('display_feedback'),status=state.get('feedback'))
                    with (logdir/'bridge_actions.jsonl').open('a',encoding='utf8') as log:log.write(json.dumps(record,ensure_ascii=False)+'\n')
                updates.put((state,taps.point,error))
        except Exception as e:
            error=str(e);updates.put((state,taps.point,error));print('Touch bridge:',error,flush=True)
            try:call('touch_heartbeat',active=False,error=error,keypad_error=error)
            except Exception:pass
        finally:
            if touch_running:reader.stop()
            try:call('receiver_stop')
            except Exception:pass
            updates.put((state,taps.point,error or '设备接收已停止，按 Esc 返回'))
            worker_done.set()
    thread=threading.Thread(target=worker,name='touch-forward',daemon=True);thread.start()
    last_display=None
    def draw():
        nonlocal last_display
        if worker_done.is_set():keys.stop();app.destroy();return
        keys.drain()
        if user32.GetForegroundWindow()==hwnd:foreground.set()
        else:foreground.clear()
        latest=None
        while not updates.empty():latest=updates.get_nowait()
        if latest:
            state,point,error=latest;f=state.get('display_feedback',{});t=state.get('touch',{});k=state.get('keypad',{})
            if point:
                canvas.delete('pointer');x,y=point;canvas.create_oval(x*.8-7,y*.8-7,x*.8+7,y*.8+7,fill='#55dfbd',outline='',tags='pointer')
            label='正在转发' if t.get('active') or k.get('active') else '已暂停 / 已停止'
            names=menu_names(f)
            recent=(str(k.get('last_input') or '')+' '+k.get('last_action','')).strip() or (names[t['last_menu']] if t.get('last_menu') is not None else '等待操作')
            headline.configure(text=f"{label} · {recent}")
            for i in range(12):
                visible='normal' if i<len(names) else 'hidden'
                if f.get('firmware',0)>=30:
                    mx,my=512+(i//6)*240,332+(i%6)*32
                    canvas.coords(f'row{i}',mx*.8,my*.8,(mx+232)*.8,(my+28)*.8)
                    canvas.coords(f'menu_label{i}',(mx+14)*.8,(my+14)*.8)
                else:
                    my=112+i*48
                    canvas.coords(f'row{i}',632*.8,my*.8,992*.8,(my+44)*.8)
                    canvas.coords(f'menu_label{i}',646*.8,(my+22)*.8)
                canvas.itemconfigure(f'row{i}',state=visible)
                canvas.itemconfigure(f'menu_label{i}',state=visible)
                if i>=len(names):continue
                canvas.itemconfigure(f'row{i}',fill='#285367' if i==f.get('focus') else '#172737')
                canvas.itemconfigure(f'menu_label{i}',text=f'{i+1}  {names[i]}')
            for key,bind in k.get('config',{}).get('bindings',{}).items():
                canvas.itemconfigure('key_'+key,fill='#285367' if key==k.get('last_input') else '#172737')
                caption=BY_ACTION[bind['action']]['label']+(f" ×{bind['step']}" if bind['step']>1 else '')
                canvas.itemconfigure('label_'+key,text=LABELS[key]+'\n'+caption)
            details.configure(text=f"小键盘 {k.get('actions',0)} 次 · 触摸 {t.get('taps',0)} 次 · 琴键音量 {f.get('volume','—')}% · {'静音' if f.get('amp_muted',True) else '演奏中'}")
            error_label.configure(text=error or k.get('error','') or t.get('error',''));last_display=state
        if not stop.is_set():app.after(60,draw)
    def close(*_):
        if stop.is_set():return
        stop.set();foreground.clear()
        def finish():
            if thread.is_alive():app.after(60,finish)
            else:keys.stop();app.destroy()
        app.after(10,finish)
    app.bind('<Escape>',close);app.protocol('WM_DELETE_WINDOW',close);app.after(20,draw);app.mainloop()

if __name__=='__main__':main()
