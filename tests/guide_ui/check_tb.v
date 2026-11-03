`timescale 1ns/1ps
module guide_ui_check;
 reg clk=0,rst=1;always #5 clk=!clk;
 reg [10:0] x=0,y=0;
 reg [15:0] tm=0,duration=0;reg [9:0] index=0,count=0,lpc=0;reg drums=0;
 reg [2:0] page=0,effects=1;reg [3:0] cursor=0;reg confirm=0;
 wire [23:0] rgb;
 panel_renderer dut(.midi_bytes(16'd65535),.midi_messages(16'd12345),.midi_errors(16'd2),.midi_pedal(1'b0),.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
 .ui_page(page),.ui_cursor(cursor),.ui_confirm(confirm),.bend_position(4'd4),.focus(4'd9),.vibrato_depth(3'd2),.fx(effects),.timbre(3'd4),.volume(7'd7),.voices(6'd3),.mode(2'd2),
 .calibrated(1'b1),.fault(1'b0),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
 .loop_actual_cs(lpc),.loop_position_cs(10'd0),.loop_layers(3'd2),.loop_notice(3'd0),.loop_duration(2'd2),
 .loop_playing(1'b1),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd20),.drum_mode(drums),
 .notice(4'd0),.pressed(32'h211),.peak(8'd100),.guide_valid(1'b1),.guide_playing(1'b1),.guide_loading(1'b0),.guide_demo(1'b0),
 .guide_time_cs(tm),.guide_duration_cs(duration),.guide_count(count),.guide_index(index),.guide_speed(2'd2),
 .guide_target(32'h54000),.guide_onset(32'h44000),.guide_next(32'h1a0000),.guide_colors(64'h1000000000),.actual_keys(32'h4c000),.rgb(rgb));
 task pixel(input integer px,py,input [23:0] want);
 begin @(negedge clk);x=px;y=py;repeat(4)@(negedge clk);if(rgb!==want)$fatal(1,"pixel %d,%d got %h expected %h",px,py,rgb,want);end endtask
 integer menu_row,menu_x,menu_y;
 initial begin repeat(3)@(negedge clk);rst=0;tm=65535;duration=4820;count=512;index=511;lpc=800;
 repeat(200)@(negedge clk);
 if(dut.midi_rx_bcd!==20'h65535 || dut.midi_event_bcd!==20'h12345 || dut.midi_error_bcd!==20'h00002)$fatal(1,"MIDI count conversion");
 if(dut.time_bcd!==20'h65535 || dut.duration_bcd!==20'h04820 || dut.count_bcd!==20'h00512 || dut.index_bcd!==20'h00511 || dut.loop_bcd!==20'h00800)$fatal(1,"BCD conversion");
 tm=0;duration=1;count=0;index=1;lpc=0;repeat(200)@(negedge clk);
 if(dut.time_bcd!==0 || dut.duration_bcd!==1 || dut.count_bcd!==0 || dut.index_bcd!==1 || dut.loop_bcd!==0)$fatal(1,"BCD update");
 pixel(464,180,24'h67d8b8);pixel(528,180,24'hb8ddd1);pixel(592,180,24'hebb376);
 pixel(480,180,24'he88874);pixel(496,180,24'hebf0e7);pixel(552,120,24'he9c38a);
 drums=1;pixel(480,180,24'he88874);pixel(464,180,24'h67d8b8);
 // Geometry is identical on all pages and independent of the legacy focus.
 page=0;cursor=1;pixel(681,377,24'h79d7bd);pixel(688,377,24'h244d50);
 pixel(688,413,24'h10212b);pixel(30,15,24'h101f2e);
 page=1;cursor=3;pixel(681,449,24'h79d7bd);pixel(976,386,24'h79d7bd);
 page=2;cursor=4;pixel(681,485,24'h79d7bd);pixel(976,422,24'h79d7bd);
 effects=3;pixel(976,530,24'h10212b);effects=7;pixel(976,530,24'h79d7bd);effects=1;
 page=3;cursor=5;confirm=1;pixel(681,521,24'heab17e);pixel(688,521,24'h513d2f);
 pixel(80,523,24'h79d7bd);pixel(200,523,24'h263c48);
 confirm=0;pixel(681,521,24'h79d7bd);
 page=4;cursor=4;pixel(681,485,24'h79d7bd);pixel(688,521,24'h0c1925);
 page=5;cursor=2;pixel(681,413,24'h79d7bd);pixel(688,413,24'h244d50);
 // No 2x glyph may bleed into the four-pixel gutter between menu rows.
 page=1;cursor=1;
 for(menu_row=0;menu_row<5;menu_row=menu_row+1)
  for(menu_y=366+menu_row*36;menu_y<370+menu_row*36;menu_y=menu_y+1)
   for(menu_x=704;menu_x<972;menu_x=menu_x+1)pixel(menu_x,menu_y,24'h10212b);
 $display("PASS BCD extremes, chord onset/hold colors, preview, actual-key borders, page-independent key feedback, six-page navigation, preset marks and destructive-action confirmation");$finish;
 end
endmodule
