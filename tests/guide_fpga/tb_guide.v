`timescale 1ns/1ps
module tb_guide;
 reg clk=0,rst=1,tick=0,probe=0,rx_valid=0,recorder=0,ui_valid=0;
 reg [7:0] rx_data=0;reg [3:0] ui_action=0;
 always #5 clk=~clk;
 reg [7:0] throttle=0;
 always @(posedge clk)throttle<=throttle+1'b1;
 wire tx_ready=throttle[1:0]!=1;
 wire tx_valid;wire [7:0] tx_data;
 wire owned,receiving,valid,playing,loading,demo;
 wire [15:0] tm,duration;wire [9:0] count,index;wire [1:0] speed;
 wire [31:0] current,onset,next;wire [63:0] colors;
 guide_transport #(.CLK_HZ(1000),.RX_TIMEOUT_CYCLES(200),.UPLOAD_TIMEOUT_CYCLES(40000)) dut(
  .clk(clk),.rst(rst),.audio_tick(tick),.probe(probe),.rx_valid(rx_valid),.rx_data(rx_data),
  .tx_ready(tx_ready),.tx_valid(tx_valid),.tx_data(tx_data),.recorder_active(recorder),
  .ui_valid(ui_valid),.ui_action(ui_action),.owned(owned),.receiving(receiving),
  .guide_valid(valid),.guide_playing(playing),.guide_loading(loading),.guide_demo(demo),
  .guide_time_cs(tm),.guide_duration_cs(duration),.guide_count(count),.guide_index(index),
  .guide_speed(speed),.guide_current(current),.guide_onset(onset),.guide_next(next),.guide_colors(colors));
 reg [7:0] request[0:27],response[0:23];
 reg [31:0] events[0:511];
 integer got=0,seqnum=1,checks=0,clocks=0,reloads=0;
 reg atomic_watch=0;
 always @(posedge clk)begin
  clocks=clocks+1;
  if(tx_valid)begin
   if(got>=24)$fatal(1,"reply too long");
   response[got]=tx_data;got=got+1;
  end
  if(dut.player.reload)reloads=reloads+1;
  if(atomic_watch && current!=0 && current!==32'h00014000)$fatal(1,"torn chord %h",current);
 end
 function [15:0] crc16(input [15:0] crc,input [7:0] data);
  reg [15:0] v;integer j;begin v=crc^{data,8'd0};for(j=0;j<8;j=j+1)v=(v<<1)^(v[15]?16'h1021:0);crc16=v;end
 endfunction
 function [31:0] crc32(input [31:0] crc,input [7:0] data);
  reg [31:0] v;integer j;begin v=crc^{24'd0,data};for(j=0;j<8;j=j+1)v=(v>>1)^(v[0]?32'hedb88320:0);crc32=v;end
 endfunction
 function [31:0] ev(input [15:0] time0,input [4:0] key0,input on0,input [1:0] tr);
  begin ev={8'd0,tr,on0,key0,time0};end
 endfunction
 task packet(input [7:0] op,input [7:0] len,input [159:0] payload);
  integer j;reg [15:0] crc;
  begin
   request[0]=8'ha5;request[1]=8'h47;request[2]=1;request[3]=seqnum;request[4]=op;request[5]=len;
   for(j=0;j<20;j=j+1)request[6+j]=payload[j*8 +: 8];
   crc=16'hffff;for(j=2;j<26;j=j+1)crc=crc16(crc,request[j]);
   request[26]=crc[7:0];request[27]=crc[15:8];seqnum=(seqnum+1)&255;
  end
 endtask
 task byte_in(input [7:0] b);
  begin @(negedge clk);rx_data=b;rx_valid=1;@(negedge clk);rx_valid=0;end
 endtask
 task reply_check(input [7:0] status);
  integer timeout,j;reg [15:0] crc;
  begin
   timeout=0;
   while(got<24 && timeout<2000)begin @(negedge clk);timeout=timeout+1;end
   if(got!=24)$fatal(1,"reply timeout %d state %d",got,dut.state);
   if({response[3],response[2],response[1],response[0]}!==32'h4b414754 || response[4]!=1 ||
      response[5]!=request[3] || response[6]!=request[4] || response[7]!=status)
      $fatal(1,"reply header/status op %d expected %d got %d",request[4],status,response[7]);
   crc=16'hffff;for(j=4;j<22;j=j+1)crc=crc16(crc,response[j]);
   if({response[23],response[22]}!==crc)$fatal(1,"ACK CRC");
   repeat(6)@(negedge clk);checks=checks+1;
  end
 endtask
 task send_request(input [7:0] wanted);
  integer j;
  begin
   got=0;
   for(j=0;j<28;j=j+1)byte_in(request[j]);
   reply_check(wanted);
  end
 endtask
 task ctl(input [7:0] action0);
  begin packet(4,1,{152'd0,action0});send_request(0);repeat(80)@(negedge clk);end
 endtask
 task begin_upload(input integer n,input [15:0] length0,input corrupt);
  reg [31:0] crc;integer j,k;
  begin
   crc=32'hffffffff;
   for(j=0;j<n;j=j+1)for(k=0;k<4;k=k+1)crc=crc32(crc,events[j][k*8 +: 8]);
   crc=~crc;if(corrupt)crc=crc^1;
   packet(1,8,{96'd0,crc,length0,n[15:0]});send_request(0);
  end
 endtask
 task chunk(input integer offset,input integer n,input [7:0] want);
  reg [159:0] payload;integer j;
  begin
   payload=0;payload[15:0]=offset;payload[23:16]=n;
   for(j=0;j<n;j=j+1)payload[24+j*32 +:32]=events[offset+j];
   packet(2,3+4*n,payload);send_request(want);
  end
 endtask
 task commit(input [7:0] want);
  begin packet(3,0,0);send_request(want);repeat(80)@(negedge clk);end
 endtask
 task run_to(input integer target);
  integer limit;
  begin
   limit=0;tick=1;
   while(tm!=target && limit<100000)begin @(negedge clk);limit=limit+1;end
   tick=0;repeat(80)@(negedge clk);
   if(tm!=target)$fatal(1,"time did not reach %d, got %d playing %b",target,tm,playing);
  end
 endtask
 integer i,saved;reg [7:0] saved_ack[0:23];
 initial begin
  repeat(5)@(negedge clk);rst=0;repeat(40)@(negedge clk);
  if(!valid || !demo || playing || count!=56 || duration!=1600 || speed!=2)$fatal(1,"default demo");
  // Safe capability probe, same ACK format, no binary command bytes.
  request[3]=0;request[4]=0;got=0;probe=1;@(negedge clk);probe=0;reply_check(0);
  if(response[16][3:0]!=9)$fatal(1,"probe flags");
  packet(4,1,1);request[26]=request[26]^1;send_request(1);
  if(playing)$fatal(1,"bad CRC changed playback");
  events[0]=ev(0,14,1,0);events[1]=ev(0,16,1,1);
  events[2]=ev(3,14,0,0);events[3]=ev(4,18,1,2);
  events[4]=ev(6,16,0,1);events[5]=ev(7,18,0,2);
  begin_upload(6,10,0);
  if(!loading || !demo || count!=56)$fatal(1,"begin replaced old score");
  chunk(0,3,0);if(dut.received_count!=3)$fatal;
  for(i=0;i<24;i=i+1)saved_ack[i]=response[i];
  send_request(0);
  for(i=0;i<24;i=i+1)if(response[i]!==saved_ack[i])$fatal(1,"duplicate ACK changed");
  if(dut.received_count!=3)$fatal(1,"duplicate write advanced");
  chunk(4,2,5);chunk(3,3,0);commit(0);
  if(count!=6 || demo || loading || playing)$fatal(1,"commit");
  saved=reloads;send_request(0);if(reloads!=saved)$fatal(1,"duplicate commit reloaded");
  atomic_watch=1;ctl(4);
  if(!playing || current!==32'h00014000 || onset!==current || colors[33:32]!=1 || index!=2)$fatal(1,"initial chord %h",current);
  send_request(0);if(!playing)$fatal(1,"duplicate toggle toggled");
  atomic_watch=0;run_to(3);
  if(current!==32'h00010000 || onset!=0 || next!==32'h00040000)$fatal(1,"release/preview %h %h",current,next);
  ctl(5);
  if(playing || tm!=4 || current!==32'h00050000 || onset!==32'h00040000 || index!=4 || colors[37:36]!=2)
    $fatal(1,"next/held %d %h %h idx%d",tm,current,onset,index);
  if({response[13],response[12]}!=4 || {response[19],response[18]}!=4)$fatal(1,"step ACK precedes settled state");
  ctl(6);
  if(tm!=0 || current!==32'h00014000 || onset!==32'h00014000 || index!=2)$fatal(1,"previous");
  tick=1;repeat(1800)@(negedge clk);tick=0;if(tm!=0)$fatal(1,"pause moved clock");
  ctl(1);run_to(6);if(current!==32'h00040000)$fatal(1,"second release");
  run_to(7);if(current!=0)$fatal(1,"end note off");
  run_to(0);if(playing || current!=0 || index!=0)$fatal(1,"finish did not reset");
  events[0]=ev(0,3,1,3);events[1]=ev(25,3,0,3);
  begin_upload(2,30,1);chunk(0,2,0);commit(1);
  if(count!=6 || demo || !valid || loading)$fatal(1,"bad data replaced committed bank");
  begin_upload(2,30,0);chunk(0,2,0);commit(0);
  ctl(1);run_to(16);
  if(current!==8 || onset!=0 || colors[7:6]!=3)$fatal(1,"held note/150ms accent");
  ctl(2);tick=1;repeat(1100)@(negedge clk);tick=0;if(tm!=16 || current!=8)$fatal(1,"pause changed held notes");
  ctl(5);if(tm!=16 || current!=8)$fatal(1,"next after final onset");
  ctl(1);begin_upload(2,30,1);chunk(0,2,0);commit(1);
  if(!playing || current!=8 || tm!=16 || count!=2)$fatal(1,"failed upload interrupted old playback");
  begin_upload(2,30,0);chunk(0,2,0);commit(0);
  if(playing || current!=0 || tm!=0 || count!=2)$fatal(1,"successful bank swap was not atomic");
  ctl(1);run_to(16);
  ctl(1);run_to(25);if(current!=0)$fatal(1,"held note release");run_to(0);
  // Same physical pitch in two tracks must survive one track's release.
  events[0]=ev(0,14,1,0);events[1]=ev(0,14,1,1);events[2]=ev(4,14,0,0);events[3]=ev(8,14,0,1);
  begin_upload(4,10,0);chunk(0,4,0);commit(0);ctl(1);run_to(4);
  if(current!==32'h4000 || colors[29:28]!=1)$fatal(1,"overlapping track release");
  ctl(0);
  recorder=1;packet(1,8,{96'd0,32'd0,16'd10,16'd1});send_request(4);
  if(loading || count!=4)$fatal(1,"record/upload exclusion");
  // Local guide commands remain usable while phone records.
  ui_action=4;ui_valid=1;@(negedge clk);ui_valid=0;repeat(40)@(negedge clk);if(!playing)$fatal;
  recorder=0;ctl(0);
  // Invalid ordering aborts the staging bank without damaging the committed score.
  events[0]=ev(9,1,1,0);events[1]=ev(8,1,0,0);
  begin_upload(2,10,0);chunk(0,2,3);commit(5);
  if(count!=4 || !valid)$fatal;
  events[0]=ev(0,1,1,0)|32'h80000000;
  begin_upload(1,10,0);chunk(0,1,3);if(count!=4)$fatal;
  // Framing timeout consumes the binary prefix and recovers on the next request.
  byte_in(8'ha5);byte_in(8'h47);byte_in(1);if(!owned)$fatal;
  repeat(210)@(negedge clk);if(owned)$fatal(1,"RX timeout");
  packet(0,0,0);send_request(0);
  // Full bank, final address511, streamed CRC and 10-bit count all tested.
  for(i=0;i<512;i=i+1)events[i]=ev(i*2,i[4:0],!i[0],i[6:5]);
  begin_upload(512,1025,0);
  for(i=0;i<512;i=i+4)chunk(i,4,0);
  if(dut.received_count!=512)$fatal(1,"full count");
  commit(0);if(count!=512 || duration!=1025)$fatal(1,"full bank commit");
  ctl(8);if(speed!=3)$fatal;ctl(8);if(speed!=0)$fatal;
  ctl(7);if(!demo || count!=56 || playing || tm!=0)$fatal(1,"select demo");
  events[0]=ev(0,1,1,0);begin_upload(1,10,0);repeat(40020)@(negedge clk);
  if(loading || !demo || count!=56)$fatal(1,"staging timeout changed demo");
  $display("PASS %0d framed commands: CRC/retry/banks, same-time chords, track colors, sustain, timing, pause, step, speed, 512-event boundary and timeouts",checks);
  $finish;
 end
 initial begin #6000000;$fatal(1,"global timeout");end
endmodule
