`timescale 1ns/1ps
// Bounded voltage test on the LED DATA pin, never a supply output.
// Blank the chain before taking over, then force LOW/HIGH for <=30 seconds.
// Exit through a low reset interval, then the normal all-zero frame stream.
module led_pin_diagnostic #(
 parameter CLK_HZ=50000000, parameter PREP_CYCLES=1000000,
 parameter RESET_CYCLES=16000, parameter HOLD_SECONDS=30
)(input wire clk,rst,cancel,input wire command_valid,input wire [1:0] command,
 input wire normal_data,output wire pin_data,output wire blank_chain,reset_chain,
 output reg [1:0] mode,phase,output reg [5:0] seconds_left);
 localparam NORMAL=0,PREPARE=1,ACTIVE=2,RECOVER=3;
 reg [25:0] ticks;reg [19:0] wait_ticks;
 assign blank_chain=(phase!=NORMAL) || command_valid;
 assign reset_chain=(phase==ACTIVE || phase==RECOVER);
 assign pin_data=phase==ACTIVE?(mode==2):phase==RECOVER?1'b0:normal_data;
 always @(posedge clk)begin
  if(rst)begin mode<=0;phase<=NORMAL;seconds_left<=0;ticks<=0;wait_ticks<=0;end
  else if(cancel || (command_valid && command==0))begin
   mode<=0;seconds_left<=0;
   if(phase!=NORMAL)begin phase<=RECOVER;wait_ticks<=RESET_CYCLES-1;end
  end else if(command_valid && (command==1 || command==2))begin
   mode<=command;phase<=PREPARE;wait_ticks<=PREP_CYCLES-1;seconds_left<=0;
  end else case(phase)
   PREPARE:if(wait_ticks!=0)wait_ticks<=wait_ticks-1'b1;
    else begin phase<=ACTIVE;seconds_left<=HOLD_SECONDS;ticks<=CLK_HZ-1;end
   ACTIVE:if(ticks!=0)ticks<=ticks-1'b1;
    else if(seconds_left>1)begin ticks<=CLK_HZ-1;seconds_left<=seconds_left-1'b1;end
    else begin phase<=RECOVER;mode<=0;seconds_left<=0;wait_ticks<=RESET_CYCLES-1;end
   RECOVER:if(wait_ticks!=0)wait_ticks<=wait_ticks-1'b1;else phase<=NORMAL;
   default:;
  endcase
 end
endmodule
