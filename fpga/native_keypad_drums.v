`timescale 1ns/1ps
// Device-specific report decoding after USB PID/CRC/toggle/profile checks.
// Event IDs: K01..K12=0..11, A+/A-/press=12..14, B+/B-/press=15..17.
module native_keypad_drums #(parameter CLK_HZ=50000000)(input wire clk,rst,connected,
 input wire mode_change,
 input wire report_valid,input wire [4:0] report_length,input wire [127:0] report_data,
 output wire event_valid,input wire event_ready,output reg [4:0] event_id,
 output reg fault);
 // The 12 pads are edges. Encoder gestures are ordered, including repeated wheel detents.
 reg [11:0] held,pad_pending,new_keys;
 reg [2:0] mouse_held;
 reg a_turned,b_turned,ctrl,ctrl_wheeled,ctrl_tail;
 reg [21:0] release_timer;
 reg [2:0] cleanup_mask;
 reg [20:0] cleanup_timer;
 reg [12:0] queue[0:15];   // {event ID, detents in this report}
 reg [3:0] rd,wr;
 reg [4:0] queued;
 reg [7:0] delivered;
 wire keyboard_report=(report_data[7:0]==1 && report_length==9) || (report_data[7:0]==4 && report_length==12);
 wire mouse_report=report_data[7:0]==2 && report_length==5;
 wire [2:0] buttons=report_data[10:8];
 wire new_ctrl=report_data[8] || report_data[12];
 wire [7:0] wheel=report_data[39:32];
 wire [7:0] wheel_count=wheel[7] ? (~wheel+1'b1) : wheel;
 wire a_wheel=ctrl || (ctrl_tail && !(buttons[0] || mouse_held[0]));
 wire moving=wheel!=0;
 // 1189:8840 sends each detent as wheel+zero, temporarily clearing button
 // bits in both packets even when the encoder is physically held. Its real
 // release is a *separate* zero report. Ignore only the detent's own trailer.
 wire [2:0] next_buttons = moving ? (mouse_held|buttons) :
                           (buttons | (cleanup_timer!=0 ? cleanup_mask : 3'b0));
 wire a_held=buttons[1] || mouse_held[1];
 wire b_held=buttons[0] || mouse_held[0];
 // A+/A-, B+/B-, held A+/A-, held B+/B-.
 wire [4:0] wheel_id=(a_wheel ? (a_held ? 5'd18 : 5'd12) : (b_held ? 5'd20 : 5'd15)) + wheel[7];
 wire a_tap=mouse_held[1] && !next_buttons[1] && !a_turned;
 wire b_tap=mouse_held[0] && !next_buttons[0] && !b_turned;
 wire [2:0] additions={2'd0,moving}+{2'd0,a_tap}+{2'd0,b_tap};
 wire [3:0] tap_pos=wr+moving;
 wire [3:0] b_pos=tap_pos+a_tap;
 wire [12:0] head=queue[rd];
 integer i,j;
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
 always @* begin
  new_keys=0;
  for(i=0;i<9;i=i+1)
   if(report_data[7:0]==4 || i<6) new_keys=new_keys|usage_mask(report_data[24+i*8 +: 8]);
  event_id=head[12:8];
  for(j=11;j>=0;j=j-1) if(pad_pending[j]) event_id=j;
 end
 assign event_valid=connected && !report_valid && (pad_pending!=0 || queued!=0);
 always @(posedge clk) begin
  if(rst || !connected || mode_change) begin
   held<=0;pad_pending<=0;mouse_held<=0;a_turned<=0;b_turned<=0;
   ctrl<=0;ctrl_wheeled<=0;ctrl_tail<=0;release_timer<=0;
   cleanup_mask<=0;cleanup_timer<=0;
   rd<=0;wr<=0;queued<=0;delivered<=0;fault<=0;
  end else begin
   if(event_valid && event_ready) begin
    if(pad_pending!=0) pad_pending[event_id]<=0;
    else if(delivered+1'b1==head[7:0]) begin rd<=rd+1'b1;queued<=queued-1'b1;delivered<=0;end
    else delivered<=delivered+1'b1;
   end
   if(ctrl_tail) begin
    if(release_timer==0) ctrl_tail<=0;
    else release_timer<=release_timer-1'b1;
   end
   if(cleanup_timer!=0)cleanup_timer<=cleanup_timer-1'b1;
   if(report_valid && keyboard_report) begin
    pad_pending<=pad_pending|(new_keys & ~held);held<=new_keys;
    if(new_ctrl && !ctrl) begin ctrl_wheeled<=0;ctrl_tail<=0;end
    if(!new_ctrl && ctrl) begin ctrl_tail<=!ctrl_wheeled;release_timer<=CLK_HZ/25;end
    ctrl<=new_ctrl;
   end
   if(report_valid && mouse_report) begin
    if(queued+additions>16) fault<=1;
    else if(additions!=0) begin
     if(moving) queue[wr]<={wheel_id,wheel_count};
     if(a_tap) queue[tap_pos]<={5'd14,8'd1};
     if(b_tap) queue[b_pos]<={5'd17,8'd1};
     wr<=wr+additions;queued<=queued+additions;
    end
    if(moving || buttons!=0) ctrl_tail<=0;
    if(moving && a_wheel && ctrl) ctrl_wheeled<=1;
    if(moving)begin cleanup_mask<=mouse_held & ~buttons;cleanup_timer<=CLK_HZ/50;end
    else begin cleanup_mask<=0;cleanup_timer<=0;end
    if(!next_buttons[1]) a_turned<=0;
    else if(moving && a_wheel) a_turned<=1;
    if(!next_buttons[0]) b_turned<=0;
    else if(moving && !a_wheel) b_turned<=1;
    mouse_held<=next_buttons;
   end
  end
 end
endmodule
