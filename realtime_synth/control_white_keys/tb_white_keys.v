// Physical scan + real post-accept key mask + actual 1024x600 pixel pipeline.
`timescale 1ns/1ps
module tb_white_keys;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,play=1,recal=0,ready=1;
 reg [1:0] mode=2;
 reg [4:0] test_key=14;
 reg [31:0] down=0;
 reg eoc=1;reg [12:0] adc=0;integer delay_count=0;
 wire soc,calibrated,fault,cv,gate;wire [4:0] addr,voice;
 wire [31:0] pressed,step;wire [15:0] scans;
 keyboard_input #(.SLOT_CYCLES(12),.SETTLE_CYCLES(2),.ADC_TIMEOUT(30),.STARTUP_CYCLES(3)) keys(
  .clk(clk),.rst(rst),.recalibrate(recal),.play(play),.mode(mode),.test_key(test_key),
  .press_threshold(16'd256),.release_threshold(16'd128),.max_level(16'd16384),.velocity_scale(16'd64),
  .mux_addr(addr),.adc_soc(soc),.adc_eoc(eoc),.adc_data(adc),.calibrated(calibrated),.fault(fault),
  .pressed_mask(pressed),.scan_count(scans),.cfg_ready(ready),.cfg_valid(cv),.cfg_voice(voice),.cfg_gate(gate),.cfg_step(step));
 // Independent table of the physical PCB address->logical sensor wiring.
 reg [4:0] physical_to_key[0:31];
 always @(posedge clk)begin
  if(soc)begin eoc<=0;delay_count<=2;end
  else if(delay_count>0)begin
   delay_count<=delay_count-1;
   if(delay_count==1)begin eoc<=1;adc<=down[physical_to_key[addr]]?13'd4500:13'd4000;end
  end
 end
 reg [31:0] reference[0:31];integer ons=0,offs=0;
 always @(posedge clk)if(cv && ready && !rst)begin
  if(step!==reference[voice])$fatal(1,"key index %0d step %0d expected %0d",voice,step,reference[voice]);
  if(gate)ons=ons+1;else offs=offs+1;
 end
 reg [10:0] x=0,y=0;wire [23:0] rgb;reg drum=0;
 panel_renderer video(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
  .focus(4'd0),.fx(3'd0),.timbre(3'd4),.volume(7'd25),.voices(6'd0),
  .mode(mode),.calibrated(calibrated),.fault(fault),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
  .loop_actual_cs(10'd0),.loop_position_cs(10'd0),.loop_layers(3'd0),.loop_notice(3'd0),.loop_duration(2'd2),
  .loop_playing(1'b0),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd0),
  .drum_mode(drum),.notice(4'd0),.pressed(pressed),.peak(8'd0),.rgb(rgb));
 task pixel(input integer px,input integer py,input [23:0] expected);begin
  @(negedge clk);x=px;y=py;repeat(3)@(negedge clk);
  if(rgb!==expected)$fatal(1,"pixel (%0d,%0d) rgb %h expected %h mask %h",px,py,rgb,expected,pressed);
 end endtask
 task check_row(input integer py,input [31:0] mask);
 integer j;begin
  for(j=0;j<32;j=j+1)begin
   pixel(64+16*j,py,mask[j]?24'h55dfbd:24'he9edf2);
   pixel(78+16*j,py,mask[j]?24'h55dfbd:24'he9edf2);
   pixel(79+16*j,py,24'h172737);
  end
 end endtask
 integer i,seen;reg [31:0] chord;
 initial begin
  $readmemh("sim/reference_steps.hex",reference);
  for(i=0;i<32;i=i+1)physical_to_key[i]=i;
  for(i=16;i<28;i=i+1)physical_to_key[i]=43-i;
  repeat(4)@(negedge clk);rst=0;wait(calibrated);check_row(414,0);
  for(i=0;i<32;i=i+1)begin
   @(negedge clk);down=32'h1<<i;
   wait(pressed===down);check_row(415,down);check_row(464,down);
   @(negedge clk);down=0;wait(pressed===0);
  end
  chord=32'h80024001; // H1, H15, H18, H32
  @(negedge clk);down=chord;wait(pressed===chord);check_row(420,chord);
  down=32'h80000001;wait(pressed===down);check_row(420,down);
  down=0;wait(pressed===0);repeat(2)@(negedge clk);
  if(ons!=36 || offs!=36)$fatal(1,"duplicate/missing events %d/%d",ons,offs);
  // Single-channel ADC mode uses the same pitch and display index; hold through backpressure.
  @(negedge clk);mode=1;test_key=14;recal=1;@(negedge clk);recal=0;wait(calibrated);
  @(negedge clk);ready=0;down=1<<14;wait(cv);repeat(6)@(negedge clk);
  if(pressed!==0 || step!==reference[14] || voice!=14)$fatal(1,"single channel pending");
  ready=1;wait(pressed===down);check_row(416,down);down=0;wait(pressed===0);
  if(fault)$fatal(1,"ADC fault");
  $display("PASS H1..H32 natural pitches on/off, single-channel C4, chords, scan wiring, 32 full-height white keys and separators");
  $finish;
 end
 initial begin #8000000;$fatal(1,"white-key timeout");end
endmodule
