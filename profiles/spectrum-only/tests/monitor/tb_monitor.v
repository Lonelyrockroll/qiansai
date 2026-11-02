`timescale 1ns/1ps
module tb_monitor;
 reg clk=0,pclk=0,rst=1,tick=0,blank=0;reg signed [15:0] pcm=0;
 reg [1:0] mode=0;reg [10:0] x=0,y=0;
 wire [319:0] levels;wire [5:0] peaks;wire overrun;wire [23:0] rgb;
 always #10 clk=!clk;always #10.204 pclk=!pclk;
 audio_monitor dut(.sys_clk(clk),.sys_rst(rst),.sample_tick(tick),.pcm(pcm),.enable(1'b1),.test_state(mode),
  .missing_voice(5'd9),.onset_us(16'd627),.onset_valid(1'b1),.pixel_clk(pclk),.pixel_rst(rst),.frame_start(blank),.x(x),.y(y),
  .peak_count(peaks),.spectrum_levels(levels),.analysis_overrun(overrun),.rgb(rgb));
 reg [15:0] wave[0:12287];integer gap,kind,n,output_file,i;
 task frame;begin @(negedge pclk);blank=1;@(negedge pclk);blank=0;repeat(36)@(negedge pclk);end endtask
 task pixel(input integer px,input integer py,input [23:0] expected);begin
  @(negedge pclk);x=px;y=py;repeat(3)@(posedge pclk);#1;
  if(rgb!==expected)$fatal(1,"pixel %0d,%0d expected %h got %h",px,py,expected,rgb);
 end endtask
 task render(input integer c);integer f,px;begin
  case(c)1:f=$fopen("tone.ppm","wb");3:f=$fopen("test32.ppm","wb");4:f=$fopen("test31.ppm","wb");default:f=$fopen("loop-header.ppm","wb");endcase
  if(c==6)$fwrite(f,"P6\n1024 112\n255\n");else $fwrite(f,"P6\n1024 600\n255\n");
  for(px=0;px<(c==6?114690:614402);px=px+1)begin @(negedge pclk);x=px%1024;y=px/1024;@(posedge pclk);#1;if(px>=2)$fwrite(f,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);end
  $fclose(f);x=0;y=0;
 end endtask
 task text_check(input integer x0,input integer row,input integer len,input [255:0] phrase);integer j;reg [7:0] ch;begin
  for(j=0;j<len;j=j+1)begin x=x0+16*j;y=row*16;#1;ch=phrase>>((len-j-1)*8);if(dut.renderer.character!==ch)$fatal(1,"label mismatch");end
 end endtask
 initial begin
  $readmemh("stimulus.hex",wave);output_file=$fopen("frames.txt","w");gap=$test$plusargs("NATIVE")?1024:160;
  repeat(5)@(negedge clk);rst=0;
  if($test$plusargs("STATUS_ONLY"))begin
   mode=0;frame();text_check(32,4,8,"LIVE PCM");text_check(592,4,8,"LAST I2S");pixel(288,491,24'h101b27);
   mode=1;frame();text_check(32,4,16,"TEST / 32 VOICES");pixel(288,491,24'hfffaf0);
   mode=2;frame();text_check(32,4,16,"TEST / 31 VOICES");pixel(288,491,24'hf57d68);
   mode=3;frame();text_check(32,4,22,"LIVE / STOP LOOP FIRST");text_check(592,4,8,"LAST I2S");pixel(288,491,24'h101b27);
   if($test$plusargs("RENDER"))render(6);
   $display("PASS Lite header and actual RGB marker pixels in 4 states");$finish;
  end
  for(kind=0;kind<6;kind=kind+1)begin
   mode=kind==3?1:(kind==4?2:0);
   for(n=0;n<2048;n=n+1)begin @(negedge clk);pcm=wave[kind*2048+n];tick=1;@(negedge clk);tick=0;repeat(gap-2)@(negedge clk);end
   frame();if(overrun || dut.snap[319:0]!==levels || dut.snap[332:331]!==mode)$fatal(1,"window or CDC");
   $fdisplay(output_file,"%0d %0d %080h",kind,peaks,levels);
   if(mode==0)begin text_check(592,4,8,"LAST I2S");pixel(288,491,24'h101b27);end
   if(mode==1)begin pixel(288,491,24'hfffaf0);end
   if(mode==2)begin pixel(288,491,24'hf57d68);end
   for(i=0;i<64;i=i+1)pixel(i*16+5,478,levels[i*5+:5]!=0?24'h77cee0:24'h0e202a);
   if($test$plusargs("RENDER") && (kind==1 || kind==3 || kind==4))render(kind);
  end
  mode=3;frame();text_check(32,4,22,"LIVE / STOP LOOP FIRST");text_check(592,4,8,"LAST I2S");pixel(288,491,24'h101b27);
  $fclose(output_file);$display("PASS Lite 64-bin measurements, pixel bars, missing marker, loop guard and LAST I2S label; gap %0d",gap);$finish;
 end
endmodule
