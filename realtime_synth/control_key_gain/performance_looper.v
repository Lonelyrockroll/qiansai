`timescale 1ns/1ps
// Four mixed-instrument layers in a synchronous 1024x144 event RAM.
// Timestamp is the audio-frame position (20.48 us at 50 MHz / 1024).
// Commands: 1 record one layer, 2 undo, 3 play/stop, 4 duration, 5 clear.
module performance_looper #(
 parameter FRAMES_2=97656,FRAMES_4=195313,FRAMES_8=390625,PREP_FRAMES=48828,
 parameter MAX_EVENTS=256,MIN_FRAMES=12208
)(input wire clk,rst,sample_tick,session,audio_ready,stop,
 input wire command_valid,input wire [2:0] command,
 input wire live_valid,input wire [122:0] live_data,output wire live_ready,
 output wire out_valid,output wire [122:0] out_data,output wire [2:0] out_source,input wire out_ready,
 output reg playing,recording,output wire pending_record,
 output reg [2:0] layers,output reg [1:0] duration_index,output reg [18:0] position,
 output reg [18:0] actual_length,output reg [9:0] actual_cs,position_cs,
 output reg [6:0] progress,output reg [2:0] notice,output reg event_full,
 output wire [35:0] layer_counts,output reg [31:0] replayed_events);
 reg [143:0] memory[0:1023];reg [9:0] read_address;reg [143:0] read_data;
 reg [8:0] count[0:3],index[0:3];reg [143:0] cached[0:3];reg [3:0] cache_valid;
 reg [8:0] work_count;reg preparing,arm_next;reg [15:0] prep_count;
 reg [18:0] previous_length[0:3];reg [9:0] previous_cs[0:3];
 reg [1:0] scan_layer,read_layer;reg [1:0] read_state;reg [11:0] bar_counter;
 wire [18:0] cap_frames=duration_index==0?FRAMES_2:duration_index==1?FRAMES_4:FRAMES_8;
 wire [18:0] length_frames=layers!=0?actual_length:cap_frames;
 wire [11:0] bar_frames=(length_frames+19'd127)>>7;
 reg [15:0] ms_phase;reg [3:0] ms_digit;
 reg [3:0] flush_pending;
 function [3:0] layer_mask(input [2:0] n);begin case(n)0:layer_mask=0;1:layer_mask=1;2:layer_mask=3;3:layer_mask=7;default:layer_mask=15;endcase end endfunction
 wire [9:0] cap_cs=duration_index==0?10'd200:duration_index==1?10'd400:10'd800;
 wire [9:0] finish_cs=position_cs+((ms_phase>=48976 && ms_digit==9)?1'b1:1'b0);
 wire active=!stop && !command_valid && !sample_tick;
 reg due;reg [1:0] due_layer;integer k;
 always @*begin
  due=0;due_layer=0;
  for(k=0;k<4;k=k+1)if(!due && session && audio_ready && playing && k<layers && cache_valid[k] && cached[k][141:123]<=position)begin due=1;due_layer=k;end
 end
 assign pending_record=preparing || arm_next;
 assign out_valid=active && (flush_pending!=0 || live_valid || due);
 assign out_data=flush_pending!=0?{2'b11,117'd0,flush_pending}:live_valid?live_data:cached[due_layer][122:0];
 assign out_source=(flush_pending!=0 || live_valid)?3'd0:({1'b0,due_layer}+3'd1);
 assign live_ready=active && flush_pending==0 && out_ready;
 wire accepted_live=live_ready && live_valid;
 wire accepted_flush=active && flush_pending!=0 && out_ready;
 wire accepted_replay=active && flush_pending==0 && !live_valid && due && out_ready;
 wire write_event=accepted_live && session && recording && work_count<MAX_EVENTS;
 always @(posedge clk)begin
  if(write_event)memory[{layers[1:0],work_count[7:0]}]<={2'b0,position,live_data};
  read_data<=memory[read_address];
 end
 genvar g;
 generate for(g=0;g<4;g=g+1)begin:counts_out
  assign layer_counts[g*9 +: 9]=(recording && layers==g)?work_count:count[g];
 end endgenerate
 integer i;
 task rewind;
  begin
   position<=0;position_cs<=0;ms_phase<=0;ms_digit<=0;progress<=0;bar_counter<=0;cache_valid<=0;read_state<=0;scan_layer<=0;
   for(i=0;i<4;i=i+1)index[i]<=0;
  end
 endtask
 task abort_take;
  begin recording<=0;preparing<=0;arm_next<=0;work_count<=0;prep_count<=0;end
 endtask
 always @(posedge clk)begin
  if(rst)begin
   playing<=0;recording<=0;preparing<=0;arm_next<=0;layers<=0;duration_index<=2;actual_length<=0;actual_cs<=0;position_cs<=0;ms_phase<=0;ms_digit<=0;flush_pending<=0;
   position<=0;progress<=0;notice<=0;event_full<=0;replayed_events<=0;work_count<=0;prep_count<=0;
   read_address<=0;read_state<=0;scan_layer<=0;read_layer<=0;cache_valid<=0;bar_counter<=0;
   for(i=0;i<4;i=i+1)begin count[i]<=0;index[i]<=0;cached[i]<=0;previous_length[i]<=0;previous_cs[i]<=0;end
  end else begin
   if(accepted_flush)flush_pending<=0;
   if(command_valid)begin
   case(command)
    1:begin
     if(recording)begin
      if(position+1<MIN_FRAMES)notice<=5;
      else begin
       recording<=0;count[layers]<=work_count;work_count<=0;flush_pending<=flush_pending|layer_mask(layers);rewind();
       if(work_count!=0)begin
        previous_length[layers]<=actual_length;previous_cs[layers]<=actual_cs;
        actual_length<=position+1'b1;actual_cs<=finish_cs;
       end
       if(work_count!=0)begin layers<=layers+1'b1;notice<=0;end
       else begin notice<=7;if(layers==0)playing<=0;end
      end
     end else if(preparing || arm_next)begin abort_take();notice<=0;end
     else if(layers==4)notice<=2;
     else if(!session)notice<=6;
     else begin
      notice<=0;event_full<=0;work_count<=0;
      if(playing && layers!=0)arm_next<=1;
      else begin preparing<=1;prep_count<=0;playing<=0;rewind();end
     end
    end
    2:begin
     notice<=0;
     if(recording || preparing || arm_next)begin abort_take();if(layers==0)begin playing<=0;rewind();end end
     else if(layers!=0)begin
      layers<=layers-1'b1;count[layers-1'b1]<=0;cache_valid[layers-1'b1]<=0;read_state<=0;
      flush_pending<=flush_pending | (4'd1 << (layers-1'b1));
      actual_length<=previous_length[layers-1'b1];actual_cs<=previous_cs[layers-1'b1];
      if(previous_length[layers-1'b1]!=actual_length)begin flush_pending<=flush_pending|layer_mask(layers);rewind();end
      if(layers==1)begin playing<=0;actual_length<=0;actual_cs<=0;rewind();end
     end else notice<=1;
    end
    3:begin
     notice<=0;
     if(recording || preparing || arm_next)begin abort_take();playing<=0;flush_pending<=flush_pending|layer_mask(layers);rewind();end
     else if(layers==0)notice<=1;
     else begin playing<=!playing;flush_pending<=flush_pending|layer_mask(layers);rewind();end
    end
    4:begin
     if(layers!=0 || recording || preparing || arm_next)notice<=4;
     else begin duration_index<=duration_index==2?0:duration_index+1'b1;notice<=0;rewind();end
    end
    5:begin
     playing<=0;layers<=0;actual_length<=0;actual_cs<=0;flush_pending<=flush_pending|layer_mask(layers);event_full<=0;notice<=0;replayed_events<=0;abort_take();rewind();
     for(i=0;i<4;i=i+1)count[i]<=0;
    end
    default:;
   endcase
  end else if(stop || !session)begin
   if(stop)flush_pending<=0;else if(playing)flush_pending<=flush_pending|layer_mask(layers);
   playing<=0;abort_take();rewind();
  end else begin
   if(write_event)work_count<=work_count+1'b1;
   else if(accepted_live && recording && work_count>=MAX_EVENTS)begin event_full<=1;notice<=3;end
   if(accepted_replay)begin
    index[due_layer]<=index[due_layer]+1'b1;cache_valid[due_layer]<=0;replayed_events<=replayed_events+1'b1;
   end
   // One read port is shared by all layers; cached heads make arbitration independent of RAM latency.
   case(read_state)
    0:begin
     if(playing && scan_layer<layers && !cache_valid[scan_layer] && index[scan_layer]<count[scan_layer])begin
      read_address<={scan_layer,index[scan_layer][7:0]};read_layer<=scan_layer;read_state<=1;
     end else scan_layer<=scan_layer+1'b1;
    end
    1:read_state<=2;
    2:begin cached[read_layer]<=read_data;cache_valid[read_layer]<=1;read_state<=0;scan_layer<=scan_layer+1'b1;end
    default:read_state<=0;
   endcase
   if(sample_tick && audio_ready)begin
    if(preparing)begin
     if(prep_count>=PREP_FRAMES-1)begin
      preparing<=0;recording<=1;playing<=1;work_count<=0;notice<=0;rewind();
     end else prep_count<=prep_count+1'b1;
    end else if(playing || recording)begin
     if(position>=length_frames-1)begin
      flush_pending<=flush_pending|layer_mask(layers);rewind();
      if(recording)begin
       recording<=0;count[layers]<=work_count;work_count<=0;
       if(work_count!=0)begin
        previous_length[layers]<=actual_length;previous_cs[layers]<=actual_cs;
        layers<=layers+1'b1;if(layers==0)begin actual_length<=cap_frames;actual_cs<=cap_cs;end
       end
       else begin notice<=7;if(layers==0)playing<=0;end
      end else if(arm_next)begin
       recording<=1;arm_next<=0;work_count<=0;notice<=0;event_full<=0;
      end
     end else begin
      position<=position+1'b1;
      if(ms_phase>=48976)begin ms_phase<=ms_phase-16'd48976;if(ms_digit==9)begin ms_digit<=0;position_cs<=position_cs+1'b1;end else ms_digit<=ms_digit+1'b1;end
      else ms_phase<=ms_phase+16'd1024;
      if(bar_counter>=bar_frames-1)begin bar_counter<=0;if(progress!=127)progress<=progress+1'b1;end
      else bar_counter<=bar_counter+1'b1;
     end
    end
   end
  end
 end
 end
endmodule
