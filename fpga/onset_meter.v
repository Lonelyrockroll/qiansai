`timescale 1ns/1ps
// Timestamp an isolated physical note accepted by the FPGA. Decode the actual
// I2S wires, including the one-bit delay. No host clock participates.
module onset_meter(input wire clk,rst,accept_key,isolated,ready,input wire [4:0] accept_id,
 input wire bclk,lrclk,sd,output wire marker,output reg valid,output reg [15:0] elapsed_us,
 output reg [4:0] measured_key,output reg [15:0] measurement_count);
 reg old_bclk,old_lr,waiting;reg [5:0] bit_count;reg [15:0] word_bits;
 reg [4:0] candidate_key;
 reg [5:0] sub_us;reg [15:0] usec;
 assign marker=waiting;
 wire rising=bclk && !old_bclk;
 wire word_end=rising && !lrclk && bit_count==16;
 always @(posedge clk)begin
  old_bclk<=bclk;old_lr<=lrclk;
  if(old_lr && !lrclk)bit_count<=0;
  else if(rising && !lrclk && bit_count<31)bit_count<=bit_count+1'b1;
  if(rising && !lrclk)word_bits<={word_bits[14:0],sd};
  if(rst)begin valid<=0;waiting<=0;elapsed_us<=0;bit_count<=0;sub_us<=0;usec<=0;word_bits<=0;candidate_key<=0;measured_key<=0;measurement_count<=0;end
  else if(accept_key)begin
   // A chord can cancel a measurement in progress, but cannot erase the last
   // completed isolated measurement. The UI explicitly labels it LAST I2S.
   waiting<=isolated && ready;candidate_key<=accept_id;usec<=0;sub_us<=0;
  end else if(waiting)begin
   if(!ready || usec==65535)waiting<=0;
   else if(word_end && {word_bits[14:0],sd}!=0)begin valid<=1;elapsed_us<=usec;waiting<=0;measured_key<=candidate_key;measurement_count<=measurement_count+1'b1;end
   else if(sub_us==49)begin sub_us<=0;usec<=usec+1'b1;end
   else sub_us<=sub_us+1'b1;
  end
 end
endmodule
