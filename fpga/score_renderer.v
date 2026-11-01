`timescale 1ns/1ps
// A 1024x512 monochrome page expands to 1024x600 without a line/frame buffer.
// Bit 1 is black; the leftmost pixel is the high bit of each 16-bit RAM word.
// RAM read + bit extraction + RGB register matches panel_renderer's 3 cycles.
module score_renderer(input wire clk,rst,input wire show_requested,
 input wire [10:0] x,y,input wire de,frame_start,
 output wire [14:0] read_address,input wire [15:0] read_data,
 output reg visible,output reg select_page,output reg [23:0] rgb);
 reg [1:0] show_sync;
 reg [8:0] source_line;
 reg [9:0] fraction;
 wire [10:0] advanced={1'b0,fraction}+11'd512;
 reg [3:0] bit1;
 reg black2,show1,show2;
 assign read_address={source_line,x[9:4]};
 always @(posedge clk)begin
  show_sync<={show_sync[0],show_requested};
  if(frame_start)begin visible<=show_sync[1];source_line<=0;fraction<=0;end
  else if(de && x==1023)begin
   if(advanced>=600)begin fraction<=advanced-600;source_line<=source_line+1'b1;end
   else fraction<=advanced[9:0];
  end
  bit1<=x[3:0];black2<=read_data[15-bit1];
  rgb<=black2?24'h000000:24'hffffff;
  show1<=visible;show2<=show1;select_page<=show2;
  if(rst)begin
   show_sync<=0;visible<=0;select_page<=0;source_line<=0;fraction<=0;
   bit1<=0;black2<=0;show1<=0;show2<=0;rgb<=24'hffffff;
  end
 end
endmodule
