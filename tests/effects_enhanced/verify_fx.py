"""Exercise the enhanced effects against an independent integer recurrence."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

import numpy as np

from reference import Effects,FS

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT.parent/'tmp/effects_enhance/sim'
WORK.mkdir(parents=True,exist_ok=True)
sets=[
    (dict(mask=0),np.array([(((i*433)^0x52a7)&32767)-16384 for i in range(2048)])),
    (dict(mask=2,d=128,time=3,feedback=112),np.r_[12000,np.zeros(40000,dtype=int)]),
    (dict(mask=1,r=128,room=2),np.r_[12000,np.zeros(60000,dtype=int)]),
    (dict(mask=4,c=128,rate=2,depth=2),np.rint(10000*np.sin(2*np.pi*523.251*np.arange(65000)/FS))),
    (dict(mask=7,r=64,d=64,c=112,time=3,room=2,feedback=112,rate=2,depth=2),np.r_[12000,np.zeros(60000,dtype=int)]),
]
inputs=[];gold=[]
for params,samples in sets:
    ref=Effects(**params)
    for _ in range(100):ref.step(0)
    inputs.extend(samples.astype(int))
    gold.extend(ref.step(int(x)) for x in samples)
(WORK/'samples.hex').write_text(''.join(f'{int(x)&65535:04x}\n' for x in inputs))
config=[]
for i,(p,values) in enumerate(sets):
    setting=dict(mask=0,r=0,d=0,c=0,time=1,feedback=96,room=1,rate=1,depth=1)
    setting.update(p)
    config.append(f"{i}:begin n={len(values)};"+''.join(f'{k}={v};' for k,v in setting.items())+'end')
tb="""`timescale 1ns/1ps
module tb;
reg clk=0;always #10 clk=~clk;
reg rst=1,tick=0,clear=0,cv=0,en=1;reg signed [15:0] x=0;
reg [2:0] mask=0;reg [7:0] r=0,d=0,c=0,feedback=96;
reg [1:0] tm=1,room=1,rate=1,depth=1;
wire signed [15:0] y;wire valid,pending,overrun,clipped;
audio_effects dut(.clk(clk),.rst(rst),.clear(clear),.sample_tick(tick),.audio_enable(en),.dry_pcm(x),
 .cfg_valid(cv),.cfg_mask(mask),.cfg_reverb_mix(r),.cfg_delay_mix(d),.cfg_chorus_mix(c),
 .cfg_feedback(feedback),.cfg_delay_time(tm),.cfg_room(room),.cfg_rate(rate),.cfg_depth(depth),
 .pcm(y),.valid(valid),.pending(pending),.overrun(overrun),.clipped(clipped));
reg [15:0] data[0:TOTAL-1];integer i,j,n,offset=0,fd,cycles,maximum=0;
task frame(input signed [15:0] v,input wr);begin
 @(negedge clk);x=v;tick=1;@(negedge clk);tick=0;cycles=0;
 while(!valid)begin @(negedge clk);cycles=cycles+1;if(cycles>120)$fatal(1,"missed frame");end
 if(cycles>maximum)maximum=cycles;
 if(^y===1'bx || overrun || clipped)$fatal(1,"invalid output at case %0d sample %0d",i,j);
 if(wr)$fwrite(fd,"%c%c",y[7:0],y[15:8]);
 repeat(5)@(negedge clk);
end endtask
initial begin
 fd=$fopen("output.pcm","wb");$readmemh("samples.hex",data);
 for(i=0;i<5;i=i+1)begin
  rst=1;tick=0;cv=0;en=1;repeat(5)@(negedge clk);rst=0;
  case(i)
  CONFIG
  endcase
  cv=1;@(negedge clk);cv=0;frame(0,0);
  for(j=0;j<100;j=j+1)frame(0,0);
  for(j=0;j<n;j=j+1)frame(data[offset+j],1);
  offset=offset+n;
  clear=1;@(negedge clk);clear=0;
  for(j=0;j<200;j=j+1)begin frame(0,0);if(y!=0)$fatal(1,"old tail after clear");end
 end
 $fclose(fd);$display("PASS exact FX samples=%0d max clocks=%0d",offset,maximum);$finish;
end
endmodule
""".replace('TOTAL',str(len(inputs))).replace('CONFIG','\n'.join(config).replace('time=','tm='))
(WORK/'tb.v').write_text(tb)
subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-s','tb','-o',str(WORK/'fx.vvp'),
                str(ROOT/'fpga/audio_effects.v'),str(ROOT/'fpga/chorus_lfo.v'),str(WORK/'tb.v')],check=True)
proc=subprocess.run(['E:/iverilog/bin/vvp.exe','fx.vvp'],cwd=WORK,capture_output=True,text=True,timeout=600)
print(proc.stdout,proc.stderr);proc.check_returncode()
actual=np.fromfile(WORK/'output.pcm',dtype='<i2')
np.testing.assert_array_equal(actual,np.asarray(gold))
report={'passed':True,'samples':len(actual),'clip_count':0,'sources':{n:hashlib.sha256((ROOT/'fpga'/n).read_bytes()).hexdigest() for n in ('audio_effects.v','chorus_lfo.v')},'cases':[]}
start=0
for p,s in sets:
    y=actual[start:start+len(s)];start+=len(s)
    report['cases'].append({'settings':p,'peak':int(np.max(abs(y.astype(np.int64)))),'late_peak':int(np.max(abs(y[-5000:].astype(np.int64))))})
(WORK/'reference_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
