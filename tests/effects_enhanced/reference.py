"""Integer reference for the full-rate FPGA effects; used only for verification."""
import math
FS=50e6/1024
LENGTHS=[631,761,887,1013,127,239]
PHASE_STEPS=[21990,39582,70369,105553]
LFO=[round(127*math.sin(2*math.pi*i/128)) for i in range(128)]
def div0(x,bits):return -(abs(int(x))>>bits) if x<0 else int(x)>>bits
def sat16(x):return max(-32768,min(32767,int(x)))
def sat18(x):return max(-131072,min(131071,int(x)))
def approach(a,b):return min(b,a+4) if a<b else max(b,a-4)

class Effects:
 def __init__(self,mask=0,r=0,d=0,c=0,time=1,feedback=96,room=1,rate=1,depth=1):
  self.mask=mask;self.r=r;self.d=d;self.c=c;self.time=time;self.feedback=feedback;self.room=room;self.rate=rate;self.depth=depth
  self.rm=self.dm=self.cm=0;self.mute=0;self.phase=0
  # The command-consumption frame processes one zero sample after clearing
  # history, before the caller's first frame. Include its validity counters.
  self.half=1;self.previous_input=0;self.previous_tap=0;self.clipped_count=0
  self.ch=[0]*1024;self.de=[0]*8191+[0];self.rv=[[0]*n for n in LENGTHS]
  self.cp=self.dp=self.da=0;self.ca=1;self.rp=[0]*6;self.ra=[1]*6;self.lp=[0]*4
 def step(self,x,enable=True):
  self.mute=min(256,self.mute+32) if enable else max(0,self.mute-32)
  index=(self.phase>>25)&127;frac=(self.phase>>17)&255
  lfo=LFO[index]*256+(LFO[(index+1)&127]-LFO[index])*frac
  delta=lfo>>1 if self.depth==0 else lfo if self.depth==1 else (lfo*3)>>1 if self.depth==2 else lfo*2
  q=131072+delta;dist=q>>8;fraction=q&255
  distance=[1953,3906,5859,7813][self.time]
  self.rm=approach(self.rm,self.r if self.mask&1 and self.ra[3]>=1013 else 0)
  self.dm=approach(self.dm,self.d if self.mask&2 and self.da>=distance else 0)
  self.cm=approach(self.cm,self.c if self.mask&4 and self.ca>dist else 0)
  self.phase=(self.phase+PHASE_STEPS[self.rate])&0xffffffff
  c0=self.ch[(self.cp-dist)&1023] if self.ca>=dist else 0
  c1=self.ch[(self.cp-dist-1)&1023] if self.ca>dist else 0
  ct=sat16(div0(c0*(256-fraction)+c1*fraction,8))
  ch=sat16(div0(x*(256-self.cm)+ct*self.cm,8));self.ch[self.cp]=x;self.cp=(self.cp+1)&1023;self.ca=min(1024,self.ca+1)
  distance=[1953,3906,5859,7813][self.time]
  dt=self.de[(self.dp-distance)&8191] if self.da>=distance else 0
  wet=dt if self.half else div0(dt+self.previous_tap,1)
  if self.half:
   averaged=div0(ch+self.previous_input,1)
   self.de[self.dp]=sat16(div0(averaged*(256-self.feedback)+dt*self.feedback,8))
   self.dp=(self.dp+1)&8191;self.da=min(8192,self.da+1);self.previous_tap=dt
  self.previous_input=ch;self.half^=1
  g=[224,240,248][self.room];total=0
  for i in range(4):
   tap=self.rv[i][self.rp[i]] if self.ra[i]>=LENGTHS[i] else 0
   self.lp[i]=sat18(div0(tap+self.lp[i],1))
   self.rv[i][self.rp[i]]=sat18(div0(ch*(256-g)+self.lp[i]*g,8))
   total+=tap;self.rp[i]=(self.rp[i]+1)%LENGTHS[i];self.ra[i]=min(LENGTHS[i],self.ra[i]+1)
  ap=div0(total,2)
  for i in range(4,6):
   tap=self.rv[i][self.rp[i]] if self.ra[i]>=LENGTHS[i] else 0
   y=tap-div0(ap,1);self.rv[i][self.rp[i]]=sat18(ap+div0(y,1));ap=y
   self.rp[i]=(self.rp[i]+1)%LENGTHS[i];self.ra[i]=min(LENGTHS[i],self.ra[i]+1)
  value=div0(ch*(256-self.dm-self.rm)+wet*self.dm+ap*2*self.rm,8)
  gain=256 if self.mask==0 and not(self.rm or self.dm or self.cm) else self.mute
  output=div0(value*gain,8)
  self.clipped_count+=int(output>32767 or output< -32768)
  return sat16(output)
