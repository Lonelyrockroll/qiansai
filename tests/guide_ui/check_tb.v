`timescale 1ns/1ps
module guide_ui_check;
 reg clk=0,rst=1;always #5 clk=!clk;
 reg [10:0] x=0,y=0;
 reg [15:0] tm=0,duration=0;reg [9:0] index=0,count=0,lpc=0;reg drums=0;
 wire [23:0] rgb;
 panel_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
 .bend_position(4'd4),.focus(4'd9),.vibrato_depth(3'd2),.fx(3'd1),.timbre(3'd4),.volume(7'd7),.voices(6'd3),.mode(2'd2),
 .calibrated(1'b1),.fault(1'b0),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
 .loop_actual_cs(lpc),.loop_position_cs(10'd0),.loop_layers(3'd2),.loop_notice(3'd0),.loop_duration(2'd2),
 .loop_playing(1'b1),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd20),.drum_mode(drums),
 .notice(4'd0),.pressed(32'h211),.peak(8'd100),.guide_valid(1'b1),.guide_playing(1'b1),.guide_loading(1'b0),.guide_demo(1'b0),
 .guide_time_cs(tm),.guide_duration_cs(duration),.guide_count(count),.guide_index(index),.guide_speed(2'd2),
 .guide_target(32'h54000),.guide_onset(32'h44000),.guide_next(32'h1a0000),.guide_colors(64'h1000000000),.actual_keys(32'h4c000),.rgb(rgb));
 task pixel(input integer px,py,input [23:0] want);
 begin @(negedge clk);x=px;y=py;repeat(4)@(negedge clk);if(rgb!==want)$fatal(1,"pixel %d,%d got %h expected %h",px,py,rgb,want);end endtask
 initial begin repeat(3)@(negedge clk);rst=0;tm=65535;duration=4820;count=512;index=511;lpc=800;
 repeat(200)@(negedge clk);
 if(dut.time_bcd!==20'h65535 || dut.duration_bcd!==20'h04820 || dut.count_bcd!==20'h00512 || dut.index_bcd!==20'h00511 || dut.loop_bcd!==20'h00800)$fatal(1,"BCD conversion");
 tm=0;duration=1;count=0;index=1;lpc=0;repeat(200)@(negedge clk);
 if(dut.time_bcd!==0 || dut.duration_bcd!==1 || dut.count_bcd!==0 || dut.index_bcd!==1 || dut.loop_bcd!==0)$fatal(1,"BCD update");
 pixel(464,180,24'h67d8b8);pixel(528,180,24'hb8ddd1);pixel(592,180,24'hebb376);
 pixel(480,180,24'he88874);pixel(496,180,24'hebf0e7);pixel(552,120,24'he9c38a);
 drums=1;pixel(480,180,24'he88874);pixel(464,180,24'h67d8b8);
 pixel(755,430,24'h79d7bd);pixel(760,430,24'h28495a);
 $display("PASS BCD extremes, chord onset/hold colors, preview, actual-key borders, drum-page isolation and focus 9");$finish;
 end
endmodule