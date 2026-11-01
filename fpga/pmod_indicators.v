// J9 audio bar grows from L8 toward L1. The manual test addresses physical lamp IDs.
module pmod_indicators #(
 parameter STEP=15000000, HOLD_SAMPLES=2442, FALL_SAMPLES=1221
)(
 input wire clk,rst,test,single,input wire [2:0] select_lamp,
 input wire sample_tick,muted,input wire [15:0] magnitude,
 output reg testing,output wire [7:0] lamps,output wire [7:0] led_n
);
 // Ceiling of 32768 * 10^(dBFS/20) for -54, -45, -36, -30, -24, -18, -12, -6.
 reg [15:0] sampled;
 reg have_sample,have_level;
 reg [7:0] level,bar;
 reg [11:0] remaining;
 always @(posedge clk)begin
  if(rst || muted)begin
   sampled<=0;have_sample<=0;have_level<=0;level<=0;bar<=0;remaining<=0;
  end else begin
   have_sample<=sample_tick;have_level<=have_sample;
   if(sample_tick)sampled<=magnitude;
   if(have_sample)level<={sampled>=16'd16423,sampled>=16'd8231,sampled>=16'd4126,sampled>=16'd2068,
                          sampled>=16'd1037,sampled>=16'd520,sampled>=16'd185,sampled>=16'd66};
   if(have_level)begin
    if(level>=bar)begin bar<=level;remaining<=HOLD_SAMPLES-1;end
    else if(remaining!=0)remaining<=remaining-1'b1;
    else begin bar<=bar>>1;remaining<=FALL_SAMPLES-1;end
   end
  end
 end
 // Old PC/Bluetooth lamp tests explicitly override the meter, then return to live audio.
 reg [23:0] step_count;
 reg [2:0] index,held_lamp;
 reg hold_one;
 wire [7:0] meter_lamps={bar[0],bar[1],bar[2],bar[3],bar[4],bar[5],bar[6],bar[7]};
 assign lamps=testing?(8'h01<<(hold_one?held_lamp:index)):meter_lamps;
 assign led_n=~lamps;
 always @(posedge clk)begin
  if(rst)begin testing<=0;index<=0;step_count<=0;hold_one<=0;held_lamp<=0;end
  else if(test)begin testing<=1;index<=0;step_count<=0;hold_one<=single;held_lamp<=select_lamp;end
  else if(testing)begin
   if(step_count==STEP-1)begin step_count<=0;if(index==7)testing<=0;else index<=index+1'b1;end
   else step_count<=step_count+1'b1;
  end
 end
endmodule
