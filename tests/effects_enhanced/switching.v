`timescale 1ns/1ps
module switching;
reg clk=0;always #10 clk=~clk;
reg rst=1,tick=0,cv=0,clear=0,en=1;
reg signed [15:0] x=0;
reg [2:0] mask=0;
reg [7:0] r=0,d=0,c=0;
wire signed [15:0] y;
wire valid,pending,overrun,clipped;
audio_effects dut(.clk(clk),.rst(rst),.clear(clear),.sample_tick(tick),.audio_enable(en),.dry_pcm(x),
 .cfg_valid(cv),.cfg_mask(mask),.cfg_reverb_mix(r),.cfg_delay_mix(d),.cfg_chorus_mix(c),.cfg_feedback(8'd128),
 .cfg_delay_time(2'd3),.cfg_room(2'd2),.cfg_rate(2'd2),.cfg_depth(2'd2),
 .pcm(y),.valid(valid),.pending(pending),.overrun(overrun),.clipped(clipped));
integer i,waited,last=0,delta,largest=0,peak=0;
initial begin
 repeat(6)@(negedge clk);rst=0;
 for(i=0;i<125000;i=i+1)begin
  @(negedge clk);cv=0;tick=0;
  case(i)
   20000:begin mask=1;r=128;d=0;c=0;cv=1;end
   40000:begin mask=2;r=0;d=128;c=0;cv=1;end
   60000:begin mask=4;r=0;d=0;c=128;cv=1;end
   80000:begin mask=7;r=64;d=64;c=112;cv=1;end
   100000:begin mask=0;cv=1;end
  endcase
  @(negedge clk);cv=0;
  x=$rtoi(12000.0*$sin(6.283185307179586*333.0*i/48828.125));
  tick=1;@(negedge clk);tick=0;waited=0;
  while(!valid)begin @(negedge clk);waited=waited+1;if(waited>120)$fatal(1,"deadline");end
  if(overrun || clipped || ^y===1'bx)$fatal(1,"audio state");
  delta=$signed(y)-last;if(delta<0)delta=-delta;
  if(delta>largest)largest=delta;
  if($signed(y)>peak)peak=y;
  if(delta>1600)$fatal(1,"switching discontinuity %0d at frame %0d",delta,i);
  last=$signed(y);repeat(4)@(negedge clk);
 end
 $display("PASS continuous 333Hz tone and five preset changes; max adjacent delta %0d, positive peak %0d",largest,peak);$finish;
end
endmodule
