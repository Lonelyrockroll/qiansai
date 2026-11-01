// Export the actual pixel pipeline while holding a C-major chord. No framebuffer on FPGA.
`timescale 1ns/1ps
module tb_panel_preview;
 reg clk=0,rst=1;always #5 clk=!clk;
 reg [10:0] x=0,y=0;wire [23:0] rgb;
 panel_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
  .focus(4'd0),.fx(3'd0),.timbre(3'd4),.volume(7'd11),.voices(6'd3),.mode(2'd2),
  .calibrated(1'b1),.fault(1'b0),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
  .loop_actual_cs(10'd0),.loop_position_cs(10'd0),.loop_layers(3'd0),.loop_notice(3'd0),.loop_duration(2'd2),
  .loop_playing(1'b0),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd0),
  .drum_mode(1'b0),.notice(4'd0),.pressed(32'h00054000),.peak(8'd96),.rgb(rgb));
 integer i,file;
 initial begin
  file=$fopen("sim/white_keys.ppm","wb");if(file==0)$fatal(1,"preview file");
  $fwrite(file,"P6\n1024 600\n255\n");
  repeat(4)@(negedge clk);rst=0;
  for(i=0;i<1024*600+2;i=i+1)begin
   x=i%1024;y=i/1024;@(negedge clk);
   if(i>=2)$fwrite(file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
  end
  $fclose(file);$finish;
 end
endmodule
