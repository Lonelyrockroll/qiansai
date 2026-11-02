`timescale 1ns/1ps
// Reconcile source 0 only after the physical scanner has observed all keys
// released for two whole passes and no note is waiting for the router.
module key_release_guard(input wire clk,rst,input wire [15:0] scan_count,
 input wire eligible,released,live_held,can_issue,output reg flush,output reg [15:0] flush_count);
 reg [15:0] previous_scan;reg [1:0] boundaries;reg issued;
 always @(posedge clk)begin
  previous_scan<=scan_count;flush<=0;
  if(rst)begin boundaries<=0;issued<=0;flush_count<=0;end
  else if(!released || !live_held)begin boundaries<=0;issued<=0;end
  else if(!eligible)boundaries<=0;
  else if(!issued)begin
   if(boundaries==3 && can_issue)begin flush<=1;issued<=1;flush_count<=flush_count+1'b1;end
   else if(boundaries!=3 && scan_count!=previous_scan)boundaries<=boundaries+1'b1;
  end
 end
endmodule
