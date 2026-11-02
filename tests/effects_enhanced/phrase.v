`timescale 1ns/1ps
module phrase;
reg clk=0;always #10 clk=~clk;
reg rst=1,tick=0,cv=0,gate=0;
reg [4:0] voice=0;reg [31:0] step=0;reg [2:0] wave=4;
wire ready,done,busy,overrun,clipped;wire signed [23:0] mix;
synth_engine_shared dut(.clk(clk),.rst(rst),.sample_tick(tick),
 .cfg_valid(cv),.cfg_ready(ready),.pitch_offset(14'sd0),.cfg_voice(voice),.cfg_gate(gate),.cfg_restart(gate),
 .cfg_step(step),.cfg_wave(wave),.cfg_level(16'd14000),.cfg_attack(16'd672),
 .cfg_decay(16'd6),.cfg_sustain(16'd52000),.cfg_release(16'd48),
 .pcm_valid(done),.busy(busy),.overrun(overrun),.clipped(clipped),.mix_sum(mix));
integer f,j,fd,elapsed,maximum=0;reg signed [23:0] scaled;reg [15:0] pcm;
task send_note(input [4:0] id,input on,input [31:0] increment,input [2:0] timbre);begin
 @(negedge clk);while(!ready)@(negedge clk);voice=id;gate=on;step=increment;wave=timbre;cv=1;
 @(negedge clk);cv=0;
end endtask
initial begin
 fd=$fopen("phrase.pcm","wb");repeat(10)@(negedge clk);rst=0;
 for(f=0;f<390625;f=f+1)begin
  case(f)
   9766:send_note(0,1,32'd23013019,4);
   15625:send_note(0,0,32'd23013019,4);
   29297:send_note(0,1,32'd28994783,4);
   35156:send_note(0,0,32'd28994783,4);
   48828:send_note(0,1,32'd34479504,4);
   54688:send_note(0,0,32'd34479504,4);
   73242:begin send_note(0,1,32'd23013019,4);send_note(1,1,32'd28994783,4);send_note(2,1,32'd34479504,4);end
   87891:begin send_note(0,0,32'd23013019,4);send_note(1,0,32'd28994783,4);send_note(2,0,32'd34479504,4);end
   122070:begin send_note(0,1,32'd23013019,1);send_note(1,1,32'd28994783,1);send_note(2,1,32'd34479504,1);end
   219727:begin send_note(0,0,32'd23013019,1);send_note(1,0,32'd28994783,1);send_note(2,0,32'd34479504,1);end
  endcase
  @(negedge clk);tick=1;@(negedge clk);tick=0;elapsed=0;
  while(!done)begin @(negedge clk);elapsed=elapsed+1;if(elapsed>1020)$fatal(1,"audio deadline");end
  if(overrun || clipped || ^mix===1'bx)$fatal(1,"invalid dry audio");
  if(elapsed>maximum)maximum=elapsed;
  // Production melodic boost 4x followed by gain_mode=1 (1024/8192).
  scaled=mix>>>1;if(scaled>30000 || scaled< -30000)$fatal(1,"limiter needed");
  pcm=scaled[15:0];$fwrite(fd,"%c%c",pcm[7:0],pcm[15:8]);
  repeat(4)@(negedge clk);
 end
 $fclose(fd);$display("PASS HDL phrase 390625 frames, max engine clocks %0d",maximum);$finish;
end
endmodule
