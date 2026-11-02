`timescale 1ns/1ps
// Configure the real voice engine through the normal note router. The 32
// fundamentals occupy odd 1024-sample DFT bins 1..63, separated by empty bins.
module contest_tones(input wire clk,rst,input wire [1:0] mode,input wire [4:0] missing,
 input wire audio_ready,input wire [15:0] volume,output reg event_valid,input wire event_ready,
 output wire [122:0] event_data);
 reg [31:0] sounding,refresh;
 reg [4:0] cursor,note;reg gate;reg [15:0] level,last_volume;
 wire desired=(mode==1 || (mode==2 && cursor!=missing));
 wire [31:0] step={4'b0,note,1'b1,22'b0};
 assign event_data={2'b01,gate,note,3'd0,step,level,16'd2048,16'd1,16'hffff,16'd2048};
 always @(posedge clk)begin
  if(rst || mode==0)begin
   sounding<=0;refresh<=0;cursor<=0;event_valid<=0;last_volume<=volume;
   note<=0;gate<=0;level<=0;
  end else begin
   if(event_valid)begin
    if(event_ready)begin sounding[note]<=gate;refresh[note]<=0;event_valid<=0;cursor<=cursor+1'b1;end
   end else if(audio_ready)begin
    if(desired!=sounding[cursor] || (desired && refresh[cursor]))begin
     event_valid<=1;note<=cursor;gate<=desired;level<=volume>>4;
    end else cursor<=cursor+1'b1;
   end
   if(volume!=last_volume)begin last_volume<=volume;refresh<=32'hffffffff;end
  end
 end
endmodule
