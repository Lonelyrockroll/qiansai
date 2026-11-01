`timescale 1ns/1ps
// Two logical 512x32 event banks share a 1024x32 memory. The bank is the
// address MSB so Gowin maps this to two native 1024x16 physical BSRAMs;
// separate 512x32 SDP arrays are each expanded into two physical BSRAMs.
// Uploads write the inactive bank; only a complete, validated CRC32
// transaction may replace the playing score.
module guide_player #(
 parameter CLK_HZ=50000000,
 parameter UPLOAD_TIMEOUT_CYCLES=CLK_HZ*10
)(
 input wire clk,rst,audio_tick,
 input wire command_valid,output wire command_ready,
 input wire [7:0] command_op,command_length,input wire [159:0] command_payload,
 output reg response_valid,output reg [7:0] response_status,
 input wire ui_valid,input wire [3:0] ui_action,
 output wire guide_valid,guide_playing,output reg guide_loading,guide_demo,
 output wire [15:0] guide_time_cs,output reg [15:0] guide_duration_cs,
 output reg [9:0] guide_count,output wire [9:0] guide_index,
 output wire [1:0] guide_speed,output wire [31:0] guide_current,guide_onset,guide_next,
 output wire [63:0] guide_colors,output reg [9:0] received_count
);
 localparam IDLE=0,WRITE=1,CONTROL_WAIT=2;
 reg [1:0] state;
 reg active_bank,write_bank,write_enable;
 reg [8:0] write_address;
 reg [31:0] write_data;
 reg [31:0] event_memory[0:1023];
 wire [8:0] read_address;
 reg [31:0] read_event,read_demo;
 wire [31:0] read_data=guide_demo?read_demo:read_event;
 reg [9:0] expected_count;
 reg [15:0] upload_duration,last_time;
 reg [31:0] expected_crc,running_crc;
 reg [31:0] timeout_count;
 reg [1:0] slot,byte_index;
 reg [2:0] packet_count;
 reg [127:0] packet_words;
 reg [31:0] word;
 reg [31:0] crc_next;
 reg reload,control;
 reg [3:0] control_action;
 reg [1:0] control_delay;
 wire timeline_settled;
 integer i;
 assign command_ready=state==IDLE;
 assign guide_valid=guide_count!=0;
 // The built-in white-key phrase is generated below as a small combinational ROM.
 localparam DEMO_COUNT=56,DEMO_DURATION=1600;
 function [4:0] demo_key(input [4:0] n);
  begin case(n)
   0,1,13,14,15,27:demo_key=14;
   2,3,6,16,17,20:demo_key=18;
   4,5,18,19:demo_key=19;
   7,8,21,22:demo_key=17;
   9,10,23,24:demo_key=16;
   default:demo_key=15;
  endcase end
 endfunction
 function [31:0] demo_event(input [8:0] address);
  reg [4:0] n;reg [15:0] tm;
  begin
   n=address[5:1];
   tm=n*16'd50+(n>=7?16'd50:0)+(n>=14?16'd50:0)+(n>=21?16'd50:0);
   if(address[0])tm=tm+((n==6 || n==13 || n==20 || n==27)?16'd95:16'd45);
   demo_event={8'd0,2'd0,!address[0],demo_key(n),tm};
  end
 endfunction
 always @(posedge clk)begin
  if(write_enable)event_memory[{write_bank,write_address}]<=write_data;
  read_event<=event_memory[{active_bank,read_address}];
  read_demo<=demo_event(read_address);
 end
 function [31:0] crc32_byte(input [31:0] crc,input [7:0] value);
  reg [31:0] q;integer k;
  begin q=crc^{24'd0,value};for(k=0;k<8;k=k+1)q=(q>>1)^(q[0]?32'hedb88320:32'd0);crc32_byte=q;end
 endfunction
 always @*begin
  case(slot)
   0:word=packet_words[31:0];1:word=packet_words[63:32];
   2:word=packet_words[95:64];default:word=packet_words[127:96];
  endcase
  crc_next=crc32_byte(running_crc,word[byte_index*8 +: 8]);
 end
 guide_timeline timeline(.clk(clk),.rst(rst),.audio_tick(audio_tick),.reload(reload),
  .event_count(guide_count),.duration_cs(guide_duration_cs),
  .control_valid(control),.control_action(control_action),
  .read_address(read_address),.read_data(read_data),
  .settled(timeline_settled),.playing(guide_playing),.time_cs(guide_time_cs),.event_index(guide_index),.speed(guide_speed),
  .current_mask(guide_current),.onset_mask(guide_onset),.next_mask(guide_next),.colors(guide_colors));

 always @(posedge clk)begin
  if(rst)begin
   state<=IDLE;active_bank<=0;write_bank<=1;write_enable<=0;write_address<=0;write_data<=0;
   guide_loading<=0;guide_demo<=1;guide_count<=DEMO_COUNT;guide_duration_cs<=DEMO_DURATION;
   received_count<=0;expected_count<=0;upload_duration<=0;last_time<=0;
   expected_crc<=0;running_crc<=32'hffffffff;timeout_count<=0;
   slot<=0;byte_index<=0;packet_count<=0;packet_words<=0;
   reload<=0;control<=0;control_action<=0;control_delay<=0;response_valid<=0;response_status<=0;
  end else begin
   write_enable<=0;reload<=0;control<=0;response_valid<=0;
   if(guide_loading)begin
    if(timeout_count==UPLOAD_TIMEOUT_CYCLES-1)begin guide_loading<=0;timeout_count<=0;end
    else timeout_count<=timeout_count+1'b1;
   end
   if(ui_valid)begin
    if(ui_action==7)begin guide_demo<=1;guide_count<=DEMO_COUNT;guide_duration_cs<=DEMO_DURATION;reload<=1;end
    else if(ui_action<=8)begin control<=1;control_action<=ui_action;end
   end
   if(command_valid && command_ready)begin
    response_valid<=1;response_status<=0;
    case(command_op)
     0:if(command_length!=0)response_status<=3;
     1:begin
      if(command_length!=8 || command_payload[15:0]==0 || command_payload[15:0]>512 ||
         command_payload[31:16]==0)response_status<=3;
      else begin
       guide_loading<=1;write_bank<=!active_bank;received_count<=0;timeout_count<=0;
       expected_count<=command_payload[9:0];upload_duration<=command_payload[31:16];
       expected_crc<=command_payload[63:32];running_crc<=32'hffffffff;last_time<=0;
      end
     end
     2:begin
      if(!guide_loading)response_status<=5;
      else if(command_payload[23:16]==0 || command_payload[23:16]>4 ||
              command_length!=(8'd3+{command_payload[21:16],2'b0}))response_status<=3;
      else if(command_payload[15:0]!=received_count ||
              ({1'b0,received_count}+{8'd0,command_payload[18:16]})>expected_count)response_status<=5;
      else begin
       packet_count<=command_payload[18:16];packet_words<=command_payload[151:24];
       slot<=0;byte_index<=0;state<=WRITE;response_valid<=0;timeout_count<=0;
      end
     end
     3:begin
      if(command_length!=0)response_status<=3;
      else if(!guide_loading || received_count!=expected_count)response_status<=5;
      else if((~running_crc)!=expected_crc)begin response_status<=1;guide_loading<=0;end
      else begin
       active_bank<=write_bank;guide_demo<=0;guide_count<=expected_count;guide_duration_cs<=upload_duration;
       guide_loading<=0;reload<=1;
      end
     end
     4:begin
      if(command_length!=1 || command_payload[7:0]>8)response_status<=3;
      else begin
       response_valid<=0;state<=CONTROL_WAIT;control_delay<=2;
       if(command_payload[7:0]==7)begin
        guide_demo<=1;guide_count<=DEMO_COUNT;guide_duration_cs<=DEMO_DURATION;reload<=1;
       end else begin control<=1;control_action<=command_payload[3:0];end
      end
     end
     default:response_status<=2;
    endcase
   end
   if(state==WRITE)begin
    timeout_count<=0;
    if(byte_index==0 && (word[31:24]!=0 || word[15:0]>upload_duration ||
                        (received_count!=0 && word[15:0]<last_time)))begin
     guide_loading<=0;state<=IDLE;response_valid<=1;response_status<=3;
    end else begin
     running_crc<=crc_next;
     if(byte_index==3)begin
      write_enable<=1;write_address<=received_count[8:0];write_data<=word;
      received_count<=received_count+1'b1;last_time<=word[15:0];byte_index<=0;
      if({1'b0,slot}+1'b1==packet_count)begin state<=IDLE;response_valid<=1;response_status<=0;end
      else slot<=slot+1'b1;
     end else byte_index<=byte_index+1'b1;
    end
   end
   if(state==CONTROL_WAIT)begin
    if(control_delay!=0)control_delay<=control_delay-1'b1;
    else if(timeline_settled)begin state<=IDLE;response_valid<=1;response_status<=0;end
   end
  end
 end
endmodule

// A synchronous read port with one pipeline cycle. All events at one time are
// accumulated before exposing a new chord to the pixel-clock snapshot.
module guide_timeline(
 input wire clk,rst,audio_tick,reload,
 input wire [9:0] event_count,input wire [15:0] duration_cs,
 input wire control_valid,input wire [3:0] control_action,
 output wire [8:0] read_address,input wire [31:0] read_data,
 output wire settled,output reg playing,output reg [15:0] time_cs,output reg [9:0] event_index,
 output reg [1:0] speed,output reg [31:0] current_mask,onset_mask,next_mask,
 output reg [63:0] colors
);
 localparam FETCH=0,WAIT_READ=1,DECODE=2,HOLD=3,END_DATA=4,SEEK_FETCH=5,SEEK_WAIT=6,SEEK_USE=7;
 reg [2:0] state;
 reg [9:0] cursor,group_end,applied_index;
 reg [15:0] group_time,seek_base,seek_target;
 reg [127:0] current_state,group_state;
 reg [31:0] group_onsets,lookahead,rebuild_onsets;
 reg have_group,have_lookahead,at_start,rebuilding,seek_forward,seek_start;
 reg [16:0] fraction;
 reg [3:0] accent_left;
 wire [8:0] increment=speed==0?9'd128:speed==1?9'd192:speed==2?9'd256:9'd320;
 wire [17:0] advanced={1'b0,fraction}+{9'd0,increment};
 wire centisecond=playing && audio_tick && advanced>=125000;
 wire finished=centisecond && time_cs>=duration_cs-1'b1;
 assign read_address=cursor[8:0];
 assign settled=!rebuilding && (state==HOLD || state==END_DATA);
 function [127:0] apply_event(input [127:0] states,input [31:0] ev);
  reg [127:0] result;begin result=states;result[{ev[23:22],ev[20:16]}]=ev[21];apply_event=result;end
 endfunction
 function [31:0] keys(input [127:0] states);
  begin keys=states[31:0]|states[63:32]|states[95:64]|states[127:96];end
 endfunction
 function [63:0] palette(input [127:0] states);
  reg [63:0] result;integer k;
  begin
   result=0;
   for(k=0;k<32;k=k+1)begin
    if(states[k])result[k*2 +: 2]=0;
    else if(states[k+32])result[k*2 +: 2]=1;
    else if(states[k+64])result[k*2 +: 2]=2;
    else if(states[k+96])result[k*2 +: 2]=3;
   end
   palette=result;
  end
 endfunction
 task reset_position;
  begin
   playing<=0;time_cs<=0;fraction<=0;event_index<=0;current_state<=0;
   current_mask<=0;onset_mask<=0;next_mask<=0;colors<=0;accent_left<=0;
   cursor<=0;group_end<=0;applied_index<=0;group_time<=0;group_state<=0;group_onsets<=0;rebuild_onsets<=0;
   have_group<=0;have_lookahead<=0;lookahead<=0;at_start<=1;rebuilding<=0;
   seek_base<=0;seek_target<=0;seek_forward<=0;seek_start<=0;state<=FETCH;
  end
 endtask
 task rebuild(input [15:0] target_time);
  begin
   seek_target<=target_time;rebuilding<=1;cursor<=0;group_end<=0;have_group<=0;have_lookahead<=0;
   group_state<=0;group_onsets<=0;current_state<=0;applied_index<=0;rebuild_onsets<=0;state<=FETCH;
  end
 endtask
 always @(posedge clk)begin
  if(rst)begin speed<=2;reset_position();end
  else if(reload || finished || (control_valid && (control_action==0 || control_action==3)))begin
   reset_position();
  end else begin
   if(playing && audio_tick)begin
    if(centisecond)begin
     fraction<=advanced-125000;time_cs<=time_cs+1'b1;
     if(accent_left!=0)begin accent_left<=accent_left-1'b1;if(accent_left==1)onset_mask<=0;end
    end else fraction<=advanced[16:0];
   end
   case(state)
    FETCH:begin
     if(cursor>=event_count)begin
      if(have_group)begin have_lookahead<=0;next_mask<=group_onsets & keys(group_state);state<=HOLD;end
      else state<=END_DATA;
     end else state<=WAIT_READ;
    end
    WAIT_READ:state<=DECODE;
    DECODE:begin
     if(!have_group)begin
      group_time<=read_data[15:0];group_state<=apply_event(current_state,read_data);
      group_onsets<=read_data[21]?(32'd1<<read_data[20:16]):32'd0;
      have_group<=1;group_end<=cursor+1'b1;cursor<=cursor+1'b1;state<=FETCH;
     end else if(read_data[15:0]==group_time)begin
      group_state<=apply_event(group_state,read_data);
      if(read_data[21])group_onsets<=group_onsets|(32'd1<<read_data[20:16]);
      group_end<=cursor+1'b1;cursor<=cursor+1'b1;state<=FETCH;
     end else begin
      lookahead<=read_data;have_lookahead<=1;next_mask<=group_onsets & keys(group_state);state<=HOLD;
     end
    end
    HOLD:begin
     if((playing && group_time<=time_cs) || (rebuilding && group_time<=seek_target))begin
      current_state<=group_state;applied_index<=group_end;
      if(rebuilding)rebuild_onsets<=group_time==seek_target?(group_onsets & keys(group_state)):32'd0;
      if(!rebuilding)begin
       current_mask<=keys(group_state);colors<=palette(group_state);onset_mask<=group_onsets & keys(group_state);
       event_index<=group_end;accent_left<=group_onsets!=0?4'd15:4'd0;at_start<=0;
      end
      if(have_lookahead)begin
       group_time<=lookahead[15:0];group_state<=apply_event(group_state,lookahead);
       group_onsets<=lookahead[21]?(32'd1<<lookahead[20:16]):32'd0;
       group_end<=cursor+1'b1;cursor<=cursor+1'b1;have_lookahead<=0;state<=FETCH;
      end else begin
       have_group<=0;next_mask<=0;state<=END_DATA;
       if(rebuilding)begin
        current_mask<=keys(group_state);colors<=palette(group_state);onset_mask<=group_onsets & keys(group_state);
        event_index<=group_end;accent_left<=group_onsets!=0?4'd15:4'd0;time_cs<=seek_target;
        rebuilding<=0;at_start<=0;
       end
      end
     end else if(rebuilding)begin
      current_mask<=keys(current_state);colors<=palette(current_state);
      onset_mask<=rebuild_onsets;event_index<=applied_index;
      time_cs<=seek_target;rebuilding<=0;accent_left<=15;at_start<=0;
     end
    end
    END_DATA:begin
     if(rebuilding)begin
      current_mask<=keys(current_state);colors<=palette(current_state);onset_mask<=0;
      event_index<=event_count;time_cs<=seek_target;rebuilding<=0;accent_left<=0;at_start<=0;
     end
    end
    SEEK_FETCH:begin
     if(cursor>=event_count)rebuild(seek_target);
     else state<=SEEK_WAIT;
    end
    SEEK_WAIT:state<=SEEK_USE;
    SEEK_USE:begin
     if(read_data[21] && seek_forward && (read_data[15:0]>seek_base || (seek_start && read_data[15:0]>=seek_base)))
      rebuild(read_data[15:0]);
     else begin
      if(read_data[21] && !seek_forward && read_data[15:0]<seek_base)seek_target<=read_data[15:0];
      cursor<=cursor+1'b1;state<=SEEK_FETCH;
     end
    end
    default:state<=FETCH;
   endcase
   if(control_valid)begin
    case(control_action)
     1:playing<=event_count!=0;
     2:playing<=0;
     4:playing<=!playing && event_count!=0;
     5,6:begin
      playing<=0;seek_base<=time_cs;seek_target<=control_action==5?time_cs:16'd0;
      seek_forward<=control_action==5;seek_start<=at_start;cursor<=0;state<=SEEK_FETCH;fraction<=0;
     end
     8:speed<=speed+1'b1;
     default:;
    endcase
   end
  end
 end
endmodule
