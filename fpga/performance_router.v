`timescale 1ns/1ps
// Source 0 is live; sources 1..4 are Loop layers. Each owns logical note IDs.
// Serialized flush barriers release Loop-owned notes without stopping live notes.
module performance_router(input wire clk,rst,clear,cancel,
 input wire event_valid,output wire event_ready,input wire [122:0] event_data,input wire [2:0] event_source,
 output wire drum_valid,input wire drum_ready,output wire [3:0] drum_pad,
 output wire cfg_valid,input wire cfg_ready,output reg [4:0] cfg_voice,output reg cfg_gate,cfg_restart,
 output wire [31:0] cfg_step,output wire [2:0] cfg_wave,output wire [15:0] cfg_level,cfg_attack,cfg_decay,cfg_sustain,cfg_release,
 input wire [31:0] voice_active_mask,
 output reg [31:0] held_mask,output reg [5:0] held_count,live_held_count,
 output reg [31:0] events_applied,notes_applied,steals,ignored_offs);
 localparam IDLE=0,DRUM=1,SEARCH=2,DECIDE=3,SEND=4,F_SCAN=5,F_WAIT=6,F_LOAD=7,F_SEND=8;
 reg [3:0] state;reg [122:0] payload;reg [2:0] source;
 reg [2:0] owner[0:31];reg [4:0] logical_id[0:31];reg [31:0] valid_mask,live_mask;
 reg [114:0] profiles[0:31];reg [4:0] profile_address;reg [114:0] profile_q,parameters_q;
 always @(posedge clk)begin
  profile_q<=profiles[profile_address];
  if(cfg_valid && cfg_ready)profiles[cfg_voice]<=parameters_q;
 end
 reg [5:0] scan;reg matched,free_found,releasing_found;reg [4:0] match_slot,free_slot,release_slot,steal_cursor;
 reg [4:0] flush_sources;
 wire [4:0] chosen=matched?match_slot:free_found?free_slot:releasing_found?release_slot:steal_cursor;
 assign event_ready=state==IDLE && !rst && !clear && !cancel;
 assign drum_valid=state==DRUM && !cancel && !clear;
 assign drum_pad=payload[118:115];
 assign cfg_valid=(state==SEND || state==F_SEND) && !cancel && !clear;
 assign cfg_wave=parameters_q[114:112];assign cfg_step=parameters_q[111:80];assign cfg_level=parameters_q[79:64];
 assign cfg_attack=parameters_q[63:48];assign cfg_decay=parameters_q[47:32];assign cfg_sustain=parameters_q[31:16];assign cfg_release=parameters_q[15:0];
 function [3:0] pop8(input [7:0] b);integer n;begin pop8=0;for(n=0;n<8;n=n+1)pop8=pop8+b[n];end endfunction
 reg [3:0] h0,h1,h2,h3,l0,l1,l2,l3;
 always @(posedge clk)begin
  h0<=pop8(held_mask[7:0]);h1<=pop8(held_mask[15:8]);h2<=pop8(held_mask[23:16]);h3<=pop8(held_mask[31:24]);
  l0<=pop8((held_mask&live_mask)>>0);l1<=pop8((held_mask&live_mask)>>8);l2<=pop8((held_mask&live_mask)>>16);l3<=pop8((held_mask&live_mask)>>24);
  held_count<={2'd0,h0}+h1+h2+h3;live_held_count<={2'd0,l0}+l1+l2+l3;
 end
 integer i;
 always @(posedge clk)begin
  if(rst || clear)begin
   state<=IDLE;held_mask<=0;valid_mask<=0;live_mask<=0;scan<=0;steal_cursor<=0;flush_sources<=0;
   payload<=0;source<=0;cfg_voice<=0;cfg_gate<=0;cfg_restart<=0;parameters_q<=0;profile_address<=0;
   matched<=0;free_found<=0;releasing_found<=0;match_slot<=0;free_slot<=0;release_slot<=0;
   for(i=0;i<32;i=i+1)begin owner[i]<=0;logical_id[i]<=0;end
   if(rst)begin events_applied<=0;notes_applied<=0;steals<=0;ignored_offs<=0;end
  end else if(cancel)begin state<=IDLE;flush_sources<=0;end
  else case(state)
   IDLE:if(event_valid)begin
    payload<=event_data;source<=event_source;events_applied<=events_applied+1'b1;
    case(event_data[122:121])
     0:if(event_data[119:115]<12)state<=DRUM;
     1:if(event_source<=4)begin state<=SEARCH;scan<=0;matched<=0;free_found<=0;releasing_found<=0;end
     2:if(event_source<=4)begin flush_sources<=5'b00001<<event_source;scan<=0;state<=F_SCAN;end
     3:begin flush_sources<={event_data[3:0],1'b0};scan<=0;state<=F_SCAN;end
    endcase
   end
   DRUM:if(drum_ready)state<=IDLE;
   SEARCH:begin
    if(valid_mask[scan[4:0]] && owner[scan[4:0]]==source && logical_id[scan[4:0]]==payload[119:115])begin matched<=1;match_slot<=scan[4:0];end
    if(!free_found && (!valid_mask[scan[4:0]] || (!held_mask[scan[4:0]] && !voice_active_mask[scan[4:0]])))begin free_found<=1;free_slot<=scan[4:0];end
    if(!releasing_found && valid_mask[scan[4:0]] && !held_mask[scan[4:0]])begin releasing_found<=1;release_slot<=scan[4:0];end
    if(scan==31)state<=DECIDE;else scan<=scan+1'b1;
   end
   DECIDE:begin
    if(!payload[120] && (!matched || !held_mask[match_slot]))begin ignored_offs<=ignored_offs+1'b1;state<=IDLE;end
    else begin
     cfg_voice<=chosen;cfg_gate<=payload[120];cfg_restart<=payload[120] && (!matched || !held_mask[chosen]);
     parameters_q<=payload[114:0];state<=SEND;
     if(payload[120] && !matched)begin
      steal_cursor<=chosen+1'b1;
      if(valid_mask[chosen] && held_mask[chosen])steals<=steals+1'b1;
     end
    end
   end
   SEND:if(cfg_ready)begin
    valid_mask[cfg_voice]<=1;held_mask[cfg_voice]<=cfg_gate;live_mask[cfg_voice]<=source==0;
    owner[cfg_voice]<=source;logical_id[cfg_voice]<=payload[119:115];notes_applied<=notes_applied+1'b1;state<=IDLE;
   end
   F_SCAN:begin
    if(scan==32)begin state<=IDLE;flush_sources<=0;end
    else if(valid_mask[scan[4:0]] && held_mask[scan[4:0]] && flush_sources[owner[scan[4:0]]])begin
     cfg_voice<=scan[4:0];profile_address<=scan[4:0];state<=F_WAIT;
    end else scan<=scan+1'b1;
   end
   F_WAIT:state<=F_LOAD;
   F_LOAD:begin parameters_q<=profile_q;cfg_gate<=0;cfg_restart<=0;state<=F_SEND;end
   F_SEND:if(cfg_ready)begin held_mask[cfg_voice]<=0;notes_applied<=notes_applied+1'b1;scan<=scan+1'b1;state<=F_SCAN;end
   default:state<=IDLE;
  endcase
 end
endmodule
