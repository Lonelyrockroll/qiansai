`timescale 1ns/1ps
// All voices sample the same ratio once per audio frame. Offset is signed Q15
// relative to unity (zero gives the original DDS increment exactly).
module pitch_expression #(parameter RETURN_FRAMES=12207)(
 input wire clk,rst,tick,clear,adjust,select_depth,increase,
 output reg [3:0] bend_position, output reg [2:0] vibrato_depth,
 output reg signed [13:0] pitch_offset);
 reg [13:0] remaining;
 reg [23:0] lfo_phase;
 reg signed [23:0] bend_smooth,depth_smooth;

 function signed [13:0] bend_ratio(input [3:0] position);
  begin case(position) // round(32768 * (2^(cents/1200)-1)), 50 cents per detent
   0:bend_ratio=-3575; 1:bend_ratio=-2720; 2:bend_ratio=-1839; 3:bend_ratio=-933;
   5:bend_ratio=960; 6:bend_ratio=1948; 7:bend_ratio=2966; 8:bend_ratio=4013;
   default:bend_ratio=0;
  endcase end
 endfunction
 function [7:0] quarter_sine(input [4:0] index);
  begin case(index)
   0:quarter_sine=0; 1:quarter_sine=12; 2:quarter_sine=25; 3:quarter_sine=37;
   4:quarter_sine=49; 5:quarter_sine=60; 6:quarter_sine=71; 7:quarter_sine=81;
   8:quarter_sine=90; 9:quarter_sine=98; 10:quarter_sine=106; 11:quarter_sine=112;
   12:quarter_sine=117; 13:quarter_sine=122; 14:quarter_sine=125; 15:quarter_sine=126;
   default:quarter_sine=127;
  endcase end
 endfunction
 wire [4:0] quadrant_index=lfo_phase[22] ? (5'd16-{1'b0,lfo_phase[21:18]}) : {1'b0,lfo_phase[21:18]};
 wire signed [8:0] lfo_magnitude=$signed({1'b0,quarter_sine(quadrant_index)});
 reg signed [8:0] lfo_value;
 reg signed [20:0] vibrato_product;
 wire signed [13:0] target=bend_ratio(bend_position);
 wire signed [23:0] bend_error=$signed({target,8'b0})-bend_smooth;
 // 190/32768 is approximately ten cents. Five detents give about +/-50 cents.
 wire signed [23:0] depth_error=$signed({1'b0,vibrato_depth})*24'sd48640-depth_smooth;
 always @(posedge clk) begin
  lfo_value<=lfo_phase[23] ? -lfo_magnitude : lfo_magnitude;
  vibrato_product<=lfo_value*$signed({1'b0,depth_smooth[18:8]});
  if(rst || clear) begin
   remaining<=0;bend_position<=4;vibrato_depth<=0;lfo_phase<=0;
   bend_smooth<=0;depth_smooth<=0;pitch_offset<=0;lfo_value<=0;vibrato_product<=0;
  end else begin
   if(tick) begin
    lfo_phase<=lfo_phase+24'd1890; // 5.50 Hz at 50 MHz / 1024
    bend_smooth<=bend_smooth+((bend_error+(bend_error>0 ? 24'sd1023 : 24'sd0))>>>10);
    depth_smooth<=depth_smooth+((depth_error+(depth_error>0 ? 24'sd255 : 24'sd0))>>>8);
    pitch_offset<=(bend_smooth>>>8)+(vibrato_product>>>7);
    if(remaining!=0) begin
     remaining<=remaining-1'b1;
     if(remaining==1) bend_position<=4;
    end
   end
   if(adjust && select_depth) begin
    if(increase && vibrato_depth<5) vibrato_depth<=vibrato_depth+1'b1;
    if(!increase && vibrato_depth>0) vibrato_depth<=vibrato_depth-1'b1;
   end else if(adjust) begin
    remaining<=RETURN_FRAMES;
    if(increase && bend_position<8) bend_position<=bend_position+1'b1;
    if(!increase && bend_position>0) bend_position<=bend_position-1'b1;
   end
  end
 end
endmodule
