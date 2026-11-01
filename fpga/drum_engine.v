`timescale 1ns/1ps
// Twelve independent one-shot voices; under 128 clocks/sample, against a 1024-clock budget.
module drum_engine(input wire clk,rst,clear,sample_tick,
 input wire hit_valid,output wire hit_ready,input wire [3:0] hit_pad,
 input wire [15:0] level,input wire [1:0] gain_mode,
 output reg signed [23:0] mix_sum,output reg [11:0] active_mask,
 output reg [5:0] active_voices,output reg busy,overrun,limited,
 output reg [31:0] hit_count,limited_frames,output reg [3:0] last_pad);
 localparam IDLE=0,LOAD=1,ROM_WAIT=2,RING=3,SHAPE=4,TONE=5,NOISE=6,ATTACK=7,ENV=8,ACCUM=9,GAIN=10,OUTPUT=11;
 reg [3:0] state,voice;
 reg [31:0] phase[0:11],phase2[0:11],pitch[0:11];
 reg [15:0] env_t[0:11],env_n[0:11];reg [16:0] age[0:11];
 reg signed [17:0] lp_fast[0:11],lp_slow[0:11];reg open_choked;
 wire [3:0] parameter_pad=state==IDLE?hit_pad:voice;
 wire [31:0] initial_step,body_step,second_step;wire [15:0] tone_decay,noise_decay;
 wire [2:0] fast_shift,slow_shift;wire [3:0] pitch_shift;
 drum_parameters params(.pad(parameter_pad),.initial_step(initial_step),.body_step(body_step),.second_step(second_step),
  .tone_decay(tone_decay),.noise_decay(noise_decay),.fast_shift(fast_shift),.slow_shift(slow_shift),.pitch_shift(pitch_shift));
 reg signed [15:0] oscillator[0:2047];initial $readmemh("drum_oscillator.hex",oscillator);
 reg [10:0] addr1,addr2;reg signed [15:0] sine1,sine2;
 always @(posedge clk)begin sine1<=oscillator[addr1];sine2<=oscillator[addr2];end
 reg [31:0] random_state;
 function [31:0] next_random(input [31:0] old);
  reg [31:0] x;begin x=old^(old<<13);x=x^(x>>17);next_random=x^(x<<5);end
 endfunction
 wire [31:0] random_next=next_random(random_state);
 wire signed [17:0] noise_in={{2{random_next[31]}},random_next[31:16]};
 wire signed [17:0] fast_next=lp_fast[voice]+((noise_in-lp_fast[voice])>>>fast_shift);
 wire signed [17:0] slow_next=lp_slow[voice]+((noise_in-lp_slow[voice])>>>slow_shift);
 reg signed [17:0] noise_band,tone_shape,noise_shape;
 reg signed [31:0] ring_product;
 reg signed [32:0] tone_product,noise_product;
 reg signed [18:0] combined;
 reg signed [24:0] attack_product;
 reg signed [21:0] sum;
 reg [31:0] decay_t_product,decay_n_product;
 reg signed [38:0] master_product;
 wire signed [38:0] scaled=master_product>>>11;
 wire signed [38:0] limit=39'sd112000;
 reg [11:0] mask_work;reg [5:0] voices_work;
 wire [15:0] n_decay=(voice==2 && age[voice]<781)?16'd64800:(voice==4 && open_choked)?16'd64512:noise_decay;
 wire [15:0] t_decay=(voice==4 && open_choked)?16'd64512:tone_decay;
 assign hit_ready=state==IDLE && !sample_tick && !rst && !clear;
 integer i;
 always @(posedge clk)begin
  if(rst || clear)begin
   state<=IDLE;voice<=0;mix_sum<=0;busy<=0;overrun<=0;limited<=0;active_mask<=0;active_voices<=0;
   sum<=0;mask_work<=0;voices_work<=0;open_choked<=0;addr1<=0;addr2<=0;random_state<=32'h817263a5;
   if(rst)begin hit_count<=0;last_pad<=0;limited_frames<=0;end
   for(i=0;i<12;i=i+1)begin phase[i]<=0;phase2[i]<=0;pitch[i]<=0;env_t[i]<=0;env_n[i]<=0;age[i]<=0;lp_fast[i]<=0;lp_slow[i]<=0;end
  end else begin
   if(sample_tick && busy)overrun<=1;
   if(hit_valid && hit_ready && hit_pad<12)begin
    phase[hit_pad]<=0;phase2[hit_pad]<=0;pitch[hit_pad]<=initial_step;
    env_t[hit_pad]<=tone_decay==0?0:65535;env_n[hit_pad]<=noise_decay==0?0:65535;
    age[hit_pad]<=0;lp_fast[hit_pad]<=0;lp_slow[hit_pad]<=0;
    hit_count<=hit_count+1'b1;last_pad<=hit_pad;
    if(hit_pad==3)open_choked<=1;else if(hit_pad==4)open_choked<=0;
   end
   case(state)
    IDLE:if(sample_tick)begin busy<=1;voice<=0;sum<=0;mask_work<=0;voices_work<=0;state<=LOAD;end
    LOAD:begin
     addr1<={voice==11,phase[voice][31:22]};addr2<={voice==11,phase2[voice][31:22]};
     phase[voice]<=phase[voice]+pitch[voice];phase2[voice]<=phase2[voice]+second_step;
     if(pitch[voice]>body_step)pitch[voice]<=pitch[voice]-((pitch[voice]-body_step)>>pitch_shift);
     random_state<=random_next;lp_fast[voice]<=fast_next;lp_slow[voice]<=slow_next;noise_band<=fast_next-slow_next;
     if(env_t[voice]!=0 || env_n[voice]!=0)begin mask_work[voice]<=1;voices_work<=voices_work+1'b1;end
     state<=ROM_WAIT;
    end
    ROM_WAIT:state<=RING;
    RING:begin ring_product<=sine1*sine2;state<=SHAPE;end
    SHAPE:begin
     case(voice)
      0:begin tone_shape<=($signed(sine1)>>>1)+($signed(sine1)>>>3)+($signed(sine2)>>>3);noise_shape<=noise_band>>>3;end
      1:begin tone_shape<=($signed(sine1)>>>2)+($signed(sine2)>>>3);noise_shape<=noise_band-(noise_band>>>2);end
      2:begin tone_shape<=0;noise_shape<=noise_band-(noise_band>>>3);end
      3,4:begin tone_shape<=ring_product>>>18;noise_shape<=noise_band>>>1;end
      5,6,7:begin tone_shape<=($signed(sine1)>>>1)+($signed(sine2)>>>3);noise_shape<=noise_band>>>3;end
      8:begin tone_shape<=ring_product>>>18;noise_shape<=noise_band-(noise_band>>>2);end
      9:begin tone_shape<=($signed(sine1)>>>1)+($signed(sine2)>>>2);noise_shape<=noise_band>>>2;end
      10:begin tone_shape<=($signed(sine1)>>>1)+($signed(sine2)>>>2);noise_shape<=noise_band>>>3;end
      11:begin tone_shape<=($signed(sine1)>>>1)+($signed(sine2)>>>2);noise_shape<=0;end
      default:begin tone_shape<=0;noise_shape<=0;end
     endcase
     state<=TONE;
    end
    TONE:begin tone_product<=tone_shape*$signed({1'b0,env_t[voice]});state<=NOISE;end
    NOISE:begin noise_product<=noise_shape*$signed({1'b0,env_n[voice]});state<=ATTACK;end
    ATTACK:begin
     combined<=$signed(tone_product>>>16)+$signed(noise_product>>>16);
     decay_t_product<=env_t[voice]*t_decay;decay_n_product<=env_n[voice]*n_decay;
     state<=ENV;
    end
    ENV:begin
     attack_product<=combined*$signed({1'b0,(age[voice]<32?age[voice][5:0]+6'd1:6'd32)});
     env_t[voice]<=decay_t_product[31:16];env_n[voice]<=decay_n_product[31:16];
     if(voice==2 && (age[voice]==390 || age[voice]==780) && env_n[voice]!=0)env_n[voice]<=65535;
     if(age[voice]<120000)age[voice]<=age[voice]+1'b1;else begin env_t[voice]<=0;env_n[voice]<=0;end
     state<=ACCUM;
    end
    ACCUM:begin
     sum<=sum+(attack_product>>>5);
     if(voice==11)state<=GAIN;else begin voice<=voice+1'b1;state<=LOAD;end
    end
    GAIN:begin master_product<=sum*$signed({1'b0,level});state<=OUTPUT;end
    OUTPUT:begin
     if(scaled>limit)begin mix_sum<=limit[23:0];limited<=1;limited_frames<=limited_frames+1'b1;end
     else if(scaled< -limit)begin mix_sum<= -limit;limited<=1;limited_frames<=limited_frames+1'b1;end
     else begin mix_sum<=scaled[23:0];limited<=0;end
     active_mask<=mask_work;active_voices<=voices_work;busy<=0;state<=IDLE;
    end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
