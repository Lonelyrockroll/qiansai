`timescale 1ns/1ps
// Bind native controls to the descriptor actually captured from this keypad.
module usb_profile_check(input wire clk,reset,descriptor_active,packet_valid,
 input wire [6:0] length,input wire [511:0] payload,output reg profile_ok);
 reg active_old,busy;reg [511:0] data;reg [6:0] remain;reg [8:0] total;reg [31:0] crc;
 function [31:0] crc_byte(input [31:0] c0,input [7:0] b);
  reg [31:0] c;integer i;begin c=c0^{24'd0,b};for(i=0;i<8;i=i+1)c=(c>>1)^(c[0]?32'hedb88320:0);crc_byte=c;end
 endfunction
 wire [31:0] next_crc=crc_byte(crc,data[7:0]);
 always @(posedge clk) begin
  active_old<=descriptor_active;
  if(reset || (descriptor_active && !active_old))begin
   busy<=0;total<=0;crc<=32'hffffffff;profile_ok<=0;remain<=0;
   if(reset)active_old<=0;
  end else begin
   if(descriptor_active && packet_valid && length!=0 && !busy)begin data<=payload;remain<=length;busy<=1;end
   if(busy)begin
    data<=data>>8;crc<=next_crc;remain<=remain-1'b1;total<=total+1'b1;
    if(remain==1)begin busy<=0;profile_ok<=total==206 && (next_crc^32'hffffffff)==32'h8a7bf92e;end
   end
  end
 end
endmodule
