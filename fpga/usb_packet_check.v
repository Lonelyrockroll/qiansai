`timescale 1ns/1ps
// Receive packet validator. Bytes include SYNC, PID, payload, and CRC16.
// USB CRC16 reflected polynomial 0xa001; residue over data + received CRC = 0xb001.
module usb_packet_check(input wire clk,reset,start,byte_valid,input wire [7:0] byte_data,
 input wire finish,physical_error,aligned,
 output reg done,ok,valid,error,output reg [7:0] pid,
 output reg [6:0] length,output reg [511:0] payload);
 reg [7:0] count;reg [15:0] crc;reg header_bad;reg [7:0] captured_pid;
 reg [511:0] capture;
 function [15:0] crc_byte(input [15:0] old,input [7:0] b);
  reg [15:0] c;integer i;begin c=old^{8'd0,b};for(i=0;i<8;i=i+1)c=(c>>1)^(c[0]?16'ha001:0);crc_byte=c;end
 endfunction
 wire data_pid=captured_pid==8'hc3 || captured_pid==8'h4b;
 wire handshake=captured_pid==8'hd2 || captured_pid==8'h5a || captured_pid==8'h1e;
 wire accepted=!physical_error && aligned && !header_bad &&
  ((data_pid && count>=4 && count<=68 && crc==16'hb001) || (handshake && count==2));
 always @(posedge clk) begin
  done<=0;valid<=0;error<=0;
  if(reset || start)begin count<=0;crc<=16'hffff;header_bad<=0;captured_pid<=0;capture<=0;ok<=0;end
  else begin
   if(byte_valid)begin
    if(count==0)header_bad<=byte_data!=8'h80;
    else if(count==1)begin captured_pid<=byte_data;header_bad<=header_bad || (byte_data[7:4]!=(~byte_data[3:0]));end
    else begin
     crc<=crc_byte(crc,byte_data);
     if(count<66)capture[(count-2)*8 +: 8]<=byte_data;
    end
    if(count!=255)count<=count+1'b1;else header_bad<=1;
   end
   if(finish)begin
    done<=1;ok<=accepted;valid<=accepted;error<=!accepted;pid<=captured_pid;
    length<=data_pid && count>=4?count-4:0;payload<=capture;
   end
  end
 end
endmodule
