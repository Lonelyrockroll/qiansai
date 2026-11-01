`timescale 1ns/1ps
// Digital bench: real v26 melody core, original 4x melodic mix, limiter, bypass FX,
// and audio_tx's own frame tick. Drum input zero. No FPGA/analog measurement.
module tb_modal32;
 reg clk=0,rst=1,cv=0,cg=0,cr=0,hot=0;always #10 clk=~clk;
 wire tick,ready,valid,busy,overrun,clip;
 reg [4:0] id=0;reg [31:0] step=0;reg [15:0] level=16384,release_step=8;
 wire signed [15:0] engine_pcm,dry,pcm;
 wire signed [23:0] music;wire [31:0] active_mask;wire [5:0] active;
 synth_engine_shared dut(.clk(clk),.rst(rst),.sample_tick(tick),.cfg_valid(cv),.cfg_ready(ready),
  .cfg_voice(id),.cfg_gate(cg),.cfg_restart(cr),.cfg_step(step),.cfg_wave(3'd4),.cfg_level(level),
  .cfg_attack(16'd672),.cfg_decay(16'd2),.cfg_sustain(16'd0),.cfg_release(release_step),
  .pcm(engine_pcm),.pcm_valid(valid),.busy(busy),.overrun(overrun),.clipped(clip),
  .voice_active_mask(active_mask),.active_voices(active),.mix_sum(music));
`ifdef MUTE_MODE_12
 defparam dut.piano.MODE_MASK=32'hfffff7ff;
