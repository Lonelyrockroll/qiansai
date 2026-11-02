`timescale 1ns/1ps
// Full-rate mono effects, 50 MHz scheduling, one output per 48828.125 Hz frame.
// Independent chorus (fractional modulated delay), feedback delay, Schroeder room.
module audio_effects(
 input wire clk,rst,clear,sample_tick,audio_enable,
 input wire signed [15:0] dry_pcm,
 input wire cfg_valid,input wire [2:0] cfg_mask,
 input wire [7:0] cfg_reverb_mix,cfg_delay_mix,cfg_chorus_mix,cfg_feedback,
 input wire [1:0] cfg_delay_time,cfg_room,cfg_rate,cfg_depth,
 output reg signed [15:0] pcm,output reg valid,
 output wire busy,pending,tail_active,
 output reg overrun,clipped,output reg [23:0] clipped_frames,
 output reg [31:0] frames,
 output reg [2:0] mask,
 output reg [7:0] reverb_mix,delay_mix,chorus_mix,feedback,
 output reg [1:0] delay_time,room,rate,depth
);
 localparam IDLE=0,CWAIT0=1,CGET0=2,CWAIT1=3,CGET1=4,CMUL=5,CINTERP=6,CBLEND=7,COUT=8,
 DWAIT=9,DREAD=10,DMUL=11,DWRITE=12,RWAIT=13,RREAD=14,RLP=15,RMUL=16,RWRITE=17,
 FMUL=18,FSUM=19,FGAIN=20,OUTPUT=21;
 reg [4:0] state=IDLE;
 reg config_pending=0;reg [2:0] p_mask;
 reg [7:0] p_r,p_d,p_c,p_f;reg [1:0] p_time,p_room,p_rate,p_depth;
 reg [7:0] r_mix=0,d_mix=0,c_mix=0;
 reg [8:0] mute_gain=0;
 reg [18:0] tail_count=0;
 assign busy=state!=IDLE;assign pending=config_pending;assign tail_active=tail_count!=0;
 reg signed [15:0] chorus_memory[0:1023] /* synthesis syn_ramstyle="distributed_ram" */;
 reg signed [15:0] delay_memory[0:8191];
 reg signed [17:0] room_memory[0:4095];
 reg [9:0] ca,cwa,cp=0;reg [12:0] da,dwa,dp=0;reg [11:0] ra,rwa;
 reg cwe=0,dwe=0,rwe=0;
 reg signed [15:0] cwd,dwd,crd,drd;reg signed [17:0] rwd,rrd;
 // Average pairs on write and interpolate the return. The existing 8192-word
 // line now reaches 320 ms without allocating another block of sample RAM.
 reg delay_half=0;
 reg signed [15:0] delay_input_previous=0,delay_tap_previous=0,delay_return=0;
 reg [10:0] c_age=0;reg [13:0] d_age=0;
 reg [9:0] rp[0:5],r_age[0:5];reg signed [17:0] lowpass[0:3];
 always @(posedge clk)begin
  crd<=chorus_memory[ca];drd<=delay_memory[da];rrd<=room_memory[ra];
  if(cwe)chorus_memory[cwa]<=cwd;
  if(dwe)delay_memory[dwa]<=dwd;
  if(rwe)room_memory[rwa]<=rwd;
 end
 function signed [31:0] shr0(input signed [31:0] x,input [4:0] bits);
  begin shr0=x<0?-((-x)>>>bits):(x>>>bits);end
 endfunction
 function signed [15:0] sat16(input signed [31:0] x);
  begin sat16=x>32767?16'sh7fff:x< -32768?16'sh8000:x[15:0];end
 endfunction
 function signed [17:0] sat18(input signed [31:0] x);
  begin sat18=x>131071?18'sh1ffff:x< -131072?18'sh20000:x[17:0];end
 endfunction
 function [9:0] length_for(input [2:0] line);
  begin case(line)0:length_for=631;1:length_for=761;2:length_for=887;3:length_for=1013;
   4:length_for=127;default:length_for=239;endcase end
 endfunction
 function [11:0] base_for(input [2:0] line);
  begin case(line)0:base_for=0;1:base_for=631;2:base_for=1392;3:base_for=2279;
   4:base_for=3292;default:base_for=3419;endcase end
 endfunction
 function [7:0] approach(input [7:0] current,input [7:0] target);
  begin
   if(current<target)approach=target-current<=4?target:current+4;
   else if(current>target)approach=current-target<=4?target:current-4;else approach=current;
  end
 endfunction
 wire [12:0] delay_samples=delay_time==0?13'd1953:delay_time==1?13'd3906:delay_time==2?13'd5859:13'd7813;
 wire [7:0] room_gain=room==0?8'd224:room==1?8'd240:8'd248;
 reg [31:0] phase=0;
 wire [31:0] phase_step=rate==0?32'd21990:rate==1?32'd39582:rate==2?32'd70369:32'd105553;
 wire signed [15:0] lfo;
 chorus_lfo modulation(.clk(clk),.addr(phase[31:17]),.value(lfo));
 wire signed [31:0] lfo_delta=depth==0?($signed(lfo)>>>1):depth==1?$signed(lfo):
                                    depth==2?(($signed(lfo)*3)>>>1):($signed(lfo)<<<1);
 wire signed [31:0] delay_q8=32'sd131072+lfo_delta;
 wire [9:0] c_distance=delay_q8[17:8];
 reg [9:0] current_distance;reg [7:0] fraction;
 reg cvalid0,cvalid1;reg signed [15:0] x,c0,c1,c_tap,ch_sample,d_tap;
 wire signed [31:0] delay_input_pair=$signed(ch_sample)+$signed(delay_input_previous);
 wire signed [31:0] delay_tap_pair=$signed(d_tap)+$signed(delay_tap_previous);
 wire signed [15:0] delay_input_average=shr0(delay_input_pair,1);
 reg signed [31:0] mul0,mul1,room_sum,lp_next,room_write,ap_input,ap_output,reverb_out;
 reg signed [17:0] r_tap;reg [2:0] line;
 reg signed [31:0] final0,final1,final2,final_sum,final_product;
 wire [8:0] dry_gain=9'd256-{1'b0,d_mix}-{1'b0,r_mix};
 wire signed [31:0] final_scaled=shr0(final_product,8);
 integer i;
 task erase_history;
 begin
  cp<=0;dp<=0;c_age<=0;d_age<=0;phase<=0;tail_count<=0;
  delay_half<=0;delay_input_previous<=0;delay_tap_previous<=0;delay_return<=0;
  room_sum<=0;lp_next<=0;room_write<=0;ap_input<=0;ap_output<=0;reverb_out<=0;
  for(i=0;i<6;i=i+1)begin rp[i]<=0;r_age[i]<=0;end
  for(i=0;i<4;i=i+1)lowpass[i]<=0;
 end
 endtask
 task apply_pending;
 begin
  mask<=p_mask;reverb_mix<=p_r;delay_mix<=p_d;chorus_mix<=p_c;feedback<=p_f;
  delay_time<=p_time;room<=p_room;rate<=p_rate;depth<=p_depth;config_pending<=0;
 end
 endtask
 always @(posedge clk)begin
  if(rst)begin
   state<=IDLE;valid<=0;pcm<=0;overrun<=0;clipped<=0;clipped_frames<=0;frames<=0;
   config_pending<=0;mask<=0;reverb_mix<=48;delay_mix<=64;chorus_mix<=80;feedback<=96;
   delay_time<=2;room<=1;rate<=1;depth<=1;
   p_mask<=0;p_r<=0;p_d<=0;p_c<=0;p_f<=0;p_time<=0;p_room<=0;p_rate<=0;p_depth<=0;
   r_mix<=0;d_mix<=0;c_mix<=0;mute_gain<=0;
   ca<=0;cwa<=0;da<=0;dwa<=0;ra<=0;rwa<=0;cwe<=0;dwe<=0;rwe<=0;cwd<=0;dwd<=0;rwd<=0;
   current_distance<=512;fraction<=0;cvalid0<=0;cvalid1<=0;x<=0;c0<=0;c1<=0;c_tap<=0;ch_sample<=0;d_tap<=0;
   mul0<=0;mul1<=0;r_tap<=0;line<=0;final0<=0;final1<=0;final2<=0;final_sum<=0;final_product<=0;
   erase_history();
  end else begin
   valid<=0;cwe<=0;dwe<=0;rwe<=0;
   if(sample_tick && busy)overrun<=1;
   if(cfg_valid)begin
    p_mask<=cfg_mask;p_r<=cfg_reverb_mix;p_d<=cfg_delay_mix;p_c<=cfg_chorus_mix;p_f<=cfg_feedback;
    p_time<=cfg_delay_time;p_room<=cfg_room;p_rate<=cfg_rate;p_depth<=cfg_depth;config_pending<=1;
   end
   if(clear)begin
    state<=IDLE;pcm<=0;mute_gain<=0;r_mix<=0;d_mix<=0;c_mix<=0;
    clipped<=0;clipped_frames<=0;overrun<=0;
    erase_history();if(config_pending && !cfg_valid)apply_pending();
   end else case(state)
    IDLE:if(sample_tick)begin
     frames<=frames+1'b1;x<=dry_pcm;phase<=phase+phase_step;
     if(audio_enable)mute_gain<=mute_gain>=224?9'd256:mute_gain+32;
     else mute_gain<=mute_gain<=32?9'd0:mute_gain-32;
     if(dry_pcm!=0 && (r_mix!=0 || d_mix!=0 || c_mix!=0))tail_count<=(r_mix!=0 || d_mix!=0)?19'd292969:19'd1024;
     else if(tail_count!=0)tail_count<=tail_count-1'b1;
     if(config_pending)begin
      r_mix<=approach(r_mix,0);d_mix<=approach(d_mix,0);c_mix<=approach(c_mix,0);
      if(r_mix==0 && d_mix==0 && c_mix==0 && !cfg_valid)begin erase_history();apply_pending();end
     end else begin
      // A newly filled delay starts with the input at the switch instant.
      // Fade it in only once valid history exists, including a held note.
      r_mix<=approach(r_mix,(mask[0] && r_age[3]>=1013)?reverb_mix:8'd0);
      d_mix<=approach(d_mix,(mask[1] && d_age>=delay_samples)?delay_mix:8'd0);
      c_mix<=approach(c_mix,(mask[2] && c_age>c_distance)?chorus_mix:8'd0);
     end
     current_distance<=c_distance;fraction<=delay_q8[7:0];
     cvalid0<=c_age>=c_distance;cvalid1<=c_age>c_distance;
     ca<=cp-c_distance;state<=CWAIT0;
    end
    CWAIT0:state<=CGET0;
    CGET0:begin c0<=cvalid0?crd:16'sd0;ca<=cp-current_distance-1'b1;state<=CWAIT1;end
    CWAIT1:state<=CGET1;
    CGET1:begin c1<=cvalid1?crd:16'sd0;state<=CMUL;end
    CMUL:begin mul0<=c0*$signed(10'd256-{2'b0,fraction});mul1<=c1*$signed({1'b0,fraction});state<=CINTERP;end
    CINTERP:begin c_tap<=sat16(shr0(mul0+mul1,8));state<=CBLEND;end
    CBLEND:begin
     mul0<=x*$signed(10'd256-{2'b0,c_mix});mul1<=c_tap*$signed({1'b0,c_mix});
     cwe<=1;cwa<=cp;cwd<=x;cp<=cp+1'b1;if(c_age<1024)c_age<=c_age+1'b1;state<=COUT;
    end
    COUT:begin ch_sample<=sat16(shr0(mul0+mul1,8));da<=dp-delay_samples;state<=DWAIT;end
    DWAIT:state<=DREAD;
    DREAD:begin d_tap<=d_age>=delay_samples?drd:16'sd0;state<=DMUL;end
    DMUL:begin
     mul0<=delay_input_average*$signed(10'd256-{2'b0,feedback});
     mul1<=d_tap*$signed({1'b0,feedback});
     delay_return<=delay_half?d_tap:shr0(delay_tap_pair,1);
     state<=DWRITE;
    end
    DWRITE:begin
     delay_half<=!delay_half;delay_input_previous<=ch_sample;
     if(delay_half)begin
      dwe<=1;dwa<=dp;dwd<=sat16(shr0(mul0+mul1,8));dp<=dp+1'b1;
      delay_tap_previous<=d_tap;if(d_age<8192)d_age<=d_age+1'b1;
     end
     line<=0;room_sum<=0;ra<=base_for(0)+rp[0];state<=RWAIT;
    end
    RWAIT:state<=RREAD;
    RREAD:begin r_tap<=r_age[line]>=length_for(line)?rrd:18'sd0;state<=RLP;end
    RLP:begin
     if(line<4)lp_next<=shr0($signed(r_tap)+$signed(lowpass[line]),1);
     else ap_output<=$signed(r_tap)-shr0(ap_input,1);
     state<=RMUL;
    end
    RMUL:begin
     if(line<4)begin mul0<=ch_sample*$signed(10'd256-{2'b0,room_gain});mul1<=lp_next*$signed({1'b0,room_gain});end
     else room_write<=ap_input+shr0(ap_output,1);
     state<=RWRITE;
    end
    RWRITE:begin
     rwe<=1;rwa<=base_for(line)+rp[line];
     if(rp[line]+1'b1==length_for(line))rp[line]<=0;else rp[line]<=rp[line]+1'b1;
     if(r_age[line]<length_for(line))r_age[line]<=r_age[line]+1'b1;
     if(line<4)begin
      rwd<=sat18(shr0(mul0+mul1,8));lowpass[line]<=sat18(lp_next);room_sum<=room_sum+$signed(r_tap);
      if(line==3)ap_input<=shr0(room_sum+$signed(r_tap),2);
     end else begin rwd<=sat18(room_write);ap_input<=ap_output;end
     if(line==5)begin reverb_out<=ap_output;state<=FMUL;end
     else begin line<=line+1'b1;ra<=base_for(line+1'b1)+rp[line+1'b1];state<=RWAIT;end
    end
    FMUL:begin
     final0<=ch_sample*$signed({1'b0,dry_gain});
     final1<=delay_return*$signed({1'b0,d_mix});final2<=(reverb_out<<<1)*$signed({1'b0,r_mix});state<=FSUM;
    end
    FSUM:begin final_sum<=shr0(final0+final1+final2,8);state<=FGAIN;end
    FGAIN:begin final_product<=final_sum*$signed((mask==0 && r_mix==0 && d_mix==0 && c_mix==0)?10'd256:{1'b0,mute_gain});state<=OUTPUT;end
    OUTPUT:begin
     pcm<=sat16(final_scaled);valid<=1;state<=IDLE;
     if(final_scaled>32767 || final_scaled< -32768)begin clipped<=1;clipped_frames<=clipped_frames+1'b1;end
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
