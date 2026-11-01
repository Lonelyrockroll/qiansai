`timescale 1ns/1ps
// WS2812B-4020, 50 MHz only: GRB, MSB first, 32 * 24 bits.
// 0: 0.30 us high / 0.94 us low; 1: 0.62 us high / 0.62 us low.
// Every frame latches after >=320 us low. Input is snapshotted per frame.
module ws2812b_4020_chain #(
 parameter FRAME_CYCLES=500000, parameter RESET_CYCLES=16000
)(input wire clk,rst,input wire [31:0] pixel_mask,input wire [23:0] grb,
 output reg dout,output wire busy,output reg [31:0] frames,latched_mask);
 localparam WAIT=0,DATA=1,LATCH=2;
 reg [1:0] state;reg [18:0] wait_count;
 reg [31:0] mask_q;reg [23:0] color_q,shift;
 reg [5:0] phase;reg [4:0] pixel,bit_index;
 wire [5:0] high_ticks=shift[23]?6'd31:6'd15;
 assign busy=state!=WAIT;
 always @(posedge clk)begin
  if(rst)begin
   state<=WAIT;wait_count<=RESET_CYCLES-1;dout<=0;frames<=0;latched_mask<=0;
   mask_q<=0;color_q<=0;shift<=0;phase<=0;pixel<=0;bit_index<=23;
  end else case(state)
   WAIT:begin
    dout<=0;
    if(wait_count!=0)wait_count<=wait_count-1'b1;
    else begin
     mask_q<=pixel_mask;color_q<=grb;shift<=pixel_mask[0]?grb:24'd0;
     pixel<=0;bit_index<=23;phase<=0;dout<=1;state<=DATA;
    end
   end
   DATA:begin
    if(phase==high_ticks-1'b1)dout<=0;
    if(phase==61)begin
     phase<=0;
     if(bit_index!=0)begin shift<={shift[22:0],1'b0};bit_index<=bit_index-1'b1;dout<=1;end
     else if(pixel!=31)begin
      pixel<=pixel+1'b1;bit_index<=23;shift<=mask_q[pixel+1'b1]?color_q:24'd0;dout<=1;
     end else begin state<=LATCH;wait_count<=RESET_CYCLES-1;dout<=0;end
    end else phase<=phase+1'b1;
   end
   LATCH:begin
    dout<=0;
    if(wait_count!=0)wait_count<=wait_count-1'b1;
    else begin
     frames<=frames+1'b1;latched_mask<=mask_q;
     state<=WAIT;wait_count<=FRAME_CYCLES-32*24*62-RESET_CYCLES-1;
    end
   end
   default:begin state<=WAIT;wait_count<=RESET_CYCLES-1;dout<=0;end
  endcase
 end
endmodule
