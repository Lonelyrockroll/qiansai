`timescale 1ns/1ps
// The mapping is a permutation of the original 32 white pitches. The scan
// address settles long before the ADC conversions for that physical key.
module key_layout(input wire clk,rst,input wire safe_to_edit,input wire [4:0] scan_key,
 output reg [4:0] pitch_key,input wire command_valid,input wire [7:0] op,length,a,b,
 output reg response_valid,output reg [7:0] status,
 output reg [4:0] report_a,report_pitch_a,report_b,report_pitch_b);
 reg [4:0] layout[0:31]; integer i;
 always @(posedge clk)begin
  pitch_key<=layout[scan_key];response_valid<=command_valid;
  if(rst)begin
   for(i=0;i<32;i=i+1)layout[i]<=i[4:0];
   report_a<=0;report_pitch_a<=0;report_b<=0;report_pitch_b<=0;status<=0;response_valid<=0;
  end else if(command_valid)begin
   status<=0;report_a<=a[4:0];report_b<=b[4:0];
   report_pitch_a<=layout[a[4:0]];report_pitch_b<=layout[b[4:0]];
   case(op)
    24:if(length!=1 || a>=32)status<=3;
    25:if(length!=2 || a>=32 || b>=32)status<=3;
       else if(!safe_to_edit)status<=4;
       else begin
        layout[a[4:0]]<=layout[b[4:0]];layout[b[4:0]]<=layout[a[4:0]];
        report_pitch_a<=layout[b[4:0]];report_pitch_b<=layout[a[4:0]];
       end
    26:if(length!=0)status<=3;
       else if(!safe_to_edit)status<=4;
       else begin
        for(i=0;i<32;i=i+1)layout[i]<=i[4:0];
        report_a<=0;report_b<=0;report_pitch_a<=0;report_pitch_b<=0;
       end
    default:status<=2;
   endcase
  end
 end
endmodule
