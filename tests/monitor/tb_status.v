`timescale 1ns/1ps
// Check the visible LIVE/Loop/test labels and point markers at actual RGB pins.
module tb_status;
 reg clk=0,rst=1;reg [10:0] x=0,y=0;reg [1:0] mode=0;
 wire [23:0] rgb;wire [7:0] offset;
 always #10.204 clk=!clk;
 monitor_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.mode(mode),
   .missing(5'd9),.peaks(6'd32),.onset_us(16'd627),.onset_valid(1'b1),
   .frame_valid(1'b1),.pixel_word(16'd0),.read_offset(offset),.rgb(rgb));
 task word(input integer start_x,input integer start_y,input integer length,input [255:0] wanted);
  integer i;reg [7:0] expected;
  begin
   for(i=0;i<length;i=i+1)begin
    x=start_x+16*i;y=start_y;#1;expected=wanted>>((length-i-1)*8);
    if(dut.character!==expected)$fatal(1,"wrong letter mode %d x=%d y=%d: received %h wanted %h",mode,x,y,dut.character,expected);
   end
  end
 endtask
 task marker(input integer x0,input [23:0] expected);
  begin @(negedge clk);x=x0;y=508;repeat(3)@(posedge clk);#1;
   if(rgb!==expected)$fatal(1,"marker mode=%d x=%d actual=%h expected=%h",mode,x0,rgb,expected);
  end
 endtask
 integer f,i;
 initial begin
  repeat(5)@(negedge clk);rst=0;repeat(32)@(negedge clk);
  mode=0;word(560,10,8,"LIVE PCM");word(560,38,9,"LAST I2S ");marker(176,24'h162632);
  mode=1;word(560,10,16,"TEST / 32 VOICES");word(560,38,5,"PEAKS");marker(176,24'hfffaf0);
  mode=2;word(560,10,16,"TEST / 31 VOICES");word(560,38,5,"PEAKS");marker(176,24'hf57d68);
  mode=3;word(560,10,22,"LIVE / STOP LOOP FIRST");word(560,38,9,"LAST I2S ");word(350,573,10,"TURN: EXIT");
  marker(32,24'h162632);marker(176,24'h162632);
  f=$fopen("loop-header.ppm","wb");if(f==0)$fatal(1,"open header preview");
  $fwrite(f,"P6\n1024 66\n255\n");
  for(i=0;i<67586;i=i+1)begin
    @(negedge clk);x=i%1024;y=i/1024;@(posedge clk);#1;
    if(i>=2)$fwrite(f,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
  end
  $fclose(f);$display("PASS LIVE LAST I2S, loop warning, 32/31 labels, real RGB target and missing markers");$finish;
 end
endmodule
