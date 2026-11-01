"""Exercise the v22 controls and performance bench against the actual v26 RTL list."""
from pathlib import Path
import subprocess,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parent;S=R/'sim';S.mkdir(exist_ok=True)
base=R.parent/'control_key_gain';prev=R.parent/'control_pmod_bt'
sys.path.insert(0,str(R.parent/'host'))
from protocol import packet,voice_payload,WHITE_KEYS
performance=(base/'tb_performance_system.v').read_text().replace('input [2:0] focus,timbre','input [3:0] focus,input [2:0] fx,timbre').replace(".uart_rx(1'b1)",".bt_rx(1'b1),.uart_rx(1'b1)")
(S/'performance.v').write_text(performance)
links=(prev/'tb_links.v').read_text().replace('j*28+24]!=22','j*28+24]!=26')
start='  for(i=0;i<8;i=i+1)begin wait(dut.indicators.testing'
assert links.count(start)==1
links=links.replace(start,"""  // The normal silent output is dark, including after boot. Force only the audio
  // bus/mute here to verify the actual top-level tap, then request the old chase.
  @(negedge clk);if(dut.pmod_testing || leds!==8'hff)$fatal(1,"meter idle");
  force dut.PA_EN=0;force dut.pcm=-16'sd2068;
  @(posedge dut.tick);repeat(5)@(negedge clk);if(leds!==8'h07)$fatal(1,"post-FX physical pins");
  force dut.PA_EN=1;@(negedge clk);@(negedge clk);if(leds!==8'hff)$fatal(1,"mute");
  release dut.PA_EN;release dut.pcm;
  force dut.pmod_test=1;@(negedge clk);release dut.pmod_test;
"""+start)
# Exercise the accepted PC-note tag on the real controller, independently of voice allocation.
links=links.replace('frame[0:111],host_reply[0:111]','frame[0:279],host_reply[0:279]')
links=links.replace('integer i,j;reg [7:0] sum;', 'defparam dut.output_stage.WARMUP_FRAMES=4;\n integer i,j;reg [7:0] sum;')
marker='$display("PASS independent UART'
assert marker in links
links=links.replace(marker,"""pc_frame(4);wait(np==140);wait(dut.amp_ready);
  pc_frame(5);wait(np==168);if(dut.panel_keys!==32'h00004000)$fatal(1,"middle C did not light H15");
  pc_frame(6);wait(np==196);if(dut.panel_keys!==32'h80004000)$fatal(1,"F6 did not light H32");
  pc_frame(7);wait(np==224);if(dut.panel_keys!==32'h80004000)$fatal(1,"raw diagnostic lit a key");
  pc_frame(8);wait(np==252);if(dut.panel_keys!==32'h80000000)$fatal(1,"releasing C4 changed the wrong key");
  pc_frame(9);wait(np==280);if(dut.panel_keys!==0)$fatal(1,"panic did not clear screen keys");
  """+marker)
(S/'links.v').write_text(links)
def pc_key(voice,gate,index):
    note=WHITE_KEYS[index];return voice_payload(voice,gate,440*2**((note-69)/12))+bytes([0x80|index])
messages=[(10,bytes([6,8])),(29,b''),(25,b''),(28,bytes([2,5])),(6,b''),
          (2,pc_key(19,1,14)),(2,pc_key(1,1,31)),(2,voice_payload(3,1,300)),(2,pc_key(19,0,14)),(3,b'')]
(S/'pc.hex').write_text('\n'.join(f'{x:02x}' for op,value in messages for x in packet(17,op,value))+'\n')
models={'DVI_TX_Top.v','display_pll.v','panel_renderer.v','native_usb_bridge.v','keyboard_adc.v'}
files=[(R/f.get('path')).resolve() for f in ET.parse(R/'synth_display.gprj').findall('.//File')
       if f.get('path').endswith('.v') and Path(f.get('path')).name not in models and 'usb_keypad_host/' not in f.get('path')]
for top in ('tb_links','tb_performance'):
    binary=S/(top+'.vvp')
    subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-s',top,'-o',binary,*files,S/'performance.v',S/'links.v'],cwd=R,check=True)
    with (S/(top+'.log')).open('w') as log:
        subprocess.run(['E:/iverilog/bin/vvp.exe',binary],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=500)
    print((S/(top+'.log')).read_text(),flush=True)
