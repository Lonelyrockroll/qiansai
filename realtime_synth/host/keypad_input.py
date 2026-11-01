"""Dedicated 1189:8840 foreground Raw Input receiver, extracted from verified v5 tester.
Native callback only queues events; Tk, callbacks and I/O run after the callback returns.
No INPUTSINK, global hooks, key injection or device configuration writes.
"""
import ctypes as C,os,time,threading,collections
from ctypes import wintypes as W
import touch_hid as api
PTR=C.c_void_p;U16=C.c_ushort;U32=C.c_uint32
u=api.user32
u.GetForegroundWindow.argtypes=[];u.GetForegroundWindow.restype=PTR
u.GetAncestor.argtypes=[PTR,U32];u.GetAncestor.restype=PTR
class Keyboard(C.Structure):
 _fields_=[('scan',U16),('flags',U16),('reserved',U16),('vkey',U16),('message',U32),('extra',U32)]
class MouseButtons(C.Structure):_fields_=[('flags',U16),('data',U16)]
class MouseUnion(C.Union):_fields_=[('buttons',U32),('parts',MouseButtons)]
class Mouse(C.Structure):
 _fields_=[('flags',U16),('u',MouseUnion),('raw_buttons',U32),('x',C.c_int32),('y',C.c_int32),('extra',U32)]
assert C.sizeof(Keyboard)==16 and C.sizeof(Mouse)==24
KEY_NAMES={8:'Backspace',9:'Tab',13:'Enter',16:'Shift',17:'Ctrl',18:'Alt',27:'Escape',32:'Space',
 33:'PageUp',34:'PageDown',35:'End',36:'Home',37:'Left',38:'Up',39:'Right',40:'Down',44:'PrintScreen',45:'Insert',46:'Delete',91:'LeftWin',92:'RightWin',
 160:'LeftShift',161:'RightShift',162:'LeftCtrl',163:'RightCtrl',164:'LeftAlt',165:'RightAlt',173:'Mute',174:'VolumeDown',175:'VolumeUp'}
MODS={16,17,18,91,92,160,161,162,163,164,165}

def key_name(k):
 if 48<=k<=90:return chr(k)
 if 112<=k<=135:return 'F'+str(k-111)
 if 96<=k<=105:return 'Num'+str(k-96)
 return KEY_NAMES.get(k,f'VK_{k:02X}')
def decode_keyboard(raw):
 k=Keyboard.from_buffer_copy(raw[:16]);down=not bool(k.flags&1)
 return {'type':'keyboard','vkey':k.vkey,'key':key_name(k.vkey),'scan_code':k.scan,'flags':k.flags,'down':down,'modifier':k.vkey in MODS}
def decode_mouse(raw):
 m=Mouse.from_buffer_copy(raw[:24]);f=m.u.parts.flags;events=[]
 for down_bit,up_bit,name in [(1,2,'Left'),(4,8,'Right'),(16,32,'Middle'),(64,128,'X1'),(256,512,'X2')]:
  if f&down_bit:events.append({'type':'mouse_button','button':name,'down':True})
  if f&up_bit:events.append({'type':'mouse_button','button':name,'down':False})
 for bit,axis in [(0x400,'vertical'),(0x800,'horizontal')]:
  if f&bit:events.append({'type':'wheel','axis':axis,'delta':C.c_int16(m.u.parts.data).value})
 return events

