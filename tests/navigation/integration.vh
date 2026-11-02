 wire guide_valid,guide_playing,guide_loading,guide_demo;
 wire [15:0] guide_time_cs,guide_duration_cs;
 wire [9:0] guide_count,guide_index;
 wire [1:0] guide_speed;
 wire [31:0] guide_current;
 reg guide_tick=0;
 guide_player player(.clk(clk),.rst(rst),.audio_tick(guide_tick),
   .command_valid(1'b0),.command_op(8'd0),.command_length(8'd0),.command_payload(160'd0),
   .ui_valid(guide_ui_valid),.ui_action(guide_ui_action),
   .guide_valid(guide_valid),.guide_playing(guide_playing),.guide_loading(guide_loading),.guide_demo(guide_demo),
   .guide_time_cs(guide_time_cs),.guide_duration_cs(guide_duration_cs),.guide_count(guide_count),.guide_index(guide_index),
   .guide_speed(guide_speed),.guide_current(guide_current));
 wire loop_playing,loop_recording,loop_pending;
 wire [1:0] loop_duration;
 wire [2:0] loop_notice;
 wire [18:0] loop_actual_length;
 reg loop_tick=0,live_event=0;
 wire live_ready;
 performance_looper #(.FRAMES_2(64),.FRAMES_4(128),.FRAMES_8(256),.PREP_FRAMES(2),.MIN_FRAMES(8)) looper(
   .clk(clk),.rst(rst),.sample_tick(loop_tick),.session(amp_hold),.audio_ready(amp_ready),.stop(panic),
   .command_valid(loop_command_valid),.command(dut.loop_command),
   .live_valid(live_event),.live_data(123'd1),.live_ready(live_ready),.out_ready(1'b1),
   .playing(loop_playing),.recording(loop_recording),.pending_record(loop_pending),.layers(loop_layers),
   .duration_index(loop_duration),.notice(loop_notice),.layer_counts(loop_counts),.actual_length(loop_actual_length));
 task choose(input [7:0] page,input [7:0] row);begin nav_select(page,row);nav_execute();settle();end endtask
 task advance_loop(input integer samples);integer n;begin
   for(n=0;n<samples;n=n+1)begin
     @(negedge clk);loop_tick=1;@(negedge clk);loop_tick=0;repeat(2)@(negedge clk);
   end
   settle();
 end endtask
 task record_event;begin
   wait(live_ready);@(negedge clk);live_event=1;@(negedge clk);live_event=0;settle();
 end endtask
 task record_layer;begin
   choose(3,1);check(loop_pending,"record enters real looper preparation");
   advance_loop(2);check(loop_recording && loop_playing,"preparation enters actual recording");
   record_event();advance_loop(12);choose(3,1);
   check(!loop_recording && loop_playing && loop_actual_length==13,"finish recording commits actual timed layer");
 end endtask
 reg [15:0] saved_time;
 initial begin
   force dut.rx_valid=inject_valid;force dut.rx_data=inject_data;force dut.rx_error=1'b0;
   score_visible=0;score_show_requested=0;score_reserved=0;
   repeat(5)@(posedge clk);@(negedge clk);rst=0;
   choose(4,1);
   check(guide_playing,"play menu starts actual guide timeline");
   guide_tick=1;repeat(26000)@(posedge clk);@(negedge clk);guide_tick=0;settle();
   check(guide_time_cs>=50 && guide_index>=2,"real timeline advances time and musical events");
   saved_time=guide_time_cs;choose(4,1);
   check(!guide_playing && guide_time_cs==saved_time,"pause menu preserves timeline position");
   choose(4,1);check(guide_playing,"play resumes paused timeline");
   choose(4,3);
   check(guide_speed==3 && guide_playing && guide_time_cs==saved_time,"speed menu changes rate without stopping or rewinding");
   choose(4,3);check(guide_speed==0 && guide_playing,"speed selection wraps through supported rates");
   choose(4,2);
   check(!guide_playing && guide_time_cs==0 && guide_index==0 && guide_current==0,"return-to-start resets and stops actual timeline");
   choose(4,1);guide_tick=1;repeat(6000)@(posedge clk);@(negedge clk);guide_tick=0;settle();
   check(guide_playing && guide_time_cs>0,"guide can play again after returning to start");

   // These checks read real looper state, rather than command numbers.
   choose(3,4);check(loop_duration==0,"duration menu changes actual recording upper limit");
   choose(3,4);check(loop_duration==1,"duration cycles to four seconds");
   record_layer();check(loop_layers==1 && loop_counts[8:0]==1,"first layer contains captured event");
   choose(3,2);check(!loop_playing && loop_layers==1,"stop playback retains committed layer");
   choose(3,2);check(loop_playing,"play menu restarts actual loop");
   choose(3,2);record_layer();check(loop_layers==2,"second stopped-session take commits another layer");
   choose(3,3);check(loop_layers==1,"undo removes exactly one actual layer");
   choose(3,5);check(dut.ui_confirm && loop_layers==1,"first clear leaves actual layer intact");
   nav_execute();settle();check(loop_layers==0 && !loop_playing && !loop_recording,"confirmed clear clears actual looper");
   choose(3,1);advance_loop(2);record_event();advance_loop(12);local_action(3);
   check(!loop_pending && !loop_recording && !loop_playing && !amp_hold,"A aborts active take and silences actual looper");
   if(failures)$fatal(1,"integration failed %0d of %0d checks",failures,checks);
   $display("PASS navigation integration %0d checks, %0d UART replies: real guide timeline and real Loop state",checks,seqno);
   $finish;
 end
 initial begin #100000000;$fatal(1,"integration timeout");end
endmodule
