 task settle;begin repeat(6)@(posedge clk);#1;end endtask
 task local_action(input [3:0] action);begin pulse_ui(action);settle();end endtask
 task nav_command(input [7:0] command,input [7:0] page,input [7:0] cursor,input [7:0] expected);begin
   clear_payload();payload[0]=command;payload[1]=page;payload[2]=cursor;transaction(36,expected);
 end endtask
 task nav_select(input [7:0] page,input [7:0] cursor);begin
   nav_command(1,page,cursor,0);
   check(reply[7]==page && reply[8]==cursor,"selection reflected in same reply");
 end endtask
 task nav_execute;begin nav_command(2,0,0,0);end endtask
 task legacy(input [7:0] action,input [7:0] focus);begin
   clear_payload();payload[0]=action;payload[1]=focus;transaction(10,0);settle();
 end endtask
 task guarded_select(input [7:0] page,input [7:0] cursor,input [7:0] epoch,input [7:0] expected);begin
   clear_payload();payload[0]=1;payload[1]=page;payload[2]=cursor;payload[3]=1;payload[4]=epoch;transaction(36,expected);
 end endtask
 task guarded_execute(input [7:0] epoch,input [7:0] expected);begin
   clear_payload();payload[0]=2;payload[1]=1;payload[2]=epoch;transaction(36,expected);
 end endtask
 reg [7:0] saved_epoch;
 integer page, row, before_fx, before_guide, before_record, before_clear, before_flush, before_cal;
 integer effect_count=0,guide_count_seen=0,clear_count=0,record_count=0,flush_count=0,cal_count=0,express_count=0;
 integer last_loop=0,last_guide=0;
 always @(posedge clk)if(!rst)begin
   if(dut.fx_command_valid)effect_count=effect_count+1;
   if(dut.guide_ui_valid)begin guide_count_seen=guide_count_seen+1;last_guide=dut.guide_ui_action;end
   if(dut.loop_command_valid)begin
     last_loop=dut.loop_command;
     if(dut.loop_command==1)record_count=record_count+1;
     if(dut.loop_command==5)clear_count=clear_count+1;
   end
   if(dut.live_piano_flush)flush_count=flush_count+1;
   if(dut.key_recalibrate)cal_count=cal_count+1;
   if(dut.express_adjust)express_count=express_count+1;
 end
 initial begin
   force dut.rx_valid=inject_valid;force dut.rx_data=inject_data;force dut.rx_error=1'b0;
   score_visible=0;score_show_requested=0;score_reserved=0;
   repeat(5)@(posedge clk);@(negedge clk);rst=0;
   nav_command(0,0,0,0);
   check(reply[7]==0 && reply[8]==0 && reply[9]==0 && reply[10]==6 && reply[12]==1,"boot hierarchy and capability revision");
   for(i=14;i<24;i=i+1)check(reply[i]==0,"navigation response reserved bytes zero");
   check(!amp_hold && !dut.ui_local,"query never starts audio");

   // All pages have bounded wrap, and browsing never changes the audio session.
   for(page=0;page<6;page=page+1)begin
     nav_select(page,0);local_action(9);
     check(dut.ui_cursor==(page==4?4:5),"backward wrap at page start");
     local_action(1);check(dut.ui_cursor==0,"forward wrap at page end");
     local_action(1);check(dut.ui_cursor==1,"single navigation step");
     nav_command(0,0,0,0);check(reply[10]==(page==4?5:6),"row count per page");
     check(!amp_hold && !dut.ui_local,"browsing does not take audio ownership");
   end
   nav_select(0,1);nav_execute();
   check(reply[7]==1 && reply[8]==1,"execute returns entered submenu state");
   nav_command(3,0,0,0);check(reply[7]==0 && reply[8]==1,"back restores the originating home row");
   nav_select(3,0);local_action(2);check(dut.ui_page==0 && dut.ui_cursor==3,"physical Back row");

   // Direct timbres map to the engine's existing five voices.
   for(row=1;row<=5;row=row+1)begin
     nav_select(1,row);before_flush=flush_count;nav_execute();
     check(dut.key_wave==(row==1?4:row-2),"direct timbre assignment");
     check(flush_count==before_flush+1,"timbre switches flush live piano exactly once");
   end
   for(row=1;row<=5;row=row+1)begin
     nav_select(2,row);before_fx=effect_count;nav_execute();
     case(row)
       1:check(dut.fx_mask==0 && dut.fx_feedback==96 && dut.fx_delay_time==2,"dry preset");
       2:check(dut.fx_mask==1 && dut.fx_reverb_mix==128 && dut.fx_delay_mix==0,"reverb preset");
       3:check(dut.fx_mask==2 && dut.fx_delay_mix==128 && dut.fx_reverb_mix==0,"delay preset");
       4:check(dut.fx_mask==4 && dut.fx_chorus_mix==128 && dut.fx_delay_mix==0,"chorus preset");
       5:check(dut.fx_mask==7 && dut.fx_reverb_mix==64 && dut.fx_delay_mix==64 && dut.fx_chorus_mix==112,"combined preset");
     endcase
     check(effect_count==before_fx+1,"one FX command per selection");
   end

   // Destructive Loop clear requires a second intentional activation.
   nav_select(3,5);before_clear=clear_count;nav_execute();
   check(reply[9][0] && clear_count==before_clear,"first clear arms confirmation only");
   nav_command(0,0,0,0);check(reply[9][0],"query preserves confirmation");
   nav_select(3,5);check(reply[9][0],"reselecting the same touched row preserves confirmation");
   nav_execute();check(!reply[9][0] && clear_count==before_clear+1,"second clear emits one command");
   nav_execute();local_action(9);local_action(1);
   check(!dut.ui_confirm,"rotation cancels confirmation even when returning to same row");
   nav_execute();check(clear_count==before_clear+1 && dut.ui_confirm,"post-rotation clear needs two activations again");
   nav_select(0,0);check(!dut.ui_confirm,"different selection cancels confirmation");
   nav_execute();check(amp_hold && !dut.ui_local,"host start takes host session ownership");
   local_action(2);check(!amp_hold,"local stop");
   local_action(2);check(amp_hold && dut.ui_local,"local start takes local ownership");
   local_action(3);check(!amp_hold && dut.ui_page==0 && dut.ui_cursor==0,"A mutes and returns home");
   nav_select(3,1);before_record=record_count;nav_execute();
   check(record_count==before_record+1 && amp_hold,"record starts amp and emits cmd1");
   loop_recording=1;nav_execute();check(record_count==before_record+2,"record/end uses cmd1 in either state");loop_recording=0;
   nav_select(3,2);nav_execute();check(last_loop==3,"Loop play/pause");
   nav_select(3,3);nav_execute();check(last_loop==2,"Loop undo");
   nav_select(3,4);nav_execute();check(last_loop==4,"Loop duration");

   nav_select(4,1);before_guide=guide_count_seen;nav_execute();check(last_guide==4 && guide_count_seen==before_guide+1,"guide play/pause");
   nav_select(4,2);nav_execute();check(last_guide==3,"guide return to start");
   nav_select(4,3);nav_execute();check(last_guide==8,"guide speed");
   score_valid=0;nav_select(4,4);before_count=accepted;nav_execute();
   check(dut.ui_notice==3 && accepted==before_count,"missing PDF gives notice without transport command");
   score_valid=1;nav_execute();check(accepted==before_count+1 && last_action==1,"cached PDF show request");
   score_visible=1;score_show_requested=1;nav_select(0,0);before_count=accepted;
   nav_execute();check(accepted==before_count+1 && last_action==0,"PDF B priority over selected underlying action");
   score_visible=0;score_show_requested=0;

   // Backpressure is lossless. A page show waits without duplicated commands.
   nav_select(4,4);score_ui_ready=0;before_count=accepted;
   fork
     begin nav_execute();end
     begin wait(dut.state==11);repeat(30)@(posedge clk);#1;
       check(dut.ui_pending && accepted==before_count,"PDF show waits for transport ready");
       @(negedge clk);score_ui_ready=1;end
   join
   check(accepted==before_count+1 && !reply[9][3],"PDF show accepted once before response");

   nav_select(5,1);before_cal=cal_count;nav_execute();check(dut.key_mode==2 && cal_count==before_cal+1,"scan enable with calibration");
   nav_select(5,2);nav_execute();check(cal_count==before_cal+2,"explicit calibration");
   nav_select(5,1);nav_execute();check(dut.key_mode==0,"scan disable");
   nav_select(5,2);nav_execute();check(dut.ui_notice==1,"calibrate with scan disabled gives notice");
   nav_select(5,3);nav_execute();check(!dut.drum_mode,"volume target toggles without changing page");
   check(dut.ui_page==5 && dut.ui_cursor==3,"settings selection retained after target switch");
   ui_value=16'd17000;local_action(7);check(dut.key_level==17000,"B-held volume uses current target");
   ui_value=1;before_count=express_count;local_action(13);local_action(15);
   check(express_count==before_count+2 && dut.express_depth && dut.express_up,"A pitch gestures retained");ui_value=0;
   nav_select(5,5);nav_execute();check(dut.ui_pattern,"screen pattern enabled");nav_execute();check(!dut.ui_pattern,"screen pattern disabled");
   nav_select(5,4);nav_execute();check(dut.monitor_open && reply[9][1],"monitor opens from settings");
   local_action(2);check(dut.monitor_demo==1,"monitor B starts 32-tone test");
   local_action(2);check(dut.monitor_demo==2,"monitor B chooses 31-tone test");
   local_action(1);check(dut.missing_voice==16 && dut.ui_cursor==4,"monitor rotation moves missing tone, not menu");
   nav_command(3,0,0,0);check(!dut.monitor_open && !amp_hold,"Back exits test safely");

   // Legacy flat commands keep their semantics, including destructive actions.
   legacy(6,8);before_fx=effect_count;legacy(2,0);
   check(effect_count==before_fx+1 && dut.ui_focus==8,"legacy select followed by host execute");
   nav_select(2,1);legacy(6,8);local_action(2);
   check(dut.fx_mask==0 && !dut.legacy_selection,"physical B follows visible menu after legacy selection");
   nav_select(2,1);legacy(6,8);local_action(1);before_fx=effect_count;local_action(2);
   check(dut.fx_mask==1 && effect_count==before_fx+1,"physical rotation releases legacy selection latch");
   legacy(5,0);check(amp_hold,"legacy flat start remains available");
   check(!dut.legacy_selection,"legacy execute leaves no hidden selection latch");
   legacy(5,6);check(!amp_hold,"legacy flat mute remains available");
   legacy(5,9);check(last_guide==4,"legacy guide action retained");
   legacy(5,7);check(dut.drum_mode,"legacy volume target retained");
   before_clear=clear_count;legacy(5,5);check(clear_count==before_clear+1,"legacy clear remains immediate for protocol compatibility");
   nav_select(0,0);legacy(9,0);check(dut.ui_cursor==5,"host previous action accepted");
   nav_command(1,6,0,3);check(dut.ui_page==0 && dut.ui_cursor==5,"bad page rejected without mutation");
   nav_command(1,4,5,3);nav_command(1,0,6,3);nav_command(4,0,0,3);

   // An emergency between either host transaction boundary invalidates a tap,
   // including the case where its visible page and cursor do not change.
   local_action(3);nav_command(0,0,0,0);saved_epoch=reply[13];
   local_action(3);guarded_select(0,0,saved_epoch,4);
   check(!amp_hold && dut.ui_page==0 && dut.ui_cursor==0,"A on home row zero invalidates stale selection");
   nav_command(0,0,0,0);saved_epoch=reply[13];
   guarded_select(2,3,saved_epoch,0);saved_epoch=reply[13];
   local_action(3);guarded_execute(saved_epoch,4);
   check(!amp_hold && dut.ui_page==0 && dut.ui_cursor==0,"A between select and execute cannot restart audio");
   nav_command(0,0,0,0);saved_epoch=reply[13];
   guarded_select(2,3,saved_epoch,0);saved_epoch=reply[13];
   guarded_execute(saved_epoch,0);check(dut.fx_mask==2,"matching guarded click executes selected effect");
   guarded_execute(saved_epoch,4);check(dut.fx_mask==2,"replayed execute token is rejected");
   nav_select(3,5);saved_epoch=reply[13];before_clear=clear_count;
   guarded_execute(saved_epoch,0);check(dut.ui_confirm && clear_count==before_clear,"guarded clear first click confirms only");
   saved_epoch=reply[13];guarded_select(3,5,saved_epoch,0);saved_epoch=reply[13];
   guarded_execute(saved_epoch,0);check(!dut.ui_confirm && clear_count==before_clear+1,"fresh second click clears exactly once");
   guarded_execute(saved_epoch,4);check(clear_count==before_clear+1,"stale clear cannot execute twice");
   nav_command(0,0,0,0);saved_epoch=reply[13];nav_command(0,0,0,0);
   check(reply[13]==saved_epoch,"read-only polling preserves the interaction epoch");
   nav_select(5,5);nav_execute();local_action(3);
   check(!dut.ui_pattern && dut.ui_page==0 && dut.ui_cursor==0,"A exits full-screen pattern and returns visible home");

   // A button sampled on the selection packet's final byte is explicitly
   // reported as pending. Clients must reject that acknowledgement before
   // using its epoch, even though the selection itself was accepted.
   nav_command(0,0,0,0);saved_epoch=reply[13];
   clear_payload();payload[0]=1;payload[1]=2;payload[2]=3;payload[3]=1;payload[4]=saved_epoch;
   fork
     begin start_request(36);end
     begin
       wait(dut.rx_index==27 && inject_valid && inject_data==13);
       ui_action=3;ui_valid=1;@(negedge clk);ui_valid=0;
     end
   join
   finish_reply(36,0);settle();
   check(reply[9][3],"selection acknowledgement exposes simultaneous pending emergency");
   check(!amp_hold && dut.ui_page==0 && dut.ui_cursor==0,"simultaneous emergency wins after selection reply");

   // Queued local requests wait for complete UART response boundaries.
   nav_select(0,1);clear_payload();start_request(36);
   wait(dut.state==3);@(negedge clk);ui_action=1;ui_valid=1;@(negedge clk);ui_valid=0;settle();
   check(dut.ui_pending && dut.ui_cursor==1,"local navigation queued during serial transmit");
   finish_reply(36,0);settle();check(dut.ui_cursor==2 && !dut.ui_pending,"queued navigation applied once after transmit");
   nav_select(3,5);local_action(2);check(dut.ui_confirm,"confirmation armed before emergency");
   @(negedge clk);native_panic=1;@(negedge clk);native_panic=0;settle();
   check(dut.ui_page==0 && dut.ui_cursor==0 && !dut.ui_confirm && !amp_hold,"native emergency returns home and clears confirmation");
   if(failures)$fatal(1,"navigation failed %0d of %0d checks",failures,checks);
   $display("PASS hierarchy navigation %0d checks, %0d UART replies: pages, presets, confirmation, legacy, overlays and packet boundaries",checks,seqno);
   $finish;
 end
 initial begin #100000000;$fatal(1,"navigation timeout");end
endmodule
