`timescale 1ns/1ps
module tb_banks;
 reg clk=0,pclk=0,srst=1,prst=1,tick=0,enable=1,blank=0;
 reg signed [15:0] pcm=0;reg [1:0] mode=1;
 wire [23:0] rgb;
 always #10 clk=!clk;
 always #10.204 pclk=!pclk;
 audio_monitor dut(.sys_clk(clk),.sys_rst(srst),.sample_tick(tick),.pcm(pcm),.enable(enable),
  .test_state(mode),.missing_voice(5'd7),.onset_us(16'd55),.onset_valid(1'b1),
  .pixel_clk(pclk),.pixel_rst(prst),.frame_start(blank),.x(11'd704),.y(11'd286),.rgb(rgb));
 integer writes=0,j;
 reg [15:0] saved[0:143];
 always @(posedge clk)if(dut.writer!=0 && !dut.analysis_reset)begin
  writes=writes+1;
  if(dut.frame_valid && dut.write_bank==dut.display_bank)$fatal(1,"writer touched visible bank");
 end
 task sample_window(input integer amplitude);
  integer n;begin
   for(n=0;n<1024;n=n+1)begin
    @(negedge clk);pcm=n[5]?amplitude:-amplitude;tick=1;
    @(negedge clk);tick=0;repeat(158)@(negedge clk);
   end
   repeat(170)@(negedge clk);
  end
 endtask
 task video_boundary;
  begin
   repeat(5)@(negedge pclk);blank=1;@(negedge pclk);blank=0;repeat(5)@(negedge pclk);
  end
 endtask
 initial begin
  repeat(6)@(negedge clk);srst=0;prst=0;
  video_boundary();
  if(dut.frame_valid)$fatal(1,"startup showed uninitialized bank");
  sample_window(1200);
  if(writes!=144 || dut.published_bank!=1 || dut.frame_valid)$fatal(1,"first bank");
  for(j=0;j<144;j=j+1)saved[j]=dut.display_ram[256+j];
  sample_window(1900);sample_window(3000);
  if(writes!=144 || dut.published_bank!=1)$fatal(1,"unacknowledged frame overwritten");
  for(j=0;j<144;j=j+1)if(saved[j]!==dut.display_ram[256+j])$fatal(1,"unacknowledged data changed");
  enable=0;repeat(10)@(negedge clk);video_boundary();
  if(!dut.frame_valid || dut.display_bank!=1 || dut.metadata_pixel[12:11]!=1)$fatal(1,"published frame lost on disable");
  enable=1;mode=2;
  fork
   sample_window(2000);
   begin wait(dut.writer==2);@(negedge pclk);prst=1;repeat(5)@(negedge pclk);prst=0;end
  join
  if(writes!=288 || dut.published_bank!=0)$fatal(1,"second bank");
  video_boundary();
  if(dut.frame_valid)$fatal(1,"reset consumer falsely claimed a new bank");
  sample_window(900);video_boundary();
  if(writes!=432 || !dut.frame_valid || dut.display_bank!=1 || dut.metadata_pixel[12:11]!=2)$fatal(1,"recovery after independent pixel reset");
  $display("PASS bank exchange: 432 writes, stall without vblank, disable, pixel reset during writer, valid frame recovery");$finish;
 end
endmodule
