`timescale 1ns/1ps
module tb_monitor;
 reg clk=0,pclk=0,rst=1,tick=0,frame_start=0;
 reg signed [15:0] pcm=0;
 reg [1:0] mode=0;reg [4:0] missing=9;
 reg [10:0] x=0,y=0;
 wire [319:0] levels;wire [5:0] peaks;wire overrun;wire [23:0] rgb;
 always #10 clk=!clk;
 always #10.204 pclk=!pclk;
 audio_monitor dut(.sys_clk(clk),.sys_rst(rst),.sample_tick(tick),.pcm(pcm),.enable(1'b1),
  .test_state(mode),.missing_voice(missing),.onset_us(16'd627),.onset_valid(1'b1),
  .pixel_clk(pclk),.pixel_rst(rst),.frame_start(frame_start),.x(x),.y(y),
  .peak_count(peaks),.spectrum_levels(levels),.analysis_overrun(overrun),.rgb(rgb));
 reg [15:0] stimulus[0:12287];
 integer j,n,kind,report,gap;
 reg [383:0] wave_seen;reg [255:0] phase_seen;reg [319:0] bars_seen;
 reg [15:0] word_seen;
 always @(posedge clk)if(!rst && dut.writer!=0 && dut.frame_valid && dut.write_bank==dut.display_bank)
     $fatal(1,"writer touched currently displayed bank");
 task frame;
  begin
   @(negedge pclk);frame_start=1;@(negedge pclk);frame_start=0;repeat(32)@(negedge pclk);
  end
 endtask
 task render(input integer testcase);
  integer f,px;begin
   case(testcase)
    1:f=$fopen("tone.ppm","wb");
    3:f=$fopen("test32.ppm","wb");
    default:f=$fopen("test31.ppm","wb");
   endcase
   if(f==0)$fatal(1,"open preview");
   $fwrite(f,"P6\n1024 600\n255\n");
   for(px=0;px<614402;px=px+1)begin
    @(negedge pclk);x=px%1024;y=px/1024;@(posedge pclk);#1;
    if(px>=2)$fwrite(f,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
   end
   $fclose(f);x=0;y=0;
  end endtask
 initial begin
  $readmemh("stimulus.hex",stimulus);
  report=$fopen("frames.txt","w");gap=$test$plusargs("NATIVE")?1024:160;
  repeat(5)@(negedge clk);rst=0;
  for(kind=0;kind<6;kind=kind+1)begin
   mode=kind==3?1:(kind==4?2:0);
   for(n=0;n<2048;n=n+1)begin
    @(negedge clk);pcm=stimulus[kind*2048+n];tick=1;@(negedge clk);tick=0;
    repeat(gap-2)@(negedge clk);
    if(n==1023)begin
     repeat(170)@(negedge clk);
     if(kind==3 && dut.metadata_pixel[12:11]!==0)$fatal(1,"mode changed outside frame boundary");
     frame();
    end
   end
   if(overrun)$fatal(1,"overrun at gap %0d",gap);
   repeat(170)@(negedge clk);
   frame();
   if(!dut.frame_valid || dut.metadata_pixel[12:11]!==mode || dut.metadata_pixel[5:0]!==peaks)
     $fatal(1,"CDC frame metadata mismatch");
   for(j=0;j<64;j=j+1)begin
    word_seen=dut.display_ram[dut.display_bank*256+j];wave_seen[j*6+:6]=word_seen[5:0];
    if(word_seen[11:6] !== (j==0?wave_seen[5:0]:wave_seen[(j-1)*6+:6]))$fatal(1,"previous sample mismatch");
    bars_seen[j*5+:5]=dut.display_ram[dut.display_bank*256+64+j][4:0];
   end
   if(bars_seen!==levels)$fatal(1,"CDC spectrum bank mismatch");
   for(j=0;j<16;j=j+1)phase_seen[j*16+:16]=dut.display_ram[dut.display_bank*256+128+j];
   $fdisplay(report,"%0d %0d %080h %096h %064h",kind,peaks,bars_seen,wave_seen,phase_seen);
   if($test$plusargs("RENDER") && (kind==1 || kind==3 || kind==4))render(kind);
  end
  $fclose(report);$display("PASS six cases, sample interval %0d clocks; coherent vertical-blank mailbox",gap);$finish;
 end
endmodule
