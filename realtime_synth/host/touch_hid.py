"""Windows Raw Input touchscreen reader. Only the selected USB HID is decoded.

Uses the Windows HID parser, not guessed byte offsets or a replacement driver.
No keyboard/mouse registration, input injection, or global hooks.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import threading
import time

VID_PID='VID_0483&PID_5750'
user32=C.WinDLL('user32',use_last_error=True)
hid=C.WinDLL('hid',use_last_error=True)
U8=C.c_ubyte;U16=C.c_ushort;U32=C.c_uint32;I32=C.c_int32
PTR=C.c_void_p
SUCCESS=0x00110000

class DeviceList(C.Structure):
    _fields_=[('handle',PTR),('kind',U32)]
class Caps(C.Structure):
    _fields_=[('Usage',U16),('UsagePage',U16),('InputReportByteLength',U16),
        ('OutputReportByteLength',U16),('FeatureReportByteLength',U16),('Reserved',U16*17),
        ('NumberLinkCollectionNodes',U16),('NumberInputButtonCaps',U16),('NumberInputValueCaps',U16),
        ('NumberInputDataIndices',U16),('NumberOutputButtonCaps',U16),('NumberOutputValueCaps',U16),
        ('NumberOutputDataIndices',U16),('NumberFeatureButtonCaps',U16),('NumberFeatureValueCaps',U16),
        ('NumberFeatureDataIndices',U16)]
class Range(C.Structure):
    _fields_=[('UsageMin',U16),('UsageMax',U16),('StringMin',U16),('StringMax',U16),
        ('DesignatorMin',U16),('DesignatorMax',U16),('DataIndexMin',U16),('DataIndexMax',U16)]
class NotRange(C.Structure):
    _fields_=[('Usage',U16),('Reserved1',U16),('StringIndex',U16),('Reserved2',U16),
        ('DesignatorIndex',U16),('Reserved3',U16),('DataIndex',U16),('Reserved4',U16)]
class CapUnion(C.Union):
    _fields_=[('Range',Range),('NotRange',NotRange)]
COMMON=[('UsagePage',U16),('ReportID',U8),('IsAlias',U8),('BitField',U16),
        ('LinkCollection',U16),('LinkUsage',U16),('LinkUsagePage',U16),
        ('IsRange',U8),('IsStringRange',U8),('IsDesignatorRange',U8),('IsAbsolute',U8)]
class ValueCaps(C.Structure):
    _fields_=COMMON+[('HasNull',U8),('Reserved',U8),('BitSize',U16),('ReportCount',U16),
        ('Reserved2',U16*5),('UnitsExp',U32),('Units',U32),('LogicalMin',I32),('LogicalMax',I32),
        ('PhysicalMin',I32),('PhysicalMax',I32),('u',CapUnion)]
class ButtonCaps(C.Structure):
    _fields_=COMMON+[('ReportCount',U16),('Reserved2',U16),('Reserved',U32*9),('u',CapUnion)]
assert C.sizeof(Caps)==64 and C.sizeof(ValueCaps)==72 and C.sizeof(ButtonCaps)==72

user32.GetRawInputDeviceList.argtypes=[PTR,C.POINTER(U32),U32];user32.GetRawInputDeviceList.restype=U32
user32.GetRawInputDeviceInfoW.argtypes=[PTR,U32,PTR,C.POINTER(U32)];user32.GetRawInputDeviceInfoW.restype=U32
hid.HidP_GetCaps.argtypes=[PTR,C.POINTER(Caps)];hid.HidP_GetCaps.restype=U32
hid.HidP_GetValueCaps.argtypes=[C.c_int,PTR,C.POINTER(U16),PTR];hid.HidP_GetValueCaps.restype=U32
hid.HidP_GetButtonCaps.argtypes=[C.c_int,PTR,C.POINTER(U16),PTR];hid.HidP_GetButtonCaps.restype=U32
hid.HidP_GetUsageValue.argtypes=[C.c_int,U16,U16,U16,C.POINTER(U32),PTR,PTR,U32];hid.HidP_GetUsageValue.restype=U32
hid.HidP_GetUsages.argtypes=[C.c_int,U16,U16,PTR,C.POINTER(U32),PTR,PTR,U32];hid.HidP_GetUsages.restype=U32

def require(code):
    if code==0xffffffff:raise C.WinError(C.get_last_error())
    return code
def hid_ok(code):
    if code!=SUCCESS:raise OSError(f'HID parser status 0x{code:08x}')
def usages(cap):
    return range(cap.u.Range.UsageMin,cap.u.Range.UsageMax+1) if cap.IsRange else [cap.u.NotRange.Usage]
def cap_record(cap):
    result={name:int(getattr(cap,name)) for name in ('UsagePage','ReportID','LinkCollection','LinkUsage','LinkUsagePage','IsAbsolute')}
    result['Usages']=list(usages(cap))
    if isinstance(cap,ValueCaps):result.update({name:int(getattr(cap,name)) for name in ('BitSize','ReportCount','LogicalMin','LogicalMax')})
    return result

class TouchDevice:
    def __init__(self,handle,path):
        self.handle=handle;self.path=path
        size=U32();require(user32.GetRawInputDeviceInfoW(handle,0x20000005,None,C.byref(size)))
        self.preparsed=C.create_string_buffer(size.value)
        require(user32.GetRawInputDeviceInfoW(handle,0x20000005,self.preparsed,C.byref(size)))
        self.caps=Caps();hid_ok(hid.HidP_GetCaps(self.preparsed,C.byref(self.caps)))
        self.values=(ValueCaps*self.caps.NumberInputValueCaps)();n=U16(len(self.values))
        if n.value:hid_ok(hid.HidP_GetValueCaps(0,self.values,C.byref(n),self.preparsed))
        self.buttons=(ButtonCaps*self.caps.NumberInputButtonCaps)();n=U16(len(self.buttons))
        if n.value:hid_ok(hid.HidP_GetButtonCaps(0,self.buttons,C.byref(n),self.preparsed))
    def describe(self):
        return dict(path=self.path,usage_page=self.caps.UsagePage,usage=self.caps.Usage,
            input_report_bytes=self.caps.InputReportByteLength,
            values=[cap_record(c) for c in self.values],buttons=[cap_record(c) for c in self.buttons])
    def decode(self,raw):
        report=C.create_string_buffer(raw);report_id=raw[0];groups={};meta={}
        for cap in self.values:
            if cap.ReportID!=report_id:continue
            for usage in usages(cap):
                val=U32();code=hid.HidP_GetUsageValue(0,cap.UsagePage,cap.LinkCollection,usage,C.byref(val),self.preparsed,report,len(raw))
                if code!=SUCCESS:continue
                g=groups.setdefault(cap.LinkCollection,{})
                if cap.UsagePage==1 and usage in (0x30,0x31):
                    axis='x' if usage==0x30 else 'y';g[axis]=val.value;g[axis+'_min']=cap.LogicalMin;g[axis+'_max']=cap.LogicalMax
                elif cap.UsagePage==13 and usage==0x51:g['id']=val.value
                elif cap.UsagePage==13 and usage==0x54:meta['contact_count']=val.value
                elif cap.UsagePage==13 and usage==0x56:meta['scan_time']=val.value
        for cap in self.buttons:
            if cap.ReportID!=report_id or cap.UsagePage!=13:continue
            a=(U16*32)();n=U32(32)
            code=hid.HidP_GetUsages(0,13,cap.LinkCollection,a,C.byref(n),self.preparsed,report,len(raw))
            if code==SUCCESS:
                g=groups.setdefault(cap.LinkCollection,{})
                # Digitizers Tip Switch = 0x42. In Range alone is not a press.
                if 0x42 in usages(cap):g['down']=0x42 in a[:n.value]
        contacts=[dict(collection=k,**v) for k,v in groups.items() if 'x' in v and 'y' in v and 'down' in v]
        return dict(report_id=report_id,contacts=contacts,**meta)

def enumerate_touch_devices(match=VID_PID):
    n=U32();require(user32.GetRawInputDeviceList(None,C.byref(n),C.sizeof(DeviceList)))
    devices=(DeviceList*n.value)();require(user32.GetRawInputDeviceList(devices,C.byref(n),C.sizeof(DeviceList)))
    found=[]
    for item in devices[:n.value]:
        if item.kind!=2:continue
        size=U32();require(user32.GetRawInputDeviceInfoW(item.handle,0x20000007,None,C.byref(size)))
        path=C.create_unicode_buffer(size.value+1);require(user32.GetRawInputDeviceInfoW(item.handle,0x20000007,path,C.byref(size)))
        if match.upper() not in path.value.upper():continue
        device=TouchDevice(item.handle,path.value)
        if device.caps.UsagePage==13 and device.caps.Usage==4:found.append(device)
    return found

class RawHeader(C.Structure):
    _fields_=[('kind',U32),('size',U32),('device',PTR),('wparam',C.c_size_t)]
class RawRegistration(C.Structure):
    _fields_=[('page',U16),('usage',U16),('flags',U32),('target',PTR)]
WndProc=C.WINFUNCTYPE(C.c_ssize_t,PTR,U32,C.c_size_t,C.c_ssize_t)
class WndClass(C.Structure):
    _fields_=[('style',U32),('proc',WndProc),('cls_extra',C.c_int),('win_extra',C.c_int),
        ('instance',PTR),('icon',PTR),('cursor',PTR),('background',PTR),('menu',W.LPCWSTR),('name',W.LPCWSTR)]
kernel=C.WinDLL('kernel32',use_last_error=True)
kernel.GetModuleHandleW.argtypes=[W.LPCWSTR];kernel.GetModuleHandleW.restype=PTR
user32.RegisterClassW.argtypes=[C.POINTER(WndClass)];user32.RegisterClassW.restype=U16
user32.UnregisterClassW.argtypes=[W.LPCWSTR,PTR];user32.UnregisterClassW.restype=W.BOOL
user32.CreateWindowExW.argtypes=[U32,W.LPCWSTR,W.LPCWSTR,U32,C.c_int,C.c_int,C.c_int,C.c_int,PTR,PTR,PTR,PTR];user32.CreateWindowExW.restype=PTR
user32.DefWindowProcW.argtypes=[PTR,U32,C.c_size_t,C.c_ssize_t];user32.DefWindowProcW.restype=C.c_ssize_t
user32.RegisterRawInputDevices.argtypes=[PTR,U32,U32];user32.RegisterRawInputDevices.restype=W.BOOL
user32.GetRawInputData.argtypes=[PTR,U32,PTR,C.POINTER(U32),U32];user32.GetRawInputData.restype=U32
user32.GetMessageW.argtypes=[C.POINTER(W.MSG),PTR,U32,U32];user32.GetMessageW.restype=C.c_int
user32.TranslateMessage.argtypes=[C.POINTER(W.MSG)];user32.DispatchMessageW.argtypes=[C.POINTER(W.MSG)];user32.DispatchMessageW.restype=C.c_ssize_t
user32.PostMessageW.argtypes=[PTR,U32,C.c_size_t,C.c_ssize_t];user32.PostMessageW.restype=W.BOOL
user32.DestroyWindow.argtypes=[PTR];user32.PostQuitMessage.argtypes=[C.c_int]

class RawTouchReader:
    def __init__(self,callback,match=VID_PID):
        self.callback=callback;self.match=match;self.ready=threading.Event();self.stopped=threading.Event()
        self.error='';self.hwnd=None;self.devices={};self.count=0;self.last_seen=0
    def start(self):
        self.thread=threading.Thread(target=self._run,name='touch-raw-input',daemon=True);self.thread.start()
        if not self.ready.wait(3):raise TimeoutError('USB touch receiver startup')
        if self.error:raise OSError(self.error)
    def stop(self):
        if self.hwnd:user32.PostMessageW(self.hwnd,0x10,0,0)
        if hasattr(self,'thread'):self.thread.join(2)
    def refresh(self):
        self.devices={d.handle:d for d in enumerate_touch_devices(self.match)}
    def _raw(self,lparam):
        size=U32();require(user32.GetRawInputData(lparam,0x10000003,None,C.byref(size),C.sizeof(RawHeader)))
        if not C.sizeof(RawHeader)+8<=size.value<=65536:return
        buf=C.create_string_buffer(size.value)
        require(user32.GetRawInputData(lparam,0x10000003,buf,C.byref(size),C.sizeof(RawHeader)))
        h=RawHeader.from_buffer(buf)
        if h.kind!=2 or h.device not in self.devices:return
        off=C.sizeof(RawHeader);data=buf.raw
        length=int.from_bytes(data[off:off+4],'little');count=int.from_bytes(data[off+4:off+8],'little')
        if not length or count>256 or off+8+length*count>size.value:return
        device=self.devices[h.device]
        if length!=device.caps.InputReportByteLength:return
        for i in range(count):
            raw=data[off+8+i*length:off+8+(i+1)*length]
            decoded=device.decode(raw);self.count+=1;self.last_seen=time.monotonic()
            self.callback(dict(time=self.last_seen,path=device.path,raw_hex=raw.hex(),**decoded))
    def _run(self):
        instance=kernel.GetModuleHandleW(None);name=f'TangTouch_{id(self):x}'
        @WndProc
        def proc(hwnd,msg,wp,lp):
            try:
                if msg==0xff:self._raw(lp)
                elif msg==0xfe:
                    self.refresh();self.callback(dict(time=time.monotonic(),device_change=True,connected=bool(self.devices)))
                elif msg==0x10:user32.DestroyWindow(hwnd);return 0
                elif msg==2:self.hwnd=None;user32.PostQuitMessage(0);return 0
            except Exception as e:self.error=str(e)
            return user32.DefWindowProcW(hwnd,msg,wp,lp)
        self._proc=proc
        wc=WndClass();wc.proc=proc;wc.instance=instance;wc.name=name
        registered=False
        try:
            self.refresh()
            if len(self.devices)!=1:raise OSError(f'需要唯一的 {self.match} USB 触摸屏，当前找到 {len(self.devices)} 个')
            if not user32.RegisterClassW(C.byref(wc)):raise C.WinError(C.get_last_error())
            registered=True
            self.hwnd=user32.CreateWindowExW(0,name,'Tang touch receiver',0,0,0,0,0,PTR(-3),None,instance,None)
            if not self.hwnd:raise C.WinError(C.get_last_error())
            reg=RawRegistration(13,4,0x100|0x2000,self.hwnd) # INPUTSINK + DEVNOTIFY
            if not user32.RegisterRawInputDevices(C.byref(reg),1,C.sizeof(reg)):raise C.WinError(C.get_last_error())
            self.ready.set();msg=W.MSG()
            while True:
                status=user32.GetMessageW(C.byref(msg),None,0,0)
                if status==0:break
                if status<0:raise C.WinError(C.get_last_error())
                user32.TranslateMessage(C.byref(msg));user32.DispatchMessageW(C.byref(msg))
        except Exception as e:self.error=str(e);self.ready.set()
        finally:
            reg=RawRegistration(13,4,1,None) # remove only this process's registration
            user32.RegisterRawInputDevices(C.byref(reg),1,C.sizeof(reg))
            if self.hwnd:user32.DestroyWindow(self.hwnd);self.hwnd=None
            if registered:user32.UnregisterClassW(name,instance)
            self.stopped.set()

if __name__=='__main__':
    print(json.dumps([d.describe() for d in enumerate_touch_devices()],ensure_ascii=False,indent=2))
