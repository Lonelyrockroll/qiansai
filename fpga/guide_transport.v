`timescale 1ns/1ps
// Framed guide transfer sharing the Bluetooth byte link. Root arbitration must
// finish any TREC frame before granting tx_ready to this module.
module guide_transport #(
 parameter CLK_HZ=50000000,
 parameter RX_TIMEOUT_CYCLES=CLK_HZ/2,
 parameter UPLOAD_TIMEOUT_CYCLES=CLK_HZ*10
)(
 input wire clk,rst,audio_tick,probe,score_probe,
 input wire rx_valid,input wire [7:0] rx_data,
 input wire tx_ready,output reg tx_valid,output reg [7:0] tx_data,
 input wire recorder_active,
 input wire ui_valid,input wire [3:0] ui_action,
 output wire owned,receiving,
 output wire guide_valid,guide_playing,guide_loading,guide_demo,
 output wire [15:0] guide_time_cs,guide_duration_cs,
 output wire [9:0] guide_count,guide_index,
 output wire [1:0] guide_speed,
 output wire [31:0] guide_current,guide_onset,guide_next,
 output wire [63:0] guide_colors,
 input wire score_video_visible,capture_busy,capture_ready,
 input wire score_ui_valid,input wire [1:0] score_ui_action,output wire score_ui_ready,
 output wire score_write_enable,output wire [14:0] score_write_address,output wire [15:0] score_write_data,
 output wire score_valid,score_show_requested,score_loading,score_reserved,
 output wire [31:0] score_received_compressed,score_decoded_bytes,
 output wire [15:0] score_page_index,score_page_count
);
 localparam IDLE=0,MAGIC=1,DATA=2,CHECK=3,DISPATCH=4,WAIT_REPLY=5,
            BUILD=6,CRC_REPLY=7,CACHE=8,SEND=9;
 reg [3:0] state;
 reg [7:0] frame[0:27] /* synthesis syn_ramstyle="registers" */;
 reg [7:0] reply[0:23] /* synthesis syn_ramstyle="registers" */;
 reg [7:0] last_reply[0:23] /* synthesis syn_ramstyle="registers" */;
 reg [4:0] rx_index,tx_index,crc_index;
 reg [31:0] rx_timeout;
 reg [15:0] rx_crc,tx_crc;
 reg [7:0] reply_seq,reply_op,reply_status;
 reg cache_valid,cacheable,score_reply;
 reg [191:0] last_request,request_identity;
 wire [191:0] identity;
 genvar j;
 generate for(j=0;j<24;j=j+1)begin: identify
  assign identity[j*8 +: 8]=frame[j+2];
 end endgenerate
 reg padding_bad;
 integer i;
 always @*begin
  padding_bad=0;
  for(integer k=0;k<20;k=k+1)if(k>=frame[5] && frame[6+k]!=0)padding_bad=1;
 end
 wire guide_command_ready,guide_response_valid,score_command_ready,score_response_valid;
 wire [7:0] guide_response_status,score_response_status;
 wire command_ready=score_reply?score_command_ready:guide_command_ready;
 wire response_valid=score_reply?score_response_valid:guide_response_valid;
 wire [7:0] response_status=score_reply?score_response_status:guide_response_status;
 reg command_valid,score_command_valid;
 reg [7:0] command_op,command_length;
 reg [159:0] command_payload;
 wire [9:0] received_count;
 // Older guide-only benches leave the newly added capability pin open.
 // A hardware request is active only at logic one.
 wire score_probe_active=(score_probe===1'b1);
 assign receiving=state==MAGIC || state==DATA || (state==IDLE && rx_valid && rx_data==8'ha5);
 assign owned=state!=IDLE || tx_valid || (rx_valid && rx_data==8'ha5);
 guide_player #(.CLK_HZ(CLK_HZ),.UPLOAD_TIMEOUT_CYCLES(UPLOAD_TIMEOUT_CYCLES)) player(
  .clk(clk),.rst(rst),.audio_tick(audio_tick),
  .command_valid(command_valid),.command_ready(guide_command_ready),.command_op(command_op),
  .command_length(command_length),.command_payload(command_payload),
  .response_valid(guide_response_valid),.response_status(guide_response_status),
  .ui_valid(ui_valid),.ui_action(ui_action),
  .guide_valid(guide_valid),.guide_playing(guide_playing),.guide_loading(guide_loading),.guide_demo(guide_demo),
  .guide_time_cs(guide_time_cs),.guide_duration_cs(guide_duration_cs),.guide_count(guide_count),.guide_index(guide_index),
  .guide_speed(guide_speed),.guide_current(guide_current),.guide_onset(guide_onset),.guide_next(guide_next),
  .guide_colors(guide_colors),.received_count(received_count));
 wire score_capture_blocked;
 score_store #(.CLK_HZ(CLK_HZ),.UPLOAD_TIMEOUT_CYCLES(UPLOAD_TIMEOUT_CYCLES)) score(
  .clk(clk),.rst(rst),.command_valid(score_command_valid),.command_ready(score_command_ready),
  .command_op(command_op),.command_length(command_length),.command_payload(command_payload),
  .response_valid(score_response_valid),.response_status(score_response_status),
  .ui_valid(score_ui_valid),.ui_action(score_ui_action),.ui_ready(score_ui_ready),
  .video_visible(score_video_visible),.capture_busy(capture_busy),.capture_ready(capture_ready),
  .write_enable(score_write_enable),.write_address(score_write_address),.write_data(score_write_data),
  .valid(score_valid),.show_requested(score_show_requested),.loading(score_loading),.reserved(score_reserved),
  .capture_blocked(score_capture_blocked),.received_compressed(score_received_compressed),
  .decoded_bytes(score_decoded_bytes),.page_index(score_page_index),.page_count(score_page_count));
 function [15:0] crc16_byte(input [15:0] crc,input [7:0] data);
  reg [15:0] q;integer k;
  begin q=crc^{data,8'd0};for(k=0;k<8;k=k+1)q=(q<<1)^(q[15]?16'h1021:16'd0);crc16_byte=q;end
 endfunction
 wire [15:0] next_crc=crc16_byte(tx_crc,reply[crc_index]);
 always @(posedge clk)begin
  if(rst)begin
   state<=IDLE;rx_index<=0;tx_index<=0;crc_index<=0;rx_timeout<=0;rx_crc<=16'hffff;tx_crc<=16'hffff;
   reply_seq<=0;reply_op<=0;reply_status<=0;cache_valid<=0;cacheable<=0;score_reply<=0;last_request<=0;request_identity<=0;
   command_valid<=0;score_command_valid<=0;command_op<=0;command_length<=0;command_payload<=0;
   tx_valid<=0;tx_data<=0;
   for(i=0;i<28;i=i+1)frame[i]<=0;
   for(i=0;i<24;i=i+1)begin reply[i]<=0;last_reply[i]<=0;end
  end else begin
   tx_valid<=0;command_valid<=0;score_command_valid<=0;
   if(state==MAGIC || state==DATA)begin
    if(rx_valid)rx_timeout<=0;
    else if(rx_timeout==RX_TIMEOUT_CYCLES-1)begin state<=IDLE;rx_timeout<=0;end
    else rx_timeout<=rx_timeout+1'b1;
   end
   case(state)
    IDLE:begin
     if(rx_valid && rx_data==8'ha5)begin frame[0]<=rx_data;rx_timeout<=0;state<=MAGIC;end
     else if(probe || score_probe_active)begin
      // A fresh capability exchange starts a connection's retry namespace.
      reply_seq<=0;reply_op<=score_probe_active?16:0;score_reply<=score_probe_active;
      reply_status<=0;cacheable<=0;cache_valid<=0;state<=BUILD;
     end
    end
    MAGIC:if(rx_valid)begin
     if(rx_data==8'h47)begin frame[1]<=rx_data;rx_index<=2;rx_crc<=16'hffff;state<=DATA;end
     else if(rx_data!=8'ha5)state<=IDLE;
    end
    DATA:if(rx_valid)begin
     frame[rx_index]<=rx_data;
     if(rx_index<=25)rx_crc<=crc16_byte(rx_crc,rx_data);
     if(rx_index==27)state<=CHECK;else rx_index<=rx_index+1'b1;
    end
    CHECK:begin
     reply_seq<=frame[3];reply_op<=frame[4];score_reply<=frame[4]>=16 && frame[4]<=20;
     request_identity<=identity;cacheable<=0;
     if({frame[27],frame[26]}!=rx_crc)begin reply_status<=1;state<=BUILD;end
     else if(frame[2]!=1 || frame[5]>20 || padding_bad)begin reply_status<=3;state<=BUILD;end
     else if(cache_valid && identity==last_request)begin
      for(i=0;i<24;i=i+1)reply[i]<=last_reply[i];
      tx_index<=0;state<=SEND;
     end else if(recorder_active && frame[4]!=0 && frame[4]!=16)begin reply_status<=4;state<=BUILD;end
     else begin
      command_op<=frame[4];command_length<=frame[5];
      for(i=0;i<20;i=i+1)command_payload[i*8 +: 8]<=frame[i+6];
      state<=DISPATCH;
     end
    end
    DISPATCH:if(command_ready)begin
     if(score_reply)score_command_valid<=1;else command_valid<=1;
     state<=WAIT_REPLY;
    end
    WAIT_REPLY:if(response_valid)begin
     reply_status<=response_status;cacheable<=response_status!=4;state<=BUILD;
    end
    BUILD:begin
     reply[0]<="T";reply[1]<=score_reply?"P":"G";reply[2]<="A";reply[3]<="K";reply[4]<=1;
     reply[5]<=reply_seq;reply[6]<=reply_op;reply[7]<=reply_status;
     if(score_reply)begin
      reply[8]<=score_received_compressed[7:0];reply[9]<=score_received_compressed[15:8];
      reply[10]<=score_received_compressed[23:16];reply[11]<=score_received_compressed[31:24];
      reply[12]<=score_page_index[7:0];reply[13]<=score_page_index[15:8];
      reply[14]<=score_page_count[7:0];reply[15]<=score_page_count[15:8];
      reply[16]<={4'd0,score_capture_blocked,score_loading,score_show_requested,score_valid};reply[17]<=0;
      reply[18]<=score_decoded_bytes[7:0];reply[19]<=score_decoded_bytes[15:8];
      reply[20]<=score_decoded_bytes[23:16];reply[21]<=score_decoded_bytes[31:24];
     end else begin
      reply[8]<=received_count[7:0];reply[9]<={6'd0,received_count[9:8]};
      reply[10]<=guide_count[7:0];reply[11]<={6'd0,guide_count[9:8]};
      reply[12]<=guide_time_cs[7:0];reply[13]<=guide_time_cs[15:8];
      reply[14]<=guide_duration_cs[7:0];reply[15]<=guide_duration_cs[15:8];
      reply[16]<={4'd0,guide_demo,guide_loading,guide_playing,guide_valid};
      reply[17]<={6'd0,guide_speed};reply[18]<=guide_index[7:0];reply[19]<={6'd0,guide_index[9:8]};
      reply[20]<=0;reply[21]<=0;
     end
     crc_index<=4;tx_crc<=16'hffff;state<=CRC_REPLY;
    end
    CRC_REPLY:begin
     tx_crc<=next_crc;
     if(crc_index==21)begin reply[22]<=next_crc[7:0];reply[23]<=next_crc[15:8];state<=CACHE;end
     else crc_index<=crc_index+1'b1;
    end
    CACHE:begin
     if(cacheable)begin
      for(i=0;i<24;i=i+1)last_reply[i]<=reply[i];
      last_request<=request_identity;cache_valid<=1;
     end
     tx_index<=0;state<=SEND;
    end
    SEND:if(tx_ready && !tx_valid)begin
     tx_valid<=1;tx_data<=reply[tx_index];
     if(tx_index==23)state<=IDLE;else tx_index<=tx_index+1'b1;
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
