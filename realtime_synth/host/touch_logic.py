"""Single-finger tap recognition for the FPGA's 1024x600 menu.
Coordinates come from HID logical ranges. No desktop cursor coordinates are used.
"""
import math

MENU=['开始 / 停止演奏','切换音色','音量增加','音量减小','切换扫描','松键校准','全部静音','屏幕检测']

def menu_names(display):
    display=display or {}
    if display.get('firmware',0)>=22:
        return menu_names(dict(display,firmware=21))+['效果切换']
    if display.get('firmware',0)>=16:
        if display.get('drum_mode'):
            return ['开始 / 停止演奏','录制 / 结束','撤销末轮','播放 / 停止循环','录制上限','清空循环','全部静音','琴键设置']
        return ['开始 / 停止演奏','录制 / 结束','切换音色','琴键扫描','松键校准','播放 / 停止循环','全部静音','鼓组与 Loop']
    if display.get('drum_mode'):
        if display.get('firmware',0)>=15:
            return ['开始 / 停止演奏','录制一轮','撤销末轮','播放 / 停止循环','循环时长','清空循环','全部静音','控制模式']
        return ['开始 / 停止演奏','控制模式','音量增加','音量减小','复位音量','停止尾音','全部静音','屏幕检测']
    return MENU

def to_pixel(contact):
    out=[]
    for axis,size in [('x',1024),('y',600)]:
        value=contact[axis];low=contact[axis+'_min'];high=contact[axis+'_max']
        if not all(math.isfinite(v) for v in (value,low,high)) or high<=low or not low<=value<=high:
            raise ValueError('触摸坐标越界')
        out.append(min(size-1,max(0,round((value-low)*(size-1)/(high-low)))))
    return tuple(out)

def hit_test(x,y,pattern=False,rows=8):
    if not (0<=x<1024 and 0<=y<600):return None
    if pattern:return 7 # one tap returns from the full-screen test pattern
    if not 632<=x<992 or y<112:return None
    row=(y-112)//48
    return int(row) if 0<=row<rows and y<536 and y<112+row*48+44 else None

class ContactFrames:
    """Hybrid HID: count includes inactive contacts; count=0 can be continuation.
    Do not mistake a single finger plus two release records for three fingers.
    """
    def __init__(self):self.reset()
    def reset(self):self.expected=0;self.contacts=[];self.started=0
    def feed(self,event):
        if event.get('device_change'):self.reset();return None
        now=event['time'];count=event.get('contact_count')
        if self.expected and now-self.started>.1:self.reset()
        if count is None:return event.get('contacts',[])
        if count:
            self.reset()
            if not 1<=count<=10:return None
            self.expected=count;self.started=now
        if not self.expected:return None
        self.contacts.extend(event.get('contacts',[]))
        if len(self.contacts)<self.expected:return None
        frame=self.contacts[:self.expected];self.reset();return frame

class TapDetector:
    def __init__(self):self.last_click=-100;self.reset()
    def reset(self):
        self.candidate=None;self.blocked=False;self.was_down=False;self.last_time=0;self.point=None
    def feed(self,contacts,now,pattern=False,allowed=True,rows=8):
        if not allowed:
            self.reset();self.blocked=True;return None
        if self.was_down and now-self.last_time>1:
            self.candidate=None;self.blocked=True
        self.last_time=now
        down=[c for c in contacts if c['down']]
        if len(down)>1:
            self.candidate=None;self.blocked=True;self.was_down=True;return None
        if down:
            c=down[0]
            try:x,y=to_pixel(c)
            except ValueError:self.candidate=None;self.blocked=True;return None
            self.point=(x,y);row=hit_test(x,y,pattern,rows)
            if not self.was_down and not self.blocked:
                self.candidate=dict(id=c.get('id',0),row=row,x=x,y=y,time=now,pattern=pattern)
            elif self.candidate:
                a=self.candidate
                if c.get('id',0)!=a['id'] or row!=a['row'] or pattern!=a['pattern'] or (x-a['x'])**2+(y-a['y'])**2>24**2:
                    self.candidate=None;self.blocked=True
            self.was_down=True;return None
        candidate=self.candidate;was_down=self.was_down;blocked=self.blocked
        self.candidate=None;self.was_down=False;self.blocked=False
        if not was_down or blocked or candidate is None:return None
        releases=[c for c in contacts if c.get('id',0)==candidate['id']]
        if not releases:return None
        try:x,y=to_pixel(releases[0])
        except ValueError:return None
        self.point=(x,y)
        row=candidate['row']
        if row is None or hit_test(x,y,pattern,rows)!=row or pattern!=candidate['pattern']:return None
        if (x-candidate['x'])**2+(y-candidate['y'])**2>24**2:return None
        if not .015<=now-candidate['time']<=2.0 or now-self.last_click<.15:return None
        self.last_click=now;return row
