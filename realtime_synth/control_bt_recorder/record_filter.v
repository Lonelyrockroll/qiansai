// 49-tap Hamming-windowed lowpass, 6650 Hz cutoff at 48828.125 Hz, Q14 unity DC.
// One multiplier runs between input ticks. Decimate 3:1 after filtering.
module record_filter(input wire clk,rst,tick,input wire signed [15:0] pcm,
 output reg valid,output reg signed [15:0] sample);
 reg signed [15:0] history[0:48];
 reg [1:0] phase;
 reg running,product_valid,last_product;
 reg [5:0] tap;
 reg signed [31:0] product;
 reg signed [35:0] accum;
 wire signed [35:0] total=accum+product;
 wire signed [35:0] scaled=total>>>14;
 function signed [15:0] coefficient(input [5:0] k);
 begin case(k)
   0: coefficient=16'sd17;
   1: coefficient=16'sd14;
   2: coefficient=-16'sd1;
   3: coefficient=-16'sd22;
   4: coefficient=-16'sd36;
   5: coefficient=-16'sd25;
   6: coefficient=16'sd19;
   7: coefficient=16'sd73;
   8: coefficient=16'sd91;
   9: coefficient=16'sd34;
   10: coefficient=-16'sd87;
   11: coefficient=-16'sd191;
   12: coefficient=-16'sd175;
   13: coefficient=16'sd3;
   14: coefficient=16'sd262;
   15: coefficient=16'sd410;
   16: coefficient=16'sd267;
   17: coefficient=-16'sd176;
   18: coefficient=-16'sd685;
   19: coefficient=-16'sd855;
   20: coefficient=-16'sd339;
   21: coefficient=16'sd910;
   22: coefficient=16'sd2538;
   23: coefficient=16'sd3917;
   24: coefficient=16'sd4458;
   25: coefficient=16'sd3917;
   26: coefficient=16'sd2538;
   27: coefficient=16'sd910;
   28: coefficient=-16'sd339;
   29: coefficient=-16'sd855;
   30: coefficient=-16'sd685;
   31: coefficient=-16'sd176;
   32: coefficient=16'sd267;
   33: coefficient=16'sd410;
   34: coefficient=16'sd262;
   35: coefficient=16'sd3;
   36: coefficient=-16'sd175;
   37: coefficient=-16'sd191;
   38: coefficient=-16'sd87;
   39: coefficient=16'sd34;
   40: coefficient=16'sd91;
   41: coefficient=16'sd73;
   42: coefficient=16'sd19;
   43: coefficient=-16'sd25;
   44: coefficient=-16'sd36;
   45: coefficient=-16'sd22;
   46: coefficient=-16'sd1;
   47: coefficient=16'sd14;
   48: coefficient=16'sd17;
   default:coefficient=0;
 endcase end endfunction
 integer i;
 always @(posedge clk)begin
  if(rst)begin
   phase<=0;running<=0;product_valid<=0;last_product<=0;valid<=0;
   tap<=0;accum<=0;sample<=0;product<=0;
   for(i=0;i<49;i=i+1)history[i]<=0;
  end else begin
   valid<=0;product_valid<=running;
   if(tick)begin
    history[0]<=pcm;
    for(i=1;i<49;i=i+1)history[i]<=history[i-1];
    if(phase==2)begin phase<=0;tap<=0;running<=1;accum<=0;end
    else phase<=phase+1'b1;
   end
   if(running)begin
    product<=history[tap]*coefficient(tap);
    last_product<=tap==48;
    if(tap==48)running<=0;else tap<=tap+1'b1;
   end
   if(product_valid)begin
    accum<=total;
    if(last_product)begin
     sample<=scaled>32767?16'sh7fff:scaled< -32768?16'sh8000:scaled[15:0];
     valid<=1;
    end
   end
  end
 end
endmodule
