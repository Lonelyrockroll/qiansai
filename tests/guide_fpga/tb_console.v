`timescale 1ns/1ps
module tb_console;
 localparam BIT_CLOCKS=434;
 reg clk=0,rst=1,rx=1;
 always #10 clk=~clk;
 reg [9:0] divider=0;
 always @(posedge clk)if(rst)divider<=0;else divider<=divider+1'b1;
 wire tick=divider==1023;
 reg signed [15:0] pcm=0;
 always @(posedge clk)if(rst)pcm<=0;else if(tick)pcm<=pcm+16'sd39;
 wire tx,locked,request;wire [15:0] period,commands,dropped;
 wire [7:0] command;wire guide_valid,guide_playing,guide_loading,guide_demo;
 wire [9:0] guide_count,guide_index;wire [15:0] guide_time,guide_duration;
 wire [31:0] current;
 integer text_requests=0;
 always @(posedge clk)if(request)text_requests=text_requests+1;
 bt_console dut(.clk(clk),.rst(rst),.bt_rx(rx),.bt_tx(tx),.audio_tick(tick),.pcm(pcm),
  .locked(locked),.period(period),.commands(commands),.dropped(dropped),.request(request),.command(command),
  .accept(1'b1),.settled(1'b1),.volume(7'd7),.timbre(3'd4),.fx(3'd0),.lamps(8'd0),
  .guide_ui_valid(1'b0),.guide_ui_action(4'd0),
  .score_video_visible(1'b0),.capture_busy(1'b0),.capture_ready(1'b0),
  .score_ui_valid(1'b0),.score_ui_action(2'd0),
  .guide_valid(guide_valid),.guide_playing(guide_playing),.guide_loading(guide_loading),.guide_demo(guide_demo),
  .guide_count(guide_count),.guide_index(guide_index),.guide_time_cs(guide_time),.guide_duration_cs(guide_duration),
  .guide_current(current));
 reg [7:0] wirebytes[0:671],hostpacket[0:27],output_bytes[0:8191];
 integer output_count=0,used=0,serial_file;
 integer bitno,j,p,expected_seq,clock_count=0,frames=0,data_frames=0,guide_acks=0,finish_frames=0;
 reg [7:0] decoded;
 reg [8*240-1:0] output_path;
 always @(posedge clk)clock_count=clock_count+1;
 // Independent 8N1 receiver samples the physical TX wire at bit centers.
 initial forever begin
  @(negedge tx);
  if(!rst)begin
   repeat(BIT_CLOCKS+BIT_CLOCKS/2)@(posedge clk);
   decoded=0;
   for(bitno=0;bitno<8;bitno=bitno+1)begin
    decoded[bitno]=tx;
    repeat(BIT_CLOCKS)@(posedge clk);
   end
   if(tx!==1'b1)$fatal(1,"bad UART stop bit");
   if(output_count>=8192)$fatal(1,"wire buffer overflow");
   output_bytes[output_count]=decoded;output_count=output_count+1;
   $fdisplay(serial_file,"%02x",decoded);
  end
 end
 function [15:0] crc16(input [15:0] crc,input [7:0] data);
  reg [15:0] v;integer n;begin v=crc^{data,8'd0};for(n=0;n<8;n=n+1)v=(v<<1)^(v[15]?16'h1021:0);crc16=v;end
 endfunction
 task send_byte(input [7:0] b);
  integer n;
  begin
   @(negedge clk);rx=0;repeat(BIT_CLOCKS)@(negedge clk);
   for(n=0;n<8;n=n+1)begin rx=b[n];repeat(BIT_CLOCKS)@(negedge clk);end
   rx=1;repeat(BIT_CLOCKS)@(negedge clk);
  end
 endtask
 task ext(input [7:0] b);
  begin send_byte("~");send_byte(b);end
 endtask
 task require_bytes(input integer count);
  integer waits;
  begin
   waits=0;
   while(output_count<used+count && waits<1500000)begin @(negedge clk);waits=waits+1;end
   if(output_count<used+count)$fatal(1,"serial reply timeout, have %d used %d need %d",output_count,used,count);
  end
 endtask
 task guide_ack(input [7:0] seq0,input [7:0] op0);
  reg [15:0] sum;integer n;
  begin
   require_bytes(24);
   if({output_bytes[used+0],output_bytes[used+1],output_bytes[used+2],output_bytes[used+3]}!==32'h5447414b ||
      output_bytes[used+4]!=1 || output_bytes[used+5]!=seq0 || output_bytes[used+6]!=op0 || output_bytes[used+7]!=0)
     $fatal(1,"unexpected TGAK at %d seq %d op %d status %d",used,seq0,op0,output_bytes[used+7]);
   sum=16'hffff;for(n=4;n<22;n=n+1)sum=crc16(sum,output_bytes[used+n]);
   if(sum!={output_bytes[used+23],output_bytes[used+22]})$fatal(1,"TGAK CRC from physical UART");
   used=used+24;guide_acks=guide_acks+1;frames=frames+1;
  end
 endtask
 task trec(input integer wanted_kind);
  reg [15:0] sum;integer n,length0,kind;
  begin
   require_bytes(6);
   if({output_bytes[used+0],output_bytes[used+1],output_bytes[used+2],output_bytes[used+3]}!==32'h54524543 ||
      output_bytes[used+4]!=1)$fatal(1,"unexpected TREC header at %d",used);
   kind=output_bytes[used+5];length0=kind==1?80:16;
   require_bytes(length0);
   if(wanted_kind!=0 && kind!=wanted_kind)$fatal(1,"TREC kind %d expected %d",kind,wanted_kind);
   sum=16'hffff;for(n=4;n<length0-2;n=n+1)sum=crc16(sum,output_bytes[used+n]);
   if(sum!={output_bytes[used+length0-1],output_bytes[used+length0-2]})$fatal(1,"TREC CRC from physical UART");
   if(kind==1)begin
    if(output_bytes[used+10]!=129)$fatal(1,"ADPCM block length");
    data_frames=data_frames+1;
   end
   if(kind==2)begin
    if(output_bytes[used+13]!=0)$fatal(1,"recording stopped with fault %d",output_bytes[used+13]);
    finish_frames=finish_frames+1;
   end
   used=used+length0;frames=frames+1;
  end
 endtask
 task hostile_frame;
  reg [15:0] sum;integer n;
  begin
   for(n=0;n<28;n=n+1)hostpacket[n]=0;
   hostpacket[0]=8'ha5;hostpacket[1]=8'h47;hostpacket[2]=1;hostpacket[3]=91;hostpacket[4]=2;hostpacket[5]=19;
   hostpacket[6]="~";hostpacket[7]="S";hostpacket[8]="M";hostpacket[9]="T";hostpacket[10]="U";
   hostpacket[11]=8'ha5;hostpacket[12]="~";hostpacket[13]="R";hostpacket[14]="+";hostpacket[15]="-";
   hostpacket[16]="~";hostpacket[17]="I";hostpacket[18]="~";hostpacket[19]="K";
   hostpacket[20]=13;hostpacket[21]=10;hostpacket[22]="F";hostpacket[23]="L";hostpacket[24]="?";
   sum=16'hffff;for(n=2;n<26;n=n+1)sum=crc16(sum,hostpacket[n]);
   hostpacket[26]=sum[7:0];hostpacket[27]=sum[15:8];
   for(n=0;n<28;n=n+1)send_byte(hostpacket[n]);
  end
 endtask
 integer before_commands,original_count,before_requests,before_acks,before_finishes;
 initial begin
  $readmemh("demo-upload.hex",wirebytes);
  if(!$value$plusargs("OUT=%s",output_path))output_path="console-wire.hex";
  serial_file=$fopen(output_path,"w");if(!serial_file)$fatal;
  repeat(20)@(negedge clk);rst=0;
  repeat(100)@(negedge clk);
  send_byte("U");send_byte("U");send_byte("U");send_byte("U");
  if(!locked || period!=BIT_CLOCKS)$fatal(1,"baud training %d",period);
  ext("I");trec(3);ext("G");guide_ack(0,0);
  if(!guide_demo || !guide_valid || guide_playing)$fatal(1,"initial capability state");
  for(p=0;p<24;p=p+1)begin
   for(j=0;j<28;j=j+1)send_byte(wirebytes[p*28+j]);
   guide_ack(wirebytes[p*28+3],wirebytes[p*28+4]);
  end
  if(guide_demo || !guide_playing || guide_count!=84 || guide_duration!=2400 || current!==32'h4000)
     $fatal(1,"serial upload playback");
  before_commands=commands;before_requests=text_requests;before_acks=guide_acks;before_finishes=finish_frames;
  ext("R");trec(1);ext("K");
  if(!dut.recorder.active)$fatal(1,"recording not running");
  hostile_frame();
  if(commands!=before_commands || text_requests!=before_requests || guide_count!=84 || !guide_playing)
    $fatal(1,"binary body leaked to text or guide while recording");
  trec(1);ext("K");trec(1);
  if(!dut.recorder.active || finish_frames!=before_finishes || guide_acks!=before_acks)$fatal(1,"embedded ~S/~I stopped recording or guide replied");
  ext("S");
  while(finish_frames==before_finishes)trec(0);
  if(dut.recorder.active || commands!=before_commands || text_requests!=before_requests)$fatal(1,"stop/commands");
  ext("G");guide_ack(0,0);
  if(guide_count!=84 || !guide_playing || guide_demo)$fatal(1,"guide changed during audio");
  if($test$plusargs("TIMEOUT"))begin
   send_byte("?");send_byte(8'ha5);send_byte(8'h47);send_byte("~");send_byte("M");
   repeat(12501000)@(negedge clk);
   if(dut.discard_left!=0)$fatal(1,"binary discard timeout");
   require_bytes(24);if(output_bytes[used]!="O" || output_bytes[used+1]!="K")$fatal;
   used=used+24;
   if(commands!=before_commands+1)$fatal(1,"partial frame leaked commands");
   ext("G");guide_ack(0,0);
  end
  repeat(6000)@(negedge clk);
  if(output_count!=used)$fatal(1,"unexpected trailing response %d",output_count-used);
  if(dropped!=0)$fatal(1,"framing or console drop counter %d",dropped);
  $fclose(serial_file);
  $display("PASS physical 8N1 UART at divisor %d: %d TGAK, %d TREC data, %d recording end; %d clocks",period,guide_acks,data_frames,finish_frames,clock_count);
  $finish;
 end
 initial begin #600000000;$fatal(1,"overall timeout");end
endmodule