`endif
 reg signed [25:0] mix_total=0;
 wire signed [25:0] boosted=$signed({{2{music[23]}},music})<<<2;
 always @(posedge clk)if(rst)mix_total<=0;else mix_total<=boosted;
 wire amp_ready,amuting,aclear,aclip,alim,alate;wire [31:0] limited_frames;
 audio_output output_stage(.clk(clk),.rst(rst),.sample_tick(tick),.panic(1'b0),.wake_request(1'b0),
  .hold_open(1'b1),.active_voices(active),.mix_sum(mix_total[23:0]),.gain_mode(hot?2'd2:2'd1),
  .pcm(dry),.ready(amp_ready),.muting(amuting),.clear_engine(aclear),.clipped(aclip),
  .limited(alim),.limiter_overrun(alate),.limited_frames(limited_frames));
 wire fxlate,fxclip;
 audio_effects effects(.clk(clk),.rst(rst),.clear(aclear),.sample_tick(tick),
  .audio_enable(amp_ready && !amuting),.dry_pcm(dry),.cfg_valid(1'b0),.cfg_mask(3'd0),
  .cfg_reverb_mix(8'd0),.cfg_delay_mix(8'd0),.cfg_chorus_mix(8'd0),.cfg_feedback(8'd0),
  .cfg_delay_time(2'd0),.cfg_room(2'd0),.cfg_rate(2'd0),.cfg_depth(2'd0),
  .pcm(pcm),.overrun(fxlate),.clipped(fxclip));
 audio_tx #(.PT_BIAS(683)) tx(.clk(clk),.rst(rst),.pcm_left(pcm),.pcm_right(pcm),.sample_tick(tick));

 reg [31:0] pitches[0:31],modes[0:31],contributing[0:31];
 integer cycles=0,tick_cycle=-1,last_latency=0,max_cycles=0,frames=0,lane;
 integer wav,observed,logf,n,s,full=0,i,v,phase=0,index=0;
 reg [1023:0] prefix;
 reg signed [15:0] onset[0:7];
 always @(posedge clk)begin
  cycles=cycles+1;
  if(tick)begin
   if(tick_cycle>=0 && cycles-tick_cycle!=1024)$fatal(1,"incorrect sample period");
   tick_cycle=cycles;frames=frames+1;
  end
  if(!rst && dut.piano.valid[3])begin
   for(lane=0;lane<4;lane=lane+1)begin
    modes[dut.piano.add_index[7:3]][{dut.piano.add_index[2:0],lane[1:0]}]=dut.piano.alive[lane];
    if(($signed(dut.piano.products[lane])>>>15)!=0)
     contributing[dut.piano.add_index[7:3]][{dut.piano.add_index[2:0],lane[1:0]}]=1'b1;
   end
  end
  if(!rst && dut.piano_done && dut.voice==0 && phase!=0 && index<8)begin
   if(phase==1)onset[index]=dut.piano_sample;
   else if(dut.piano_sample!==onset[index])$fatal(1,"retrigger differs at sample %d",index);
   index=index+1;
  end
 end
 always @(negedge clk)if(!rst && valid)begin
  last_latency=cycles-tick_cycle;
  if(last_latency>max_cycles)max_cycles=last_latency;
  if(last_latency>=1024)$fatal(1,"deadline");
 end
 task cfg(input [4:0] voice,input [31:0] freq,input gate,restart,input [15:0] vol,rel);
 begin
  @(negedge clk);while(!ready)@(negedge clk);
  id=voice;step=freq;cg=gate;cr=restart;level=vol;release_step=rel;cv=1;
  @(negedge clk);cv=0;
 end endtask
 task frame;
 begin @(posedge clk);while(!tick)@(posedge clk);@(negedge clk);end endtask
 // Read the pre-edge value of pcm, i.e. the same word sampled by audio_tx.
 task sample_to_file;
 begin
  @(posedge clk);while(!tick)@(posedge clk);
  if((^pcm)===1'bx)$fatal(1,"X PCM");
  $fwrite(wav,"%c%c",pcm[7:0],pcm[15:8]);
  $fwrite(observed,"%0d %0d %08h",active,last_latency,active_mask);
  for(v=0;v<(full?32:1);v=v+1)$fwrite(observed," %08h",modes[v]);
  $fwrite(observed,"\n");@(negedge clk);
 end endtask
 initial begin
  if(!$value$plusargs("PREFIX=%s",prefix))$fatal(1,"missing prefix");
  if(!$value$plusargs("N=%d",n))n=2048;
  if($test$plusargs("FULL"))full=1;
  if($test$plusargs("HOT"))hot=1;
  $readmemh("white_steps.hex",pitches);
  if(!full)pitches[0]=32'd23068672; // 11 / 2048 of sample rate, near C4.
  wav=$fopen($sformatf("%0s.pcm",prefix),"wb");
  observed=$fopen($sformatf("%0s.frames",prefix),"w");
  logf=$fopen($sformatf("%0s.stats",prefix),"w");
  if(!wav || !observed || !logf)$fatal(1,"open evidence");
  for(i=0;i<32;i=i+1)begin modes[i]=0;contributing[i]=0;end
  repeat(4)@(negedge clk);rst=0;
  repeat(200)frame(); // Give the v26 real output warmup/gain slew time before attack.
  if(!amp_ready)$fatal(1,"output warmup failed");
  phase=1;index=0;
  for(i=0;i<(full?32:1);i=i+1)cfg(i,pitches[i],1,1,hot?65535:16384,8);
  repeat(full?160:512)frame();
  if(index!=8 || active!==(full?32:1))$fatal(1,"onset/voices");
  for(i=0;i<32;i=i+1)contributing[i]=0;
  repeat(n)sample_to_file();
  $fclose(wav);$fclose(observed);
  $fwrite(logf,"nonzero_products");
  for(i=0;i<(full?32:1);i=i+1)$fwrite(logf," %08h",contributing[i]);
  $fwrite(logf,"\n");
  if(overrun || clip || aclip || alate || fxlate || fxclip || (!hot && limited_frames!=0))
   $fatal(1,"stress/clipping failure engClip=%d lim=%d fxClip=%d",clip,limited_frames,fxclip);
  if(full && !hot)begin
   phase=0;
   cfg(0,pitches[0],0,0,16384,8);repeat(16)frame();
   if(dut.piano.gains[0]>65535-14*8 || dut.piano.gains[0]<65535-16*8)$fatal(1,"real release taper");
   cfg(0,pitches[0],1,1,16384,8);phase=2;index=0;repeat(12)frame();
   if(index!=8)$fatal(1,"missing retrigger");
   phase=0;
   for(i=0;i<32;i=i+1)cfg(i,pitches[i],0,0,16384,32768);
   repeat(12)frame();if(active!=0 || pcm!==0)$fatal(1,"release did not silence output");
   cfg(0,0,1,1,16384,8);repeat(10)frame();
   if(active!=0 || pcm!==0 || modes[0]!==0)$fatal(1,"zero step");
   cfg(0,pitches[0],1,1,0,8);repeat(10)frame();
   if(active!=0 || pcm!==0)$fatal(1,"zero level");
   cfg(0,32'hffffffff,1,1,16384,8);repeat(10)frame();
   if(dut.step[0]!==32'h0ff00000 || modes[0]==0 || modes[0][31])$fatal(1,"upper clamp / bandlimit");
   $fwrite(logf,"max_step_mask %08h\n",modes[0]);
  end
  $fdisplay(logf,"max_cycles %0d frames %0d limiter_frames %0d",max_cycles,frames,limited_frames);
  $fclose(logf);
  $display("PASS modal32 scenario full=%d n=%d maxcycles=%d",full,n,max_cycles);$finish;
 end
 initial begin #180000000;$fatal(1,"bench timeout");end
endmodule
