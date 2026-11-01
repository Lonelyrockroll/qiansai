`timescale 1ps/1ps
// The production top, real console/transport/store, actual shared RAM and score
// renderer are elaborated. Only unrelated IP is omitted by Icarus -i. The TB
// supplies clocks, a shortened frame boundary and parsed command fields; the
// guard, forward/return synchronizers and ownership wiring are NOT duplicated.
module score_ownership_tb;
 reg sys=0,pixel=0,rst=1,fs=0,cv=0;
 reg [7:0] op=0,length=0;reg [159:0] payload=0;
 integer phase=0,scenario=0,negative=0;
 always #10000 sys=~sys; // 50 MHz
 initial begin
  if(!$value$plusargs("PHASE_PS=%d",phase))phase=0;
  #(phase);forever #10204 pixel=~pixel; // 49.0004 MHz (1 ps precision)
 end
 synth_display_top top(.sys_clk(sys),.bt_rx(1'b1),.uart_rx(1'b1),.key0_n(1'b1),.key1_n(1'b1));
 initial begin
  force top.rst=rst;force top.pixel_rst=rst;force top.pixel_clk=pixel;
  force top.frame_start=fs;force top.x=11'd0;force top.y=11'd600;force top.de=1'b0;
  force top.cap_cv=1'b0;force top.cap_arm=1'b0;force top.tick=1'b0;
  force top.bluetooth.guide.score.command_valid=cv;
  force top.bluetooth.guide.score.command_op=op;
  force top.bluetooth.guide.score.command_length=length;
  force top.bluetooth.guide.score.command_payload=payload;
  force top.bluetooth.guide.score.ui_valid=1'b0;
  if(!$value$plusargs("CASE=%d",scenario))scenario=0;
  if($test$plusargs("NO_GUARD"))begin negative=1;force top.score_hide_guard=0;end
 end
 task issue(input [7:0] code,input [7:0] len,input [159:0] body);
 begin
  @(negedge sys);op=code;length=len;payload=body;cv=1;
  if(top.bluetooth.guide.score.command_ready!==1)$fatal(1,"Test attempted command while store not ready");
  @(posedge sys);#100;
 end endtask
 reg armed=0,clear_frame=0,stale_fired=0,clear_fired=0,saw_visible=0;
 reg saw_show=0,pending=0,saw_begin_ack=0;
 integer age=0,writes=0,ack_age=-1,owned_by_return=0;
 // Schedule a stale show precisely within the forward synchronization window;
 // the next frame is deliberately held off for longer than the 32-cycle guard.
 always @(negedge pixel)begin
  fs=0;
  if(!rst && armed && scenario!=2 && !stale_fired && !top.score_show && top.score_video.show_sync[1])begin
   fs=1;stale_fired=1;
  end else if(!rst && clear_frame && !clear_fired)begin fs=1;clear_fired=1;end
 end
 always @(posedge pixel)begin
  #100;
  if(armed && top.score_visible_pixel)saw_visible=1;
 end
 task check_write_safe;
 begin
  if(top.score_video_owned || top.score_show || top.score_visible_pixel || top.score_video.show_sync!=0 || top.score_select)
   $fatal(1,"UNSAFE write while display may read: owned=%b show=%b sync=%b actual=%b select=%b",
    top.score_video_owned,top.score_show,top.score_video.show_sync,top.score_visible_pixel,top.score_select);
 end endtask
 always @(posedge sys)begin
  if(!rst && armed)begin
   // Observe the actual write pulse presented to the physical RAM port.
   if(top.capture.shared.ram.sys_write===1'b1)begin check_write_safe;writes=writes+1;end
   if(top.score_show)begin saw_show=1;age=0;end else if(saw_show)age=age+1;
   #100;
   if(top.score_video_owned!==top.bluetooth.guide.score.video_visible)$fatal(1,"Store ownership wiring differs from top");
   if(!negative && saw_show && top.score_hide_guard!==((age<32)?32-age:0))
    $fatal(1,"32-cycle guard mismatch age=%d got=%d",age,top.score_hide_guard);
   if(saw_show && !top.score_show && !top.score_video_owned && (top.score_video.show_sync!=0 || top.score_visible_pixel))
    $fatal(1,"UNSAFE ownership released while stale show/visible can still be sampled");
   if(saw_show && age>=32 && top.score_hide_guard==0 && top.score_visible_sync[1] && top.score_video_owned)
    owned_by_return=owned_by_return+1;
   if(pending && top.bluetooth.guide.score.response_valid)begin
    if(top.bluetooth.guide.score.response_status!=0)$fatal(1,"BEGIN failed");
    if(top.score_video_owned || top.score_video.show_sync!=0 || top.score_visible_pixel || age<32)
     $fatal(1,"UNSAFE BEGIN ACK before CDC ownership release age=%d",age);
    pending=0;saw_begin_ack=1;ack_age=age;
   end
  end
 end
 reg [159:0] begin_body,chunk_body;
 initial begin
  repeat(8)@(negedge sys);rst=0;
  repeat(4)@(negedge sys);
  // Seed an already uploaded, valid page; the upload parser/CRC is covered by
  // its separate tests. SHOW, HIDE, BEGIN, CHUNK and the RAM write are real.
  top.bluetooth.guide.score.valid=1;armed=1;
  begin_body=0;begin_body[31:0]=2;begin_body[95:80]=1;begin_body[111:96]=1024;begin_body[127:112]=512;
  issue(20,1,160'd1); // SHOW, briefly high before any display frame boundary.
  if(top.score_show!==1)$fatal(1,"SHOW did not assert");
  if(scenario==1)begin issue(20,1,160'd0);if(top.score_show!==0)$fatal(1,"HIDE did not deassert");end
  issue(17,16,begin_body); // BEGIN itself hides in cases 0 and 2.
  if(top.score_show!==0 || top.score_loading!==1)$fatal(1,"BEGIN did not hide/start loading");
  pending=1;
  @(negedge sys);cv=0;
  repeat(50)@(negedge sys);
  if(stale_fired && (!saw_visible || saw_begin_ack || owned_by_return==0))
   $fatal(1,"Late visible page did not retain ownership beyond guard");
  if(scenario==2 && (!saw_begin_ack || ack_age!=33))
   $fatal(1,"Hidden case must release immediately after 32 cycles, ack age %d",ack_age);
  clear_frame=1;
  wait(saw_begin_ack===1'b1);
  chunk_body=0;chunk_body[31:24]=2;chunk_body[39:32]=2;chunk_body[47:40]=8'ha5;
  issue(18,6,chunk_body);
  @(negedge sys);cv=0;
  wait(writes==1);@(negedge sys);
  if(top.capture.shared.ram.memory[0]!==16'ha5a5)$fatal(1,"Actual shared RAM not written");
  $display("PASS CDC phase=%0d case=%0d stale=%0d visible=%0d ack_age=%0d held_by_return=%0d actual_ram_writes=%0d",phase,scenario,stale_fired,saw_visible,ack_age,owned_by_return,writes);
  $finish;
 end
 initial begin #20000000;$fatal(1,"Ownership test timeout phase=%d case=%d",phase,scenario);end
endmodule
