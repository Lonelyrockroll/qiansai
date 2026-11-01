`timescale 1ns/1ps
module tb_java_upload;
 reg clk=0,rst=1,rx_valid=0,tick=0;
 reg [7:0] rx_data=0;
 always #5 clk=~clk;
 wire tx_valid;wire [7:0] tx_data;
 wire playing,demo;wire [9:0] count,index;wire [15:0] tm,duration;
 wire [31:0] current,onset;
 guide_transport dut(.clk(clk),.rst(rst),.audio_tick(tick),.probe(1'b0),
   .rx_valid(rx_valid),.rx_data(rx_data),.tx_ready(1'b1),.tx_valid(tx_valid),.tx_data(tx_data),
   .recorder_active(1'b0),.ui_valid(1'b0),.ui_action(4'd0),
   .guide_playing(playing),.guide_demo(demo),.guide_count(count),.guide_index(index),
   .guide_time_cs(tm),.guide_duration_cs(duration),.guide_current(current),.guide_onset(onset));
 reg [7:0] bytes[0:671],ack[0:23];
 reg [31:0] expected[0:83];
 integer received=0,packet,offset,k,limit,ack_file;
 reg [8*240-1:0] ack_path;
 always @(posedge clk)if(tx_valid)begin
   if(received>=24)$fatal(1,"ACK overflow");
   ack[received]=tx_data;received=received+1;$fdisplay(ack_file,"%02x",tx_data);
 end
 function [15:0] crc16(input [15:0] v,input [7:0] data);
  reg [15:0] q;integer i;begin q=v^{data,8'b0};for(i=0;i<8;i=i+1)q=(q<<1)^(q[15]?16'h1021:0);crc16=q;end
 endfunction
 reg [15:0] crc;
 initial begin
  $readmemh("demo-upload.hex",bytes);$readmemh("demo-events.hex",expected);
  if(!$value$plusargs("ACK=%s",ack_path))ack_path="demo-acks.hex";
  ack_file=$fopen(ack_path,"w");if(!ack_file)$fatal(1,"cannot open ACK output");
  repeat(5)@(negedge clk);rst=0;
  for(packet=0;packet<24;packet=packet+1)begin
   received=0;
   for(offset=0;offset<28;offset=offset+1)begin
    @(negedge clk);rx_valid=1;rx_data=bytes[packet*28+offset];
    @(negedge clk);rx_valid=0;
   end
   limit=0;
   while(received<24 && limit<5000)begin @(negedge clk);limit=limit+1;end
   if(received!=24 || ack[5]!=packet+1 || ack[7]!=0)$fatal(1,"Java packet %d failed status %d",packet,ack[7]);
   crc=16'hffff;for(k=4;k<22;k=k+1)crc=crc16(crc,ack[k]);
   if(crc!={ack[23],ack[22]})$fatal(1,"bad returned CRC");
   if(packet==22)begin
    if(count!=84 || duration!=2400 || demo || playing)$fatal(1,"commit state");
    for(k=0;k<84;k=k+1)if(dut.player.event_memory[512+k]!==expected[k])$fatal(1,"Java event %d storage mismatch",k);
   end
   repeat(5)@(negedge clk);
  end
  if(!playing || current!==32'h4000 || onset!==32'h4000 || index!=1)$fatal(1,"first note");
  tick=1;wait(tm==45);tick=0;repeat(50)@(negedge clk);
  if(current!=0 || index!=2)$fatal(1,"first note release");
  tick=1;wait(tm==50);tick=0;repeat(50)@(negedge clk);
  if(current!==32'h4000 || index!=3)$fatal(1,"same-key retrigger");
  $display("PASS Android Java's 24 exact binary frames uploaded 84 event words and drove on/off/retrigger timing");
  $fclose(ack_file);
  $finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
