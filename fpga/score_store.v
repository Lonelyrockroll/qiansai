`timescale 1ns/1ps
// Single-page RLE bitmap receiver. No bitmap RAM is allocated here: writes go
// to the PC PCM capture buffer, whose other physical port feeds the display.
module score_store #(
 parameter CLK_HZ=50000000,parameter UPLOAD_TIMEOUT_CYCLES=CLK_HZ*10
)(
 input wire clk,rst,
 input wire command_valid,output wire command_ready,
 input wire [7:0] command_op,command_length,input wire [159:0] command_payload,
 output reg response_valid,output reg [7:0] response_status,
 input wire ui_valid,input wire [1:0] ui_action,output wire ui_ready,
 input wire video_visible,capture_busy,capture_ready,
 output reg write_enable,output reg [14:0] write_address,output reg [15:0] write_data,
 output reg valid,show_requested,loading,output wire reserved,capture_blocked,
 output reg [31:0] received_compressed,decoded_bytes,
 output reg [15:0] page_index,page_count
);
 localparam IDLE=0,HIDE=1,INGEST=2,EXPAND=3,CLEAR=4;
 reg [2:0] state;
 reg clear_pending,reply_pending;
 reg [31:0] expected_size,expected_crc,crc,timeout_count;
 reg [127:0] packet;
 reg [4:0] packet_count,packet_index;
 reg await_value;
 reg [7:0] run_count,run_left,run_value,first_byte;
 wire [7:0] input_byte=packet[packet_index*8 +: 8];
 assign command_ready=state==IDLE;
 assign ui_ready=state==IDLE && !loading && !clear_pending && !command_valid;
 assign reserved=valid || loading || clear_pending;
 assign capture_blocked=capture_busy || capture_ready;
 function [31:0] crc32_byte(input [31:0] acc,input [7:0] data);
  reg [31:0] q;integer k;
  begin q=acc^{24'd0,data};for(k=0;k<8;k=k+1)q=(q>>1)^(q[0]?32'hedb88320:32'd0);crc32_byte=q;end
 endfunction
 task finish_reply(input [7:0] status);
  begin
   if(reply_pending)begin response_valid<=1;response_status<=status;end
   reply_pending<=0;state<=IDLE;
  end
 endtask
 task fail_upload(input [7:0] status);
  begin
   valid<=0;show_requested<=0;loading<=0;await_value<=0;
   if(video_visible)clear_pending<=1;
   finish_reply(status);
  end
 endtask
 task control(input [1:0] action,input send_reply);
  begin
   if(action==0)show_requested<=0;
   else if(action==1)begin
    if(valid && !loading && !clear_pending)show_requested<=1;
    else if(send_reply)response_status<=5;
   end else if(action==2)begin
    show_requested<=0;valid<=0;loading<=0;clear_pending<=1;
    reply_pending<=send_reply;response_valid<=0;timeout_count<=0;state<=CLEAR;
   end else if(send_reply)response_status<=3;
  end
 endtask
 always @(posedge clk)begin
  if(rst)begin
   state<=IDLE;clear_pending<=0;reply_pending<=0;
   valid<=0;show_requested<=0;loading<=0;write_enable<=0;write_address<=0;write_data<=0;
   received_compressed<=0;decoded_bytes<=0;page_index<=0;page_count<=0;
   expected_size<=0;expected_crc<=0;crc<=32'hffffffff;timeout_count<=0;
   packet<=0;packet_count<=0;packet_index<=0;await_value<=0;run_count<=0;run_left<=0;run_value<=0;first_byte<=0;
   response_valid<=0;response_status<=0;
  end else begin
   write_enable<=0;response_valid<=0;
   if(clear_pending && !video_visible)clear_pending<=0;
   if(loading || state==CLEAR)timeout_count<=timeout_count+1'b1;
   if((loading || state==CLEAR) && timeout_count==UPLOAD_TIMEOUT_CYCLES-1)begin
    // Never release RAM while a formerly visible page can still be scanned.
    // CLEAR's pending reservation survives this BUSY reply until video acks.
    if(state==CLEAR)finish_reply(4);
    else fail_upload(5);
   end else case(state)
    IDLE:begin
     if(command_valid)begin
      response_valid<=1;response_status<=0;reply_pending<=0;
      case(command_op)
       16:if(command_length!=0)response_status<=3;
       17:begin
        if(command_length!=16 || command_payload[31:0]==0 || command_payload[31:0]>131072 ||
           command_payload[95:80]==0 || command_payload[79:64]>=command_payload[95:80] ||
           command_payload[111:96]!=1024 || command_payload[127:112]!=512)response_status<=3;
        else if(capture_blocked || clear_pending)response_status<=4;
        else begin
         valid<=0;show_requested<=0;loading<=1;await_value<=0;timeout_count<=0;
         received_compressed<=0;decoded_bytes<=0;crc<=32'hffffffff;
         expected_size<=command_payload[31:0];expected_crc<=command_payload[63:32];
         page_index<=command_payload[79:64];page_count<=command_payload[95:80];
         response_valid<=0;reply_pending<=1;state<=HIDE;
        end
       end
       18:begin
        if(command_length<5 || command_payload[31:24]==0 || command_payload[31:24]>16 ||
           command_length!=4+command_payload[31:24])response_status<=3;
        else if(!loading || command_payload[23:0]!=received_compressed ||
                received_compressed+command_payload[31:24]>expected_size)response_status<=5;
        else begin
         packet<=command_payload[159:32];packet_count<=command_payload[28:24];packet_index<=0;
         response_valid<=0;reply_pending<=1;timeout_count<=0;state<=INGEST;
        end
       end
       19:begin
        if(command_length!=0)response_status<=3;
        else if(!loading || received_compressed!=expected_size || decoded_bytes!=65536 || await_value)begin
         response_status<=5;loading<=0;valid<=0;show_requested<=0;
        end else if((~crc)!=expected_crc)begin
         response_status<=1;loading<=0;valid<=0;show_requested<=0;
        end else begin loading<=0;valid<=1;show_requested<=1;end
       end
       20:begin
        if(command_length!=1 || command_payload[7:0]>2)response_status<=3;
        else if(loading)response_status<=4;
        else control(command_payload[1:0],1'b1);
       end
       default:response_status<=2;
      endcase
     end else if(ui_valid && ui_ready)control(ui_action,1'b0);
    end
    HIDE:if(!video_visible)finish_reply(0);
    CLEAR:if(!video_visible)begin clear_pending<=0;finish_reply(0);end
    INGEST:begin
     if(packet_index==packet_count)finish_reply(0);
     else begin
      packet_index<=packet_index+1'b1;received_compressed<=received_compressed+1'b1;
      if(!await_value)begin
       if(input_byte==0)fail_upload(3);
       else begin run_count<=input_byte;await_value<=1;end
      end else begin run_left<=run_count;run_value<=input_byte;await_value<=0;state<=EXPAND;end
     end
    end
    EXPAND:begin
     if(decoded_bytes>=65536)fail_upload(3);
     else begin
      crc<=crc32_byte(crc,run_value);decoded_bytes<=decoded_bytes+1'b1;
      if(!decoded_bytes[0])first_byte<=run_value;
      else begin write_enable<=1;write_address<=decoded_bytes[15:1];write_data<={first_byte,run_value};end
      if(run_left==1)state<=INGEST;else run_left<=run_left-1'b1;
     end
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
