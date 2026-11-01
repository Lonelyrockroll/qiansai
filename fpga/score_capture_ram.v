`timescale 1ns/1ps
// Exactly two memory ports: sysclk read/write shares one address and pixelclk
// only reads. Keeping the native 16-bit width avoids SDP32 physical splitting.
module score_capture_ram #(parameter DEPTH=32768)(
 input wire sys_clk,sys_write,input wire [14:0] sys_address,
 input wire [15:0] sys_data,output reg [15:0] sys_q,
 input wire pixel_clk,input wire [14:0] pixel_address,output reg [15:0] pixel_q
);
 reg [15:0] memory[0:DEPTH-1];
 always @(posedge sys_clk)begin
  if(sys_write)memory[sys_address]<=sys_data;
  else sys_q<=memory[sys_address];
 end
 always @(posedge pixel_clk)pixel_q<=memory[pixel_address];
endmodule
