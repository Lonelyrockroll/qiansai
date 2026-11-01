`timescale 1ns/1ps
// Low-brightness, bounded tests. No audio/ADC handshake or shared resource.
// 0 off; 1 green chase (10.6s); 2 physical-key follow; 3 G/R/B chase (29.8s).
module keyboard_lights #(
 parameter CLK_HZ=50000000,parameter PREP_CYCLES=CLK_HZ,
 parameter STEP_CYCLES=CLK_HZ*3/10
)(input wire clk,rst,stop,input wire command_valid,input wire [1:0] command,
 input wire [31:0] pressed,input wire keys_valid,
 output wire dout,output reg [1:0] mode,output reg [4:0] index,
 output reg [1:0] color_phase,output reg preparing,output wire tx_busy,
 output wire [31:0] latched_mask,frames);
 reg [31:0] timer;reg [31:0] mask;reg [23:0] grb;
 always @*begin
  mask=0;grb=24'h080000; // brightness 8/255, green only in follow mode
  if(mode==2)mask=1; // D1 is the only populated indicator used during a performance.
  else if((mode==1 || mode==3) && !preparing)mask=(index==0);
  if(mode==3)case(color_phase)
   1:grb=24'h000800;2:grb=24'h000008;default:grb=24'h080000;
  endcase
 end
 always @(posedge clk)begin
  if(rst || stop)begin mode<=rst?2:0;index<=0;color_phase<=0;preparing<=0;timer<=0;end
  else if(command_valid)begin
   mode<=command;index<=0;color_phase<=0;
   preparing<=command==1 || command==3;timer<=PREP_CYCLES-1;
  end else if(mode==1 || mode==3)begin
   if(timer!=0)timer<=timer-1'b1;
   else begin
    timer<=STEP_CYCLES-1;
    if(preparing)preparing<=0;
    else if(index!=31)index<=index+1'b1;
    else if(mode==3 && color_phase!=2)begin index<=0;color_phase<=color_phase+1'b1;end
    else begin mode<=0;index<=0;color_phase<=0;end
   end
  end
 end
 ws2812b_4020_chain tx(.clk(clk),.rst(rst),.pixel_mask(mask),.grb(grb),
  .dout(dout),.busy(tx_busy),.frames(frames),.latched_mask(latched_mask));
endmodule