class KeypadReceiver:
 def __init__(self,root,callback,enabled,generation=lambda:0,test_mode=False):
  self.root=root;self.callback=callback;self.enabled=enabled;self.generation=generation;self.test_mode=test_mode
  self.devices={};self.closed=False;self.events=collections.deque();self.native_depth=0;self.needs_refresh=False
  self.raw_messages=0;self.target_events=0;self.dropped_events=0;self.test_callbacks=0;self.gui_thread=threading.get_ident();self.last_control_input=0
  root.update();self.hwnd=u.GetAncestor(PTR(root.winfo_id()),2);self.refresh()
  self.instance=api.kernel.GetModuleHandleW(None);self.class_name='KeypadNativeInput_'+str(os.getpid())+'_'+str(id(self))
  @api.WndProc
  def proc(hwnd,msg,wp,lp):
   self.native_depth+=1
   try:
    # This is an independent message-only window: never call Tk, its WndProc,
    # GUI callbacks or file I/O from this native callback.
    if msg==0xff:
     self.raw_messages+=1
     if self.enabled(wp):self.raw(lp)
    elif msg==0xfe:self.needs_refresh=True
    elif self.test_mode and msg==0x802a:
     self.test_callbacks+=1;self.enqueue(dict(self.test_fixture),self.generation())
   except Exception as e:self.enqueue({'type':'receiver_error','error':str(e)},self.generation())
   finally:self.native_depth-=1
   return u.DefWindowProcW(hwnd,msg,wp,lp)
  self.proc=proc
  wc=api.WndClass();wc.proc=proc;wc.instance=self.instance;wc.name=self.class_name
  if not u.RegisterClassW(C.byref(wc)):raise C.WinError(C.get_last_error())
  self.raw_hwnd=u.CreateWindowExW(0,self.class_name,'Keypad native input receiver',0,0,0,0,0,PTR(-3),None,self.instance,None)
  if not self.raw_hwnd:raise C.WinError(C.get_last_error())
  # Foreground delivery only. No INPUTSINK, keyboard hooks or input suppression.
  if not test_mode:
   self.regs=(api.RawRegistration*3)(*[api.RawRegistration(p,v,0x2000,self.raw_hwnd) for p,v in [(1,6),(1,2),(12,1)]])
   if not u.RegisterRawInputDevices(self.regs,3,C.sizeof(api.RawRegistration)):raise C.WinError(C.get_last_error())
 def enqueue(self,event,generation):
  if len(self.events)>=2048:self.dropped_events+=1;return
  event['time']=time.monotonic()
  event['_generation']=generation;self.events.append(event)
 def drain(self):
  assert threading.get_ident()==self.gui_thread and self.native_depth==0
  if self.needs_refresh:self.needs_refresh=False;self.refresh()
  for _ in range(min(256,len(self.events))):
   e=self.events.popleft()
   if e.pop('_generation')==self.generation():self.callback(e)
 def refresh(self):
  n=U32();api.require(u.GetRawInputDeviceList(None,C.byref(n),C.sizeof(api.DeviceList)))
  a=(api.DeviceList*n.value)();api.require(u.GetRawInputDeviceList(a,C.byref(n),C.sizeof(api.DeviceList)))
  devices={}
  for item in a[:n.value]:
   length=U32()
   if u.GetRawInputDeviceInfoW(item.handle,0x20000007,None,C.byref(length))==0xffffffff:continue
   b=C.create_unicode_buffer(length.value+1)
   if u.GetRawInputDeviceInfoW(item.handle,0x20000007,b,C.byref(length))==0xffffffff:continue
   if 'VID_1189&PID_8840' in b.value.upper():devices[item.handle]={'path':b.value,'kind':item.kind}
  self.devices=devices
 def raw(self,lp):
  generation=self.generation()
  n=U32();api.require(u.GetRawInputData(lp,0x10000003,None,C.byref(n),C.sizeof(api.RawHeader)))
  if not C.sizeof(api.RawHeader)<=n.value<=8192:return
  b=C.create_string_buffer(n.value);api.require(u.GetRawInputData(lp,0x10000003,b,C.byref(n),C.sizeof(api.RawHeader)))
  header=api.RawHeader.from_buffer(b)
  if header.device not in self.devices:return
  raw=b.raw[C.sizeof(api.RawHeader):];dev=self.devices[header.device]
  if header.kind==1:events=[decode_keyboard(raw)]
  elif header.kind==0:events=decode_mouse(raw) # Ignore pointer motion completely.
  elif header.kind==2:
   if len(raw)<8:return
   length=int.from_bytes(raw[:4],'little');count=int.from_bytes(raw[4:8],'little')
   if not length or count>64 or 8+length*count>len(raw):return
   events=[{'type':'consumer_report','raw_hex':raw[8+i*length:8+(i+1)*length].hex()} for i in range(count)]
  else:return
  for e in events:
   # Guard legacy button activation immediately; GUI queue draining is later.
   if e['type']=='mouse_button' or (e['type']=='keyboard' and e['vkey'] in (13,32)):self.last_control_input=time.monotonic()
   e['collection']=dev['path'].split('#')[1].upper();self.target_events+=1;self.enqueue(e,generation)
 def stop(self):
  if self.closed:return
  self.closed=True
  if not self.test_mode:
   regs=(api.RawRegistration*3)(*[api.RawRegistration(p,v,1,None) for p,v in [(1,6),(1,2),(12,1)]])
   u.RegisterRawInputDevices(regs,3,C.sizeof(api.RawRegistration))
  u.DestroyWindow(self.raw_hwnd);u.UnregisterClassW(self.class_name,self.instance)
