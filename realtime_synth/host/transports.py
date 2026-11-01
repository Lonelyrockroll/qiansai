"""Windows COM and FTDI D2XX transport; no pip packages or driver changes."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import os
import winreg

DLL_PATHS = [
    Path(os.environ.get('SYNTH_FTDI_DLL','')),
    Path(r'E:\Gowin_edu\Gowin_V1.9.11.03_Education_x64\Programmer\bin\ftd2xx.dll'),
    Path(r'E:\Gowin_edu\Gowin_V1.9.11.03_Education_x64\Programmer\bin\data\DLL\ftdi\x64\ftd2xx64.dll'),
]


class D2XX:
    def __init__(self):
        failures=[]
        for path in DLL_PATHS:
            if not path.is_file():
                continue
            try:
                self.dll=c.WinDLL(str(path));self.path=str(path);break
            except OSError as error:
                failures.append(str(error))
        else:
            raise OSError('找不到可用的 64 位 FTDI DLL。可使用 COM 方式，或设置 SYNTH_FTDI_DLL。'+';'.join(failures))
        specs={
            'FT_CreateDeviceInfoList':[c.POINTER(w.DWORD)],
            'FT_GetDeviceInfoDetail':[w.DWORD,*([c.POINTER(w.DWORD)]*4),c.c_void_p,c.c_void_p,c.POINTER(c.c_void_p)],
            'FT_OpenEx':[c.c_void_p,w.DWORD,c.POINTER(c.c_void_p)],
            'FT_Close':[c.c_void_p], 'FT_SetBaudRate':[c.c_void_p,w.DWORD],
            'FT_SetDataCharacteristics':[c.c_void_p,c.c_ubyte,c.c_ubyte,c.c_ubyte],
            'FT_SetFlowControl':[c.c_void_p,c.c_ushort,c.c_ubyte,c.c_ubyte],
            'FT_SetTimeouts':[c.c_void_p,w.DWORD,w.DWORD],
            'FT_SetBitMode':[c.c_void_p,c.c_ubyte,c.c_ubyte],
            'FT_Purge':[c.c_void_p,w.DWORD], 'FT_SetLatencyTimer':[c.c_void_p,c.c_ubyte],
            'FT_GetQueueStatus':[c.c_void_p,c.POINTER(w.DWORD)],
            'FT_Read':[c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)],
            'FT_Write':[c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)],
        }
        for name,args in specs.items():
            f=getattr(self.dll,name);f.argtypes=args;f.restype=w.DWORD

    def call(self,name,*args):
        status=getattr(self.dll,name)(*args)
        if status:
            raise OSError(f'{name} 失败，FTDI 状态 {status}；请关闭 Programmer 或其他串口程序再连接')

    def devices(self):
        count=w.DWORD();self.call('FT_CreateDeviceInfoList',c.byref(count));devices=[]
        for index in range(count.value):
            flags,kind,idcode,location=(w.DWORD() for _ in range(4))
            serial=c.create_string_buffer(64);description=c.create_string_buffer(128);handle=c.c_void_p()
            self.call('FT_GetDeviceInfoDetail',index,c.byref(flags),c.byref(kind),c.byref(idcode),
                      c.byref(location),serial,description,c.byref(handle))
            if idcode.value != 0x04036010:
                continue
            serial_text=serial.value.decode(errors='replace')
            if serial_text.endswith('A'):
                continue # Tang firmware channel A is the JTAG interface, not the synth UART.
            devices.append(dict(id=f'd2xx:{location.value}',label=f'FTDI 位置 {location.value} · '+description.value.decode(errors='replace'),
                                location=location.value,index=index,serial=serial_text,
                                preferred=serial_text.endswith('B'),opened=bool(flags.value&1)))
        return devices


class FtdiTransport:
    def __init__(self,location):
        self.api=D2XX();self.handle=c.c_void_p()
        self.api.call('FT_OpenEx',c.c_void_p(location),4,c.byref(self.handle)) # open by location, not unstable index
        try:
            for name,args in [('FT_SetBitMode',(0,0)),('FT_SetBaudRate',(115200,)),
                              ('FT_SetDataCharacteristics',(8,0,0)),('FT_SetFlowControl',(0,0,0)),
                              ('FT_SetTimeouts',(50,500)),('FT_SetLatencyTimer',(2,)),('FT_Purge',(3,))]:
                self.api.call(name,self.handle,*args)
        except Exception:
            self.close();raise

    def write(self,data):
        written=w.DWORD();buf=c.create_string_buffer(data)
        self.api.call('FT_Write',self.handle,buf,len(data),c.byref(written))
        if written.value!=len(data):raise OSError('串口写入不完整')

    def read(self):
        queued=w.DWORD();self.api.call('FT_GetQueueStatus',self.handle,c.byref(queued))
        if not queued.value:return b''
        size=min(queued.value,4096);buf=c.create_string_buffer(size);got=w.DWORD()
        self.api.call('FT_Read',self.handle,buf,size,c.byref(got));return buf.raw[:got.value]

    def close(self):
        if self.handle.value:
            self.api.call('FT_Close',self.handle);self.handle=c.c_void_p()


class DCB(c.Structure):
    _fields_=[('length',w.DWORD),('baud',w.DWORD),('flags',w.DWORD),('reserved',w.WORD),
              ('xonlim',w.WORD),('xofflim',w.WORD),('bytesize',c.c_ubyte),('parity',c.c_ubyte),
              ('stopbits',c.c_ubyte),('xonchar',c.c_char),('xoffchar',c.c_char),('errorchar',c.c_char),
              ('eofchar',c.c_char),('eventchar',c.c_char),('reserved1',w.WORD)]
class Timeouts(c.Structure):
    _fields_=[(name,w.DWORD) for name in ('interval','readmult','readconstant','writemult','writeconstant')]


class ComTransport:
    def __init__(self,port):
        self.api=c.WinDLL('kernel32',use_last_error=True)
        self.api.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
        self.api.CreateFileW.restype=w.HANDLE
        self.api.GetCommState.argtypes=[w.HANDLE,c.POINTER(DCB)]
        self.api.SetCommState.argtypes=[w.HANDLE,c.POINTER(DCB)]
        self.api.SetCommTimeouts.argtypes=[w.HANDLE,c.POINTER(Timeouts)]
        self.api.PurgeComm.argtypes=[w.HANDLE,w.DWORD]
        for name in ('ReadFile','WriteFile'):
            getattr(self.api,name).argtypes=[w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p]
        self.api.CloseHandle.argtypes=[w.HANDLE]
        self.handle=self.api.CreateFileW('\\\\.\\'+port,0xc0000000,0,None,3,0,None)
        if self.handle==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
        try:
            dcb=DCB();dcb.length=c.sizeof(DCB)
            self.check(self.api.GetCommState(self.handle,c.byref(dcb)))
            dcb.baud=115200;dcb.flags=1;dcb.bytesize=8;dcb.parity=0;dcb.stopbits=0
            self.check(self.api.SetCommState(self.handle,c.byref(dcb)))
            self.check(self.api.SetCommTimeouts(self.handle,c.byref(Timeouts(0xffffffff,0,0,0,500))))
            self.check(self.api.PurgeComm(self.handle,12))
        except Exception:self.close();raise

    def check(self,value):
        if not value:raise c.WinError(c.get_last_error())
    def write(self,data):
        buf=c.create_string_buffer(data);n=w.DWORD()
        self.check(self.api.WriteFile(self.handle,buf,len(data),c.byref(n),None))
        if n.value!=len(data):raise OSError('串口写入不完整')
    def read(self):
        buf=c.create_string_buffer(4096);n=w.DWORD()
        self.check(self.api.ReadFile(self.handle,buf,len(buf),c.byref(n),None));return buf.raw[:n.value]
    def close(self):
        if self.handle is not None:self.api.CloseHandle(self.handle);self.handle=None


def list_devices():
    devices=[];warnings=[]
    roles={}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Enum\FTDIBUS') as parent:
            for index in range(winreg.QueryInfoKey(parent)[0]):
                name=winreg.EnumKey(parent,index)
                if 'VID_0403+PID_6010+' not in name:continue
                try:
                    with winreg.OpenKey(parent,name+r'\0000\Device Parameters') as params:
                        port=winreg.QueryValueEx(params,'PortName')[0]
                        roles[port]=name[-1:]
                except OSError:pass
    except OSError:pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DEVICEMAP\SERIALCOMM') as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                _,port,_=winreg.EnumValue(key,index)
                if roles.get(port)=='A':continue
                devices.append(dict(id='com:'+port,label=port+(' · FPGA UART（B 通道）' if roles.get(port)=='B' else ' · Windows 串口'),
                                    preferred=roles.get(port)=='B'))
    except FileNotFoundError:pass
    try:devices.extend(D2XX().devices())
    except OSError as error:warnings.append(str(error))
    return devices,warnings


def open_device(identifier):
    if identifier.startswith('d2xx:'):return FtdiTransport(int(identifier.split(':')[1]))
    if identifier.startswith('com:') and identifier[4:].startswith('COM') and identifier[7:].isdigit():
        return ComTransport(identifier[4:])
    raise ValueError('请选择检测到的串口设备')
