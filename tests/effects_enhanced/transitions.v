`timescale 1ns/1ps
module tb;
reg clk=0;always #10 clk=~clk;reg rst=1,tick=0,cv=0,clear=0,en=1;
reg signed [15:0] x=0;reg [2:0] mask=7;reg [7:0] r=64,d=64,c=128;
wire signed [15:0] y;wire valid,pending,overrun,clipped;integer i,cycles;
audio_effects dut(.clk(clk),.rst(rst),.clear(clear),.sample_tick(tick),.audio_enable(en),.dry_pcm(x),
 .cfg_valid(cv),.cfg_mask(mask),.cfg_reverb_mix(r),.cfg_delay_mix(d),.cfg_chorus_mix(c),.cfg_feedback(8'd128),
 .cfg_delay_time(2'd3),.cfg_room(2'd2),.cfg_rate(2'd3),.cfg_depth(2'd3),
 .pcm(y),.valid(valid),.pending(pending),.overrun(overrun),.clipped(clipped));
task frame(input signed [15:0] sample);begin
 @(negedge clk);x=sample;tick=1;@(negedge clk);tick=0;cycles=0;
 while(!valid)begin @(negedge clk);cycles=cycles+1;if(cycles>100)$fatal(1,"deadline");end
 if(^y===1'bx || overrun || clipped)$fatal(1,"invalid output");
 repeat(3)@(negedge clk);
end endtask
task apply_config;begin cv=1;@(negedge clk);cv=0;end endtask
initial begin
 repeat(5)@(negedge clk);rst=0;apply_config();for(i=0;i<100;i=i+1)frame(0);
 // Worst legal memory/feedback/depth settings, signed excitation.
 for(i=0;i<5000;i=i+1)frame(i%2?-12000:12000);
 // Fade out to bypass while notes are present; reaches exact input.
 mask=0;apply_config();for(i=0;i<100;i=i+1)frame(1234);
 if(pending || y!=1234)$fatal(1,"bypass transition");
 // A simultaneous clear+configuration must survive and apply exactly once.
 mask=7;clear=1;cv=1;@(negedge clk);clear=0;cv=0;
 for(i=0;i<100;i=i+1)frame(0);
 if(pending || dut.mask!=7)$fatal(1,"lost pending configuration");
 frame(-12000);for(i=0;i<200000;i=i+1)begin frame(0);if(i>190000 && y!=0)$fatal(1,"nonzero limit cycle");end
 // Monitor/audio-disable ramp reaches zero even with a continuing source.
 for(i=0;i<100;i=i+1)frame(12000);en=0;
 for(i=0;i<20;i=i+1)begin frame(12000);if(i>10 && y!=0)$fatal(1,"mute ramp");end
 $display("PASS transition, simultaneous clear/config, signed tail termination, audio-disable ramp");$finish;
end
endmodule
