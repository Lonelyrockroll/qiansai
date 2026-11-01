`timescale 1ns/1ps
module tb_audio;
 reg clk=0,rst=1,tick=0,adjust=0,select_depth=0,up=1,clear=0,cfg=0,gate=0;
 always #5 clk=~clk;
 parameter VOICES=1;
 reg [4:0] voice=0;reg [2:0] wave_id=0;reg [31:0] step=23012828;
 wire [3:0] bend;wire [2:0] depth;wire signed [13:0] offset;
 pitch_expression expr(.clk(clk),.rst(rst),.tick(tick),.clear(clear),.adjust(adjust),
  .select_depth(select_depth),.increase(up),.bend_position(bend),.vibrato_depth(depth),.pitch_offset(offset));
 wire ready,done,overrun,clipped;wire signed [23:0] mix;
 synth_engine_shared #(.VOICES(VOICES)) engine(.clk(clk),.rst(rst),.sample_tick(tick),
  .pitch_offset(offset),.cfg_valid(cfg),.cfg_ready(ready),.cfg_voice(voice),.cfg_gate(gate),
  .cfg_restart(gate),.cfg_step(step),.cfg_wave(wave_id),.cfg_level(16'd16384),
  .cfg_attack(16'd672),.cfg_decay(16'd6),.cfg_sustain(16'd65535),.cfg_release(16'd8),
  .pcm_valid(done),.overrun(overrun),.clipped(clipped),.mix_sum(mix));
 task command(input [4:0] v,input [2:0] tone,input [31:0] hz_step);
  begin @(negedge clk);while(!ready)@(negedge clk);
   voice=v;wave_id=tone;step=hz_step;gate=1;cfg=1;@(negedge clk);cfg=0;end
 endtask
 task turn(input held,input dir,input integer detents);
  integer j;
  begin for(j=0;j<detents;j=j+1)begin @(negedge clk);adjust=1;select_depth=held;up=dir;
   @(negedge clk);adjust=0; end end
 endtask
 integer f,n,cycles,max_cycles=0,samples,file,tone,piano,plain,i;
 reg [8*160-1:0] filename;
 initial begin
  if(!$value$plusargs("OUT=%s",filename) || !$value$plusargs("N=%d",samples))$fatal(1,"provide OUT/N");
  if(!$value$plusargs("TONE=%d",tone))tone=0;
  plain=$test$plusargs("PLAIN");file=$fopen(filename,"w");if(!file)$fatal;
  repeat(3)@(negedge clk);rst=0;
  for(i=0;i<VOICES;i=i+1)command(i,(VOICES==1 ? tone : ((i%2) ? 4 : 1)),23012828+i*17231);
  for(n=0;n<samples;n=n+1)begin
   if(!plain)begin
    if(n==(VOICES==1?8000:1))turn(0,1,4);
    if(n==(VOICES==1?30000:2))turn(1,1,5);
   end
   @(negedge clk);tick=1;@(negedge clk);tick=0;cycles=1;
   while(!done && cycles<1024)begin @(negedge clk);cycles=cycles+1;end
   if(cycles>=1024 || overrun || clipped || (^mix===1'bx))$fatal(1,"frame %d invalid",n);
   if(cycles>max_cycles)max_cycles=cycles;
   $fdisplay(file,"%0d %0d %0d %0d",mix,offset,bend,depth);
  end
  $fclose(file);$display("PASS %d voices %d frames max %d /1024 clocks",VOICES,samples,max_cycles);$finish;
 end
endmodule
