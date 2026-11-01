"""Visible, bounded touchscreen acquisition test. Does not contact the FPGA.
The receiver surface protects other apps from touch-generated mouse clicks.
Escape closes; auto closes after --seconds. Raw input only accepts VID/PID 0483:5750.
"""
import argparse,json,queue,time,tkinter as tk
from pathlib import Path
from touch_hid import RawTouchReader

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=int,default=120);args=ap.parse_args()
    dest=Path(__file__).resolve().parents[1]/'control_display/touch_validation';dest.mkdir(exist_ok=True)
    events=queue.Queue(maxsize=2048);records=[]
    def receive(e):
        try:events.put_nowait(e)
        except queue.Full:pass
    reader=RawTouchReader(receive);reader.start()
    (dest/'hid_descriptor.json').write_text(json.dumps([d.describe() for d in reader.devices.values()],ensure_ascii=False,indent=2),encoding='utf8')
    app=tk.Tk();app.title('Tang 触摸坐标测试 — Esc 退出');app.attributes('-fullscreen',True);app.configure(bg='#0c1623')
    title=tk.Label(app,text='触摸坐标测试 · 只接收，不发声',fg='#55dfbd',bg='#0c1623',font=('Microsoft YaHei',28));title.pack(pady=36)
    tk.Label(app,text='请点 7 英寸屏幕的左上角，再点右下角。\n电脑此窗口用于接收触摸；按 Esc 可退出。',fg='#e9edf2',bg='#0c1623',font=('Microsoft YaHei',21)).pack(pady=10)
    info=tk.Label(app,text='等待触摸数据…',fg='white',bg='#0c1623',font=('Consolas',24));info.pack(pady=32)
    canvas=tk.Canvas(app,width=820,height=480,bg='#172737',highlightthickness=0);canvas.pack()
    status=tk.Label(app,fg='#96a9ba',bg='#0c1623',font=('Microsoft YaHei',14));status.pack(pady=15)
    start=time.monotonic();closed=False
    log=(dest/'probe_events.jsonl').open('w',encoding='utf8')
    def finish(*_):
        nonlocal closed
        if closed:return
        closed=True;reader.stop();log.close()
        (dest/'probe_result.json').write_text(json.dumps(dict(events=len(records),reader_error=reader.error,
            report_count=reader.count,events_file='probe_events.jsonl',elapsed_seconds=time.monotonic()-start),indent=2),encoding='utf8')
        app.destroy()
    def poll():
        while not events.empty():
            e=events.get_nowait();records.append(e);log.write(json.dumps(e,ensure_ascii=False)+'\n');log.flush()
            for c in e.get('contacts',[]):
                info.configure(text=f"X={c['x']} / {c['x_max']}   Y={c['y']} / {c['y_max']}   {'DOWN' if c['down'] else 'UP'}")
                x=c['x']/max(1,c['x_max'])*820;y=c['y']/max(1,c['y_max'])*480
                canvas.delete('pointer');canvas.create_oval(x-9,y-9,x+9,y+9,fill='#55dfbd' if c['down'] else '#96a9ba',outline='',tags='pointer')
        remaining=max(0,args.seconds-int(time.monotonic()-start));status.configure(text=f'收到 {reader.count} 份触摸报告 · {remaining} 秒后自动结束' + (' · '+reader.error if reader.error else ''))
        if remaining==0:finish()
        else:app.after(50,poll)
    app.bind('<Escape>',finish);app.protocol('WM_DELETE_WINDOW',finish);app.after(50,poll);app.mainloop()

if __name__=='__main__':main()
