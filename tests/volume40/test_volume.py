"""Verify legacy/new volume limits and the actual USB knob translation."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from protocol import Decoder,RESPONSE_SYNC,packet,keyboard_payload,DISPLAY_ACTION
from server import Controller


class VolumeRangeTests(unittest.TestCase):
    def test_capability_byte_and_legacy_default(self):
        for code,percent,maximum in [(0,25,16384),(40,40,26214)]:
            p=bytearray(20);p[17]=code;p[18]=32;p[19]=27
            parsed=Decoder().feed(RESPONSE_SYNC+packet(1,128,p)[2:])[0]
            self.assertEqual((parsed['keyboard_limit_percent'],parsed['keyboard_limit']),(percent,maximum))
            values=struct.unpack('<BBB8H',keyboard_payload(level_limit=maximum,params={'level':.9}))
            self.assertEqual(values[3],maximum)

    def test_host_control_uses_current_view_limit(self):
        for drum,value,expected in [(False,16384,17695),(False,25559,26214),(True,16384,16384)]:
            c=Controller.__new__(Controller);c.transport=True;c.feedback={'firmware':32}
            c.output_gain_feedback={'keyboard_limit':26214};c.touch={};c.keyboard={'mode':0}
            c.exchange=Mock(return_value={'level':value,'drum_mode':drum,'firmware':32})
            c.control_function('volume_up',2,1)
            self.assertEqual(c.exchange.call_args_list[1].args,(DISPLAY_ACTION,bytes([7])+expected.to_bytes(2,'little')))

    def test_native_knob_saturates(self):
        code='''`timescale 1ns/1ps
module tb;
reg clk=0;always #10 clk=~clk;
reg rst=1,drum=0;reg [15:0] level=0;wire [15:0] value;
native_usb_bridge dut(.sys_clk(clk),.rst(rst),.current_level(level),.current_timbre(3'd1),
 .drum_mode(drum),.drum_hit_ready(1'b1),.command_ready(1'b1),.command_value(value));
integer i,maxlevel,expected;
initial begin
 force dut.event_id=5'd20;#50;rst=0;
 for(i=0;i<2;i=i+1)begin
  drum=i;maxlevel=i?16384:26214;
  for(level=0;level<30000;level=level+137)begin
   expected=level+1311;if(expected>maxlevel)expected=maxlevel;
   #1;if(value!==expected)$fatal(1,"volume %0d view %0d got %0d expected %0d",level,drum,value,expected);
  end
 end
 $display("PASS native volume saturation both views");$finish;
end
endmodule'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);(path/'tb.v').write_text(code)
            subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-i','-s','tb','-o',str(path/'tb.vvp'),str(path/'tb.v'),str(ROOT/'fpga/native_usb_bridge.v')],check=True)
            result=subprocess.run(['E:/iverilog/bin/vvp.exe',str(path/'tb.vvp')],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
