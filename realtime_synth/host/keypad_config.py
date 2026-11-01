"""Application mappings only. Never writes the USB keypad's onboard configuration."""
from pathlib import Path
import copy,json,os

DEVICE='1189:8840'
DRUM_NAMES=['底鼓','军鼓','拍手','闭镲','开镲','低通鼓','中通鼓','高通鼓','吊镲','叮叮镲','边击','牛铃']
KEYS=[f'K{i:02}' for i in range(1,13)]
INPUTS=KEYS+['A_CW','A_CCW','A_PRESS','B_CW','B_CCW','B_PRESS']
RAW_KEYS=['F','K','X','Space','Enter','D','S','A','PrintScreen','Backspace','W','F13']
LABELS={**{k:f'{k} · {raw}' for k,raw in zip(KEYS,RAW_KEYS)},
    'A_CW':'旋钮 A 顺转','A_CCW':'旋钮 A 逆转','A_PRESS':'旋钮 A 按压',
    'B_CW':'旋钮 B 顺转','B_CCW':'旋钮 B 逆转','B_PRESS':'旋钮 B 按压'}
CATALOG=[
    dict(id='none',label='不分配',max_step=1),
    dict(id='play_toggle',label='开始 / 停止演奏',max_step=1),
    dict(id='mute',label='全部静音',max_step=1),
    dict(id='volume_up',label='琴键音量增加',max_step=10,unit='百分点'),
    dict(id='volume_down',label='琴键音量减小',max_step=10,unit='百分点'),
    dict(id='tone_next',label='下一个音色',max_step=4,unit='档'),
    dict(id='tone_prev',label='上一个音色',max_step=4,unit='档'),
    dict(id='menu_next',label='下一菜单项',max_step=7,unit='项'),
    dict(id='menu_prev',label='上一菜单项',max_step=7,unit='项'),
    dict(id='confirm',label='执行所选菜单',max_step=1),
    dict(id='scan_toggle',label='开启 / 关闭扫描',max_step=1),
    dict(id='calibrate',label='松键校准',max_step=1),
    dict(id='pattern',label='界面 / 检测图',max_step=1),
    *[dict(id=f'tone_{i}',label='音色：'+t,max_step=1) for i,t in enumerate(['纯净正弦','风琴音色','柔和复合','弦乐锯齿','敲击钢琴'])]]
BY_ACTION={c['id']:c for c in CATALOG}
DEFAULT_ACTIONS=['play_toggle','mute','tone_next','tone_prev','confirm','scan_toggle','calibrate','pattern',
    'none','menu_prev','menu_next','mute','volume_up','volume_down','mute','menu_next','menu_prev','confirm']

def defaults():
    return dict(schema=1,device=DEVICE,layout='3x4',name='默认控制布局',bindings={
        k:dict(action=a,step=2 if a.startswith('volume_') else 1) for k,a in zip(INPUTS,DEFAULT_ACTIONS)})

def validate(value):
    if not isinstance(value,dict) or value.get('schema')!=1 or value.get('device')!=DEVICE or value.get('layout')!='3x4':
        raise ValueError('配置必须为 1189:8840 的 3×4 控制键盘，schema=1')
    if set(value)-{'schema','device','layout','name','bindings'}:raise ValueError('配置包含未知字段')
    name=value.get('name','自定义布局')
    if not isinstance(name,str) or not name.strip() or len(name)>60:raise ValueError('配置名称需为 1～60 个字符')
    bindings=value.get('bindings')
    if not isinstance(bindings,dict) or set(bindings)!=set(INPUTS):raise ValueError('配置必须完整包含 12 个键及 6 个旋钮动作')
    out={}
    for key,bind in bindings.items():
        if not isinstance(bind,dict) or set(bind)!={'action','step'} or bind.get('action') not in BY_ACTION:
            raise ValueError(f'{key} 功能无效')
        step=bind['step'];maximum=BY_ACTION[bind['action']]['max_step']
        if isinstance(step,bool) or not isinstance(step,int) or not 1<=step<=maximum:
            raise ValueError(f'{key} 步长应为 1～{maximum} 的整数')
        out[key]=dict(action=bind['action'],step=step)
    return dict(schema=1,device=DEVICE,layout='3x4',name=name.strip(),bindings=out)

