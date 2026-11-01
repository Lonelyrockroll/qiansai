`timescale 1ns/1ps
// Sample-peak limiter. Exact integer division, immediate peak protection,
// gradual gain recovery. Completes in <=20 clocks within the 1024-clock frame.
module pcm_peak_limiter #(
 parameter CEILING=28000,parameter RELEASE_STEP=32
)(input wire clk,rst,input wire sample_valid,recover_enable,input wire signed [23:0] sample_in,
 output reg signed [15:0] pcm,output reg valid,output reg limited,overrun,
 output reg [16:0] gain_q,output reg [31:0] limited_frames);
 localparam IDLE=0,DIVIDE=1,MULTIPLY=2,OUTPUT=3;
 reg [1:0] state;reg negative;reg [23:0] magnitude,divisor,remainder;
 reg [15:0] quotient;reg [3:0] iteration;reg [16:0] recovery,used_gain;
 reg [40:0] product;
 wire [23:0] input_magnitude=sample_in[23]?(~sample_in+24'd1):sample_in;
 wire [17:0] recovering={1'b0,gain_q}+RELEASE_STEP;
 wire [16:0] next_recovery=!recover_enable?gain_q:(recovering>65536?17'd65536:recovering[16:0]);
 wire [24:0] doubled={remainder,1'b0};
 wire take_bit=doubled>={1'b0,divisor};
 wire [24:0] next_remainder=take_bit?doubled-{1'b0,divisor}:doubled;
 wire [15:0] next_quotient={quotient[14:0],take_bit};
 always @(posedge clk)begin
  if(rst)begin
   state<=IDLE;negative<=0;magnitude<=0;divisor<=0;remainder<=0;quotient<=0;iteration<=0;
   recovery<=65536;used_gain<=65536;gain_q<=65536;product<=0;pcm<=0;valid<=0;limited<=0;overrun<=0;limited_frames<=0;
  end else begin
   valid<=0;
   if(sample_valid && state!=IDLE)overrun<=1;
   case(state)
    IDLE:if(sample_valid)begin
     negative<=sample_in[23];magnitude<=input_magnitude;recovery<=next_recovery;
     if(input_magnitude<=CEILING)begin used_gain<=next_recovery;gain_q<=next_recovery;state<=MULTIPLY;end
     else begin divisor<=input_magnitude;remainder<=CEILING;quotient<=0;iteration<=0;state<=DIVIDE;end
    end
    DIVIDE:begin
     quotient<=next_quotient;remainder<=next_remainder[23:0];iteration<=iteration+1'b1;
     if(iteration==15)begin
      used_gain<=recovery<{1'b0,next_quotient}?recovery:{1'b0,next_quotient};
      gain_q<=recovery<{1'b0,next_quotient}?recovery:{1'b0,next_quotient};state<=MULTIPLY;
     end
    end
    MULTIPLY:begin product<=magnitude*used_gain;state<=OUTPUT;end
    OUTPUT:begin
     pcm<=negative?-$signed({1'b0,product[40:16]}):$signed({1'b0,product[40:16]});
     limited<=used_gain<65536 && magnitude!=0;
     if(used_gain<65536 && magnitude!=0)limited_frames<=limited_frames+1'b1;
     valid<=1;state<=IDLE;
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
