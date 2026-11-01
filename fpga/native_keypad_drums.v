`timescale 1ns/1ps
// Device-specific report decoding after USB PID/CRC/toggle/profile checks.
// Event IDs: K01..K12=0..11, A+/A-/press=12..14, B+/B-/press=15..17.
module native_keypad_drums #(parameter CLK_HZ=50000000)(input wire clk,rst,connected,
 input wire mode_change,
 input wire report_valid,input wire [4:0] report_length,input wire [127:0] report_data,
 output wire event_valid,input wire event_ready,output reg [4:0] event_id,
 output reg fault);
 reg [11:0] held;reg [18:0] pending;reg [2:0] mouse_held;

 // Ctrl is exclusively a knob-A prefix. The tail tolerates reordered mouse
 // reports after Ctrl-up; it never delays or generates a drum event.
 reg ctrl,ctrl_tail;reg [21:0] release_timer;
 reg [7:0] a_cw,a_ccw,b_cw,b_ccw;
 reg [11:0] new_keys;reg new_ctrl;reg [7:0] usage;reg [3:0] slots;
 integer i,j;reg chosen;reg [18:0] available;
 wire keyboard_report=(report_data[7:0]==1 && report_length==9) || (report_data[7:0]==4 && report_length==12);
 wire mouse_report=report_data[7:0]==2 && report_length==5;
 wire [7:0] wheel=report_data[39:32];
 wire [7:0] wheel_count=wheel[7]?(~wheel+1'b1):wheel;
 function [11:0] usage_mask(input [7:0] u);
  begin case(u)
   8'h09:usage_mask=11'b00000000001;8'h0e:usage_mask=11'b00000000010;
   8'h1b:usage_mask=11'b00000000100;8'h2c:usage_mask=11'b00000001000;
   8'h28:usage_mask=11'b00000010000;8'h07:usage_mask=11'b00000100000;
   8'h16:usage_mask=11'b00001000000;8'h04:usage_mask=11'b00010000000;
   8'h46:usage_mask=11'b00100000000;8'h2a:usage_mask=11'b01000000000;
   8'h1a:usage_mask=12'h400;8'h68:usage_mask=12'h800;default:usage_mask=0;
  endcase end
 endfunction
 always @*begin
  new_keys=0;new_ctrl=report_data[8] || report_data[12];slots=report_data[7:0]==4?9:6;usage=0;
  for(i=0;i<9;i=i+1)if(i<slots)begin usage=report_data[24+i*8 +: 8];new_keys=new_keys|usage_mask(usage);end
  available=pending;available[12]=a_cw!=0;available[13]=a_ccw!=0;available[15]=b_cw!=0;available[16]=b_ccw!=0;
  chosen=0;event_id=0;
  for(j=0;j<19;j=j+1)if(available[j] && !chosen)begin event_id=j;chosen=1;end
 end
 assign event_valid=chosen && connected && !report_valid;
 always @(posedge clk)begin
  if(rst || !connected)begin
   held<=0;pending<=0;mouse_held<=0;ctrl<=0;ctrl_tail<=0;release_timer<=0;
   a_cw<=0;a_ccw<=0;b_cw<=0;b_ccw<=0;fault<=0;
  end else begin
   if(event_valid && event_ready)begin
    case(event_id)
     12:a_cw<=a_cw-1'b1;13:a_ccw<=a_ccw-1'b1;15:b_cw<=b_cw-1'b1;16:b_ccw<=b_ccw-1'b1;
     default:pending[event_id]<=0;
    endcase
   end
   if(ctrl_tail && !report_valid)begin
    if(release_timer!=0)release_timer<=release_timer-1'b1;
    else ctrl_tail<=0;
   end
   if(report_valid)begin
    if(keyboard_report)begin
     // All twelve keys, including F13/K12, trigger only on a down edge.
     pending[11:0]<=pending[11:0] | (new_keys & ~held);held<=new_keys;
     if(new_ctrl && !ctrl)ctrl_tail<=0;
     if(!new_ctrl && ctrl)begin ctrl_tail<=1;release_timer<=CLK_HZ/25;end
     ctrl<=new_ctrl;
    end else if(mouse_report)begin
     if(report_data[9] && !mouse_held[1])pending[14]<=1;
     if(report_data[8] && !mouse_held[0])pending[17]<=1;
     mouse_held<=report_data[10:8];
     if(wheel!=0)begin
      if(ctrl || ctrl_tail)begin
       ctrl_tail<=0;
       if(wheel[7])begin if({1'b0,a_ccw}+{1'b0,wheel_count}>255)fault<=1;else a_ccw<=a_ccw+wheel_count;end
       else begin if({1'b0,a_cw}+{1'b0,wheel_count}>255)fault<=1;else a_cw<=a_cw+wheel_count;end
      end else if(wheel[7])begin if({1'b0,b_ccw}+{1'b0,wheel_count}>255)fault<=1;else b_ccw<=b_ccw+wheel_count;end
      else begin if({1'b0,b_cw}+{1'b0,wheel_count}>255)fault<=1;else b_cw<=b_cw+wheel_count;end
     end
     if(report_data[10:8]!=0)ctrl_tail<=0;
    end
   end
   if(mode_change)begin pending<=0;a_cw<=0;a_ccw<=0;b_cw<=0;b_ccw<=0;ctrl_tail<=0;end
  end
 end
endmodule