class MappingStore:
    def __init__(self,path):
        self.path=Path(path);self.error='';self.revision=0;self.value=defaults()
        if self.path.exists():
            try:self.value=validate(json.loads(self.path.read_text(encoding='utf8')))
            except (OSError,ValueError) as e:self.error=f'已使用默认配置，原配置文件保留：{e}'
    def snapshot(self):return copy.deepcopy(self.value)
    def reload(self):
        candidate=validate(json.loads(self.path.read_text(encoding='utf8'))) if self.path.exists() else defaults()
        if candidate!=self.value:self.revision+=1
        self.value=candidate;self.error='';return self.snapshot()
    def save(self,value):
        candidate=validate(value);self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        os.replace(temp,self.path);self.value=candidate;self.error='';self.revision+=1
        return self.snapshot()

VK_TO_INPUT={v:k for v,k in zip([70,75,88,32,13,68,83,65,44,8,87,124],KEYS)}
CTRL={17,162,163}

class KeypadInterpreter:
    """Emits physical IDs; F13/K12 triggers once on down, never on Ctrl or release.
    A 40 ms Ctrl tail only classifies reordered knob-A mouse-wheel reports.
    Only this device's Ctrl influences knob A; normal keyboard modifiers are ignored.
    """
    def __init__(self):self.reset()
    def reset(self):
        self.held=set();self.mouse=set();self.ctrl=False;self.ctrl_used=False;self.ctrl_release=None;self.wheel_remainder={'A':0,'B':0}
        self.blocked_keys=set();self.blocked_mouse=set();self.blocked_ctrl=False
    def suspend(self):
        keys=self.blocked_keys|self.held;mouse=self.blocked_mouse|self.mouse;ctrl=self.blocked_ctrl or self.ctrl
        self.reset();self.blocked_keys=keys;self.blocked_mouse=mouse;self.blocked_ctrl=ctrl
    def flush(self,now):
        if self.ctrl_release is not None and now-self.ctrl_release>=.04:
            self.ctrl_release=None
        return []
    def feed(self,event,now):
        collection=event.get('collection','').upper()
        if 'VID_1189&PID_8840&MI_01&' not in collection:return []
        out=self.flush(now);kind=event.get('type')
        if kind=='keyboard':
            vk=event.get('vkey');down=event.get('down')
            if vk in (0,255):return out
            if vk in CTRL:
                if self.blocked_ctrl:
                    if not down:self.blocked_ctrl=False
                    return out
                if down and not self.ctrl:
                    self.ctrl=True;self.ctrl_used=False;self.ctrl_release=None
                elif not down and self.ctrl:
                    self.ctrl=False;self.ctrl_release=now
                return out
            if vk in self.blocked_keys:
                if not down:self.blocked_keys.remove(vk)
                return out
            if self.ctrl or self.ctrl_release is not None:self.ctrl_used=True
            if vk==44 and not down:return out+[('K09',1)]
            if down:
                if vk not in self.held:
                    self.held.add(vk)
                    if vk in VK_TO_INPUT:out.append((VK_TO_INPUT[vk],1))
            else:self.held.discard(vk)
        elif kind=='wheel' and event.get('axis')=='vertical':
            if self.blocked_ctrl:return out
            delta=event.get('delta',0)
            if isinstance(delta,bool) or not isinstance(delta,int) or abs(delta)>120*64:return out
            a=self.ctrl or (self.ctrl_release is not None and now-self.ctrl_release<.04)
            if a:self.ctrl_used=True
            knob='A' if a else 'B';self.wheel_remainder[knob]+=delta
            n=int(self.wheel_remainder[knob]/120)
            self.wheel_remainder[knob]-=n*120
            if n:out.append((knob+('_CW' if n>0 else '_CCW'),abs(n)))
        elif kind=='mouse_button':
            name=event.get('button')
            if name in self.blocked_mouse:
                if not event.get('down'):self.blocked_mouse.remove(name)
                return out
            if self.ctrl or self.ctrl_release is not None:self.ctrl_used=True
            if event.get('down'):
                if name not in self.mouse:
                    self.mouse.add(name)
                    if name in ('Right','Left'):out.append(('A_PRESS' if name=='Right' else 'B_PRESS',1))
            else:self.mouse.discard(name)
        return out
