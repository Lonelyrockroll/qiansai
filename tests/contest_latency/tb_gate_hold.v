`timescale 1ns/1ps
// The same unforced pin-level stimulus runs against behavioral RTL and the
// Gowin-generated post-P&R model. Pins and ADC timing stay at production values.
module tb_gate_hold;
  reg clk=0,rst=1,play=1,ready=1,eoc=1;always #10 clk=~clk;
  reg [12:0] data=4000,latched=4000;reg down=0;
  wire [4:0] addr,physical,voice;wire soc,cal,fault,valid,gate;
  wire [31:0] mask,sensed;wire [15:0] scans,level;
  probe dut(.clk(clk),.rst(rst),.recalibrate(1'b0),.play(play),.ready(ready),.eoc(eoc),.data(data),
    .addr(addr),.physical(physical),.voice(voice),.soc(soc),.cal(cal),.fault(fault),.valid(valid),
    .gate(gate),.mask(mask),.sensed(sensed),.scans(scans),.level(level));
  integer left=0,ons=0,offs=0,observations=0,missing_held_bit=0,previous_scan=0,first=0;
  integer hold_scans=32;
  always @(posedge clk)begin
    if(rst)begin eoc<=1;data<=4000;left<=0;end
    else if(soc)begin latched<=(down && addr==14)?4720:4000;eoc<=0;left<=20;end
    else if(left>0)begin left<=left-1;if(left==1)begin data<=latched;eoc<=1;end end
    if(!rst && valid && ready)begin
      if(voice!==14 || ^gate===1'bx)$fatal(1,"unexpected voice/gate");
      if(gate)ons=ons+1;else offs=offs+1;
      $display("EVENT scan=%0d gate=%b mask=%h sensed=%h",scans,gate,mask,sensed);
    end
    if(down && cal && scans!=previous_scan && scans>first)begin
      observations=observations+1;
      if(mask!==32'h00004000)missing_held_bit=missing_held_bit+1;
      $display("HELD scan=%0d mask=%h sensed=%h",scans,mask,sensed);
    end
    previous_scan=scans;
  end
  initial begin
    if(!$value$plusargs("N=%d",hold_scans))hold_scans=32;
    repeat(8)@(negedge clk);rst=0;wait(cal===1'b1);@(negedge clk);
    if(fault || scans<16 || mask!==0 || sensed!==0)$fatal(1,"calibration failed");
    first=scans;down=1;
    wait(scans==first+hold_scans);@(posedge clk);@(negedge clk);down=0;
    wait(scans==first+hold_scans+2);@(negedge clk);
    if(fault || mask!==0 || sensed!==0 || observations!=hold_scans)$fatal(1,"invalid final state or incomplete capture");
    $display("RESULT %0d %0d %0d %0d",ons,offs,observations,missing_held_bit);$finish;
  end
  initial begin #60000000;$fatal(1,"initialization/scan timeout");end
endmodule
