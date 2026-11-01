`timescale 1ns/1ps
// Captures exactly the unbiased PCM word sampled by audio_tx on each sample_tick.
// One buffer, no decimation; readback is allowed only after capture and CRC finish.
module pcm_capture #(parameter DEPTH=32768)(
 input wire clk,rst,sample_tick,input wire signed [15:0] pcm,
 input wire command_valid,command_arm,trigger_nonzero,
 input wire [15:0] requested_length,input wire [31:0] requested_delay,
 input wire [14:0] read_address,output reg [15:0] read_data,
 output wire busy,ready,output wire [7:0] flags,
 output reg [15:0] capture_id,count,target_length,
 output reg [31:0] first_frame,output wire [31:0] checksum,
 output wire [15:0] capacity
);
 localparam IDLE=0,ARMED=1,DELAY=2,RECORD=3,FINISH=4,READY=5,ABORTED=6;
 reg [2:0] state=IDLE;
 reg trigger_mode=0,crc_overrun=0;
 reg [31:0] delay_left=0,frame_counter=0,crc=32'hffffffff;
 reg [15:0] crc_word=0;reg [4:0] crc_bits=0;
 reg [15:0] memory[0:DEPTH-1];
 wire trigger_hit=!trigger_mode || pcm!=0;
 wire store_word=!rst && !command_valid && sample_tick && count<target_length &&
     (state==RECORD || (state==ARMED && trigger_hit && delay_left==0) || (state==DELAY && delay_left==1));
 assign capacity=DEPTH;
 assign busy=state==ARMED || state==DELAY || state==RECORD || state==FINISH;
 assign ready=state==READY;
 assign flags={3'b0,crc_overrun,(state==ABORTED),ready,(state==RECORD || state==FINISH),(state==ARMED || state==DELAY)};
 assign checksum=~crc;
 // Inferred simple dual-port BRAM. Memory itself deliberately has no reset.
 always @(posedge clk) begin
   if(store_word)memory[count[14:0]]<=pcm;
   read_data<=memory[read_address];
 end
 always @(posedge clk) begin
   if(rst) begin
     state<=IDLE;trigger_mode<=0;crc_overrun<=0;delay_left<=0;frame_counter<=0;
     capture_id<=0;count<=0;target_length<=0;first_frame<=0;crc<=32'hffffffff;crc_word<=0;crc_bits<=0;
   end else begin
     if(sample_tick)frame_counter<=frame_counter+1'b1;
     if(crc_bits!=0)begin
       crc<=(crc>>1)^((crc[0]^crc_word[0])?32'hedb88320:32'd0);
       crc_word<=crc_word>>1;crc_bits<=crc_bits-1'b1;
     end
     if(command_valid)begin
       if(command_arm && requested_length!=0 && requested_length<=DEPTH && !busy)begin
         state<=ARMED;trigger_mode<=trigger_nonzero;delay_left<=requested_delay;
         capture_id<=capture_id+1'b1;count<=0;target_length<=requested_length;
         first_frame<=0;crc<=32'hffffffff;crc_overrun<=0;crc_bits<=0;
       end else if(!command_arm)begin state<=ABORTED;crc_bits<=0;end
     end else if(store_word)begin
       if(count==0)first_frame<=frame_counter;
       count<=count+1'b1;
       crc_word<=pcm;crc_bits<=16;
       if(crc_bits!=0)crc_overrun<=1;
       if(count+1'b1==target_length)state<=FINISH;else state<=RECORD;
     end else begin
       if(sample_tick && state==ARMED && trigger_hit && delay_left!=0)state<=DELAY;
       else if(sample_tick && state==DELAY && delay_left>1)delay_left<=delay_left-1'b1;
       if(state==FINISH && crc_bits==0)state<=READY;
     end
   end
 end
endmodule
