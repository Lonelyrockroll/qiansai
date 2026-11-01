`timescale 1ns/1ps
// Complete RGB output from the real renderer, including its three-stage latency.
// Usage: vvp render.vvp +DRUMS=0 +OUTPUT=/path/to/guide.ppm
module guide_ui_render;
reg clk=0,rst=1;always #5 clk=~clk;
reg [10:0] x=0,y=0;reg drums=0;wire [23:0] rgb;
panel_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
 .bend_position(4'd4),.vibrato_depth(3'd2),.focus(4'd9),.fx(3'd1),.timbre(3'd4),.volume(7'd7),.voices(6'd3),.mode(2'd2),
 .calibrated(1'b1),.fault(1'b0),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
 .loop_actual_cs(10'd600),.loop_position_cs(10'd123),.loop_layers(3'd2),.loop_notice(3'd0),.loop_duration(2'd2),
 .loop_playing(1'b1),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd20),.drum_mode(drums),
 .notice(4'd0),.pressed(drums?32'h00000211:32'h00054000),.peak(8'd100),
 .guide_valid(1'b1),.guide_playing(1'b1),.guide_loading(1'b0),.guide_demo(1'b0),
 .guide_time_cs(16'd1234),.guide_duration_cs(16'd4820),.guide_count(10'd126),.guide_index(10'd34),.guide_speed(2'd2),
 .guide_target(32'h00054000),.guide_onset(32'h00044000),.guide_next(32'h001a0000),.guide_colors(64'h0000001000000000),
 .actual_keys(32'h0004c000),.rgb(rgb));
integer i,file,drum_argument;
string output_file;
initial begin
 if(!$value$plusargs("OUTPUT=%s",output_file))$fatal(1,"Missing +OUTPUT=filename");
 if(!$value$plusargs("DRUMS=%d",drum_argument))drum_argument=0;
 drums=drum_argument!=0;
 file=$fopen(output_file,"wb");if(!file)$fatal(1,"Cannot open output frame");
 $fwrite(file,"P6\n1024 600\n255\n");repeat(4)@(negedge clk);rst=0;
 for(i=0;i<1024*600+2;i=i+1)begin
  x=i%1024;y=i/1024;@(negedge clk);
  if(i>=2)$fwrite(file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
 end
 $fclose(file);$finish;
end
endmodule
