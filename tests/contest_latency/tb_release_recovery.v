`timescale 1ns/1ps
// Production scanner, permutation, event queue, looper, router, release guard,
// onset meter and serial transmitter. Stand-ins provide Hall codes, PCM and
// bounded engine backpressure. No board latency is inferred from this test.
module tb_release_recovery;
  reg clk=0,rst=1;always #10 clk=~clk;
  wire [4:0] addr;reg [31:0] sensors=0;
  synth_display_top dut(.sys_clk(clk),.bt_rx(1'b1),.key_addr(addr));
  defparam dut.keys.STARTUP_CYCLES=3; // skip the power-on delay only
  reg eoc=1;reg [12:0] adc=4000,latched=4000;integer conversion_left=0;
  wire [4:0] channel_key=(addr>=16 && addr<28)?43-addr:addr;
  reg [4:0] layout[0:31];reg [9:0] engine_counter=0;
  wire engine_ready=engine_counter<4;
  reg signed [15:0] pcm=0;reg compare_stream=0;
  wire pad=(dut.tx.count==171);
  always @(posedge clk)begin
    engine_counter<=engine_counter==907?0:engine_counter+1'b1;
    if(rst)begin eoc<=1;adc<=4000;conversion_left<=0;end
    else if(dut.adc_soc)begin latched<=sensors[channel_key]?4720:4000;eoc<=0;conversion_left<=20;end
    else if(conversion_left>0)begin
      conversion_left<=conversion_left-1;
      if(conversion_left==1)begin adc<=latched;eoc<=1;end
    end
  end
  function [31:0] phase_step(input [4:0] white_key);
    integer note,pitch_class;real hz;
    begin
      case(white_key%7)0:pitch_class=0;1:pitch_class=2;2:pitch_class=4;3:pitch_class=5;
        4:pitch_class=7;5:pitch_class=9;default:pitch_class=11;endcase
      note=36+12*(white_key/7)+pitch_class;hz=440.0*(2.0**((note-69)/12.0));
      phase_step=$rtoi(hz*4294967296.0/48828.125+0.5);
    end
  endfunction
  integer accepted=0,applied=0;
  reg [37:0] expected[0:8191];reg [31:0] expected_keys=0;
  always @(posedge clk)if(compare_stream)begin
    if(dut.key_cv && dut.key_cr)begin
      if(dut.key_voice!==dut.physical_scan || dut.mapped_key!==layout[dut.key_voice])$fatal(1,"wrong scan/mapped key");
      if(dut.key_gate===expected_keys[dut.key_voice])$fatal(1,"duplicate edge");
      expected_keys[dut.key_voice]=dut.key_gate;
      expected[accepted]={dut.key_gate,dut.key_voice,phase_step(layout[dut.key_voice])};accepted=accepted+1;
      if(accepted>=8192)$fatal(1,"too many test events");
    end
    if(dut.router.cfg_valid && dut.router.cfg_ready)begin
      if(applied>=accepted || expected[applied]!=={dut.routed_gate,dut.router.payload[119:115],dut.routed_step})
        $fatal(1,"lost/reordered edge/pitch at %0d",applied);
      applied=applied+1;
    end
  end

  reg [122:0] injected_event;reg [2:0] injected_source;
  task inject(input [2:0] source,input [4:0] key,input gate);
    integer before_count;
    begin
      @(negedge clk);while(!dut.router_ready || dut.queued_valid)@(negedge clk);
      before_count=dut.router_notes;injected_source=source;
      injected_event={2'b01,gate,key,3'd0,phase_step(key),16'd4096,16'd269,16'd6,16'd40000,16'd5};
      force dut.queued_valid=1;force dut.queued_source=injected_source;force dut.queued_data=injected_event;
      @(negedge clk);force dut.queued_valid=0;
      @(negedge clk);release dut.queued_valid;release dut.queued_source;release dut.queued_data;
      wait(dut.router_notes==before_count+1);
    end
  endtask
  integer i,frame,start_scan,last_latency;reg [31:0] seed=32'h195757;
  initial begin
    force dut.rst=rst;force dut.clear_engine=0;force dut.uart_panic=0;force dut.amp_muting=0;force dut.amp_ready=1;force dut.uart_amp_hold=1;
    force dut.key_mode=2;force dut.key_test=14;force dut.key_wave=0;force dut.key_level=4588;force dut.key_recalibrate=0;
    force dut.key_press=256;force dut.key_release=128;force dut.key_scale=64;force dut.key_attack=269;force dut.key_decay=6;force dut.key_sustain=40000;force dut.key_tail=5;
    force dut.adc_eoc=eoc;force dut.adc_data=adc;force dut.monitor_demo=0;force dut.monitor_open=1;force dut.monitor_fade=0;
    force dut.control_live_flush=0;force dut.loop_command_valid=0;force dut.drum_hit_valid=pad;force dut.drum_hit_pad=0;
    force dut.drum_engine_ready=1;force dut.pc_pad_valid=0;force dut.engine_ready=engine_ready;
    force dut.music_active_mask=32'hffffffff;force dut.music_voices=0;force dut.drum_voices=0;
    force dut.pcm=pcm;force dut.fx_tail=0;force dut.pt_mode=2;force dut.pt_bias=1577;
    repeat(4)@(negedge clk);rst=0;
    for(i=0;i<32;i=i+1)begin layout[i]=(13*i+7)%32;dut.bluetooth.guide.keys.layout[i]=layout[i];end
    wait(dut.key_calibrated);

    // Acquire a real physical key, then supply a serial PCM word just for the
    // sticky-LAST lifecycle test. Numeric onset timings use tb_latency's synth.
    @(negedge clk);sensors[14]=1;wait(dut.key_pressed[14]);@(negedge clk);pcm=1200;
    wait(dut.onset_valid);last_latency=dut.onset_us;
    if(dut.measurement_count!=1 || dut.measured_key!=14)$fatal(1,"bad first LAST");
    sensors[15]=1;wait(dut.key_pressed[15]);wait(dut.live_held_count==2);
    start_scan=dut.key_scans;wait(dut.key_scans==start_scan+4);
    if(!dut.onset_valid || dut.onset_marker || dut.onset_us!=last_latency || dut.measured_key!=14 ||
       dut.measurement_count!=1 || dut.orphan_flush_count!=0)$fatal(1,"chord erased LAST or held keys flushed");
    sensors=0;wait(dut.live_held_count==0);@(negedge clk);pcm=0;

    // Seed a recorded layer: one sustained note plus one drum hit every audio
    // frame. Playback, RAM fetch and arbitration after this setup are real.
    // Dense replay and a competing live pad must not starve reconciliation.
    @(negedge clk);dut.looper.layers=1;dut.looper.actual_length=10000;dut.looper.count[0]=256;
    dut.looper.memory[0]={2'd0,19'd0,2'b01,1'b1,5'd8,3'd0,phase_step(8),16'd4096,16'd269,16'd6,16'd40000,16'd5};
    for(i=1;i<256;i=i+1)dut.looper.memory[i]={2'd0,i[18:0],2'b00,1'b1,1'b0,4'd2,115'd0};
    dut.looper.playing=1;
    wait(dut.held_count==1 && dut.live_held_count==0);
    inject(0,3,1);inject(0,7,1);inject(0,12,1);
    wait(dut.live_held_count==3 && dut.held_count==4);start_scan=dut.key_scans;
    wait(dut.orphan_flush);if(dut.key_scans-start_scan<2 || dut.key_scans-start_scan>3)$fatal(1,"guard boundary count");
    wait(dut.live_held_count==0 && dut.held_count==1);
    start_scan=dut.key_scans;wait(dut.key_scans==start_scan+4);
    if(dut.orphan_flush_count!=1 || dut.live_held_count!=0 || dut.held_count!=1 ||
       !dut.loop_playing || dut.loop_replayed<100)$fatal(1,"repeated/global flush or interrupted Loop");
    $display("LOOP %0d replay events while sustained Loop voice survives the one source-0 flush",dut.loop_replayed);
    @(negedge clk);force dut.loop_command_valid=1;force dut.loop_command=3;
    @(negedge clk);force dut.loop_command_valid=0;wait(dut.held_count==0 && !dut.loop_playing);

    // Stress clocked scan/lookup and queue stalls, including an audio tick and
    // competing drum pulses. Check every accepted physical event at the router.
    compare_stream=1;sensors=32'hffffffff;repeat(80000)@(negedge clk);
    sensors=0;repeat(80000)@(negedge clk);
    if(accepted!=64 || applied!=64 || expected_keys!=0 || dut.held_mask!=0)$fatal(1,"full chord lost events");
    for(frame=0;frame<72;frame=frame+1)begin
      seed=1664525*seed+1013904223;sensors=seed;repeat(10007+(frame%7)*1043)@(negedge clk);
    end
    sensors=0;repeat(80000)@(negedge clk);
    if(accepted!=applied || expected_keys!=0 || dut.key_pressed!=0 || dut.mapped_pressed!=0 ||
       dut.held_mask!=0 || dut.orphan_flush_count!=1 || dut.router_ignored!=0 || dut.router_steals!=0)
      $fatal(1,"unpaired events or unnecessary recovery");
    $display("PASS recovery: LAST retained over second chord key; 3 orphan live notes cleared once during dense live pads/Loop playback; sustained Loop note preserved; %0d paired physical-ID/mapped-step events, 72 input masks, no ignored off/steals.",applied);$finish;
  end
  initial begin #100000000;$fatal(1,"test timeout");end
endmodule
