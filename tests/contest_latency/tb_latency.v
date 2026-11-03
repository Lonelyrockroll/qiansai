`timescale 1ns/1ps
// Run the production top's physical-key to serial-audio cone. The test replaces
// the analog ADC with an explicit conversion model. It does not replace the
// scanner, event arbitration, synthesizer, effects, limiter or serializers.
module tb_latency;
  reg clk=0, rst=1, flush=0, hold_open=1, monitor_view=0;
  always #10 clk=~clk;
  wire bclk, lrclk, serial_data, hp_clk, hp_ws, hp_data;
  wire [4:0] addr;
  synth_display_top top(.sys_clk(clk),.midi_rx(1'b1),.bt_rx(1'b1),.key_addr(addr),.i2s_bclk(bclk),
    .i2s_lrclk(lrclk),.i2s_data(serial_data),.HP_BCK(hp_clk),.HP_WS(hp_ws),.HP_DIN(hp_data));

  localparam REVISIT_NS=751*32*20;
  integer key=14,volume=4588,timbre=0,stim=0,slope=0,conversion_clocks=20;
  reg [12:0] sample=4000,latch_code=4000;
  reg eoc=1, measure=0;
  integer conversion_left=0;
  time motion=0,threshold=0,first_adc=0,accepted=0,routed=0,first_pcm=0;
  time first_i2s=0,first_i2s16=0,first_pt=0,prior_internal_tick=0,last_aperture=0;
  time mark_rise=0,mark_fall=0;
  integer level=0,velocity=0,peak=0,words=0;
  wire [4:0] target_channel=(key>=16 && key<28)?43-key:key;
  wire [15:0] attack=(timbre==4?672:269),decay=(timbre==4?2:6);
  wire [15:0] sustain=(timbre==4?0:40000),release_rate=(timbre==4?8:5);

  function integer input_at(input time now_ns);
    time displacement;
    begin
      displacement=0;
      if(addr==target_channel && stim!=0)begin
        displacement=stim==1?1024:(now_ns-motion)*slope/REVISIT_NS;
        if(displacement>1400)displacement=1400;
      end
      input_at=4000+displacement;
    end
  endfunction

  // Every SOC samples the currently addressed Hall channel. The code is held
  // through the EOC handshake. The production scanner discards conversion 0.
  always @(posedge clk)begin
    if(rst)begin eoc<=1;conversion_left<=0;sample<=4000;end
    else if(top.adc_soc)begin
      eoc<=0;conversion_left<=conversion_clocks;latch_code<=input_at($time);
      if(measure && addr==target_channel && top.keys.conversion!=0 &&
         input_at($time)>=4256 && first_adc==0)first_adc=$time;
      if(top.key_calibrated && addr==target_channel && top.keys.conversion==2)begin
        if(last_aperture!=0 && $time-last_aperture!=REVISIT_NS)
          $fatal(1,"nonconstant scan period %0d ns",$time-last_aperture);
        last_aperture=$time;
      end
    end else if(conversion_left>0)begin
      conversion_left<=conversion_left-1;
      if(conversion_left==1)begin eoc<=1; sample<=latch_code;end
    end
    if(!rst && top.tick)begin
      if(prior_internal_tick!=0 && $time-prior_internal_tick!=20480)$fatal(1,"audio tick period");
      prior_internal_tick=$time;
    end
    if(measure && top.key_cv && top.key_cr && top.key_gate)begin
      if(accepted!=0 || top.key_voice!=key)$fatal(1,"unexpected second/key Note On");
      accepted=$time;level=top.key_cv_level;velocity=top.key_velocity;
    end
    if(measure && top.routed_cfg_valid && top.engine_ready && top.routed_gate && routed==0)begin
      routed=$time;
      if((key==0 && top.routed_step!==5753207) || (key==14 && top.routed_step!==23012828) ||
         (key==31 && top.routed_step!==122873760))$fatal(1,"mapped pitch mismatch for key %0d",key);
    end
  end
  always @(posedge top.fx_valid)if(measure && top.pcm!=0 && first_pcm==0)first_pcm=$time;
  always @(posedge top.debug_sample)if(measure && monitor_view && mark_rise==0)mark_rise=$time;
  always @(negedge top.debug_sample)if(measure && monitor_view && mark_rise!=0 && mark_fall==0)mark_fall=$time;
  always @(negedge clk)if(measure && $time>=threshold && $time-threshold>10000000)
    $fatal(1,"no usable word in 10 ms: key=%0d adc=%0d accepted=%0d routed=%0d pcm=%0d i2s=%0d",key,first_adc,accepted,routed,first_pcm,first_i2s);

  reg serial_started=0;integer i2bits=0,ptbits=0,actual=0,actual_pt=0;
  reg [15:0] i2word,ptword;
  always @(posedge clk)begin
    if(rst)serial_started=0;
    else if(top.tick)begin serial_started=1;i2bits=0;ptbits=0;end
  end
  always @(posedge bclk)if(serial_started && !rst)begin
    if(lrclk!==(i2bits>=32))$fatal(1,"I2S LRCLK alignment");
    if((i2bits%32)>=1 && (i2bits%32)<=16)i2word={i2word[14:0],serial_data};
    else if(serial_data!==1'b0)$fatal(1,"I2S padding");
    if(i2bits==16 && measure)begin
      if(^i2word===1'bx || i2word!==top.tx.left_frame)$fatal(1,"bad serial sample %h",i2word);
      actual=$signed(i2word);if(actual<0)actual=-actual;
      if(accepted!=0)words=words+1;
      if(actual>peak)peak=actual;
      if(actual!=0 && first_i2s==0)first_i2s=$time;
      if(actual>=16 && first_i2s16==0)first_i2s16=$time;
    end
    i2bits=i2bits+1;
  end
  function integer bias_for(input integer lane);
    case(lane)0:bias_for=1577+140;1:bias_for=1577-140;2:bias_for=1577+36;default:bias_for=1577-38;endcase
  endfunction
  always @(posedge hp_clk)if(serial_started && !rst)begin
    ptword={ptword[14:0],hp_data};
    if(measure && ptbits%16==15)begin
      if(hp_ws!==((ptbits%32)>=16) || ^ptword===1'bx)$fatal(1,"bad PT slot");
      actual_pt=$signed(ptword)-bias_for(ptbits/32);
      if(actual_pt!=$signed(top.tx.left_frame))$fatal(1,"PT word/bias mismatch");
      if(actual_pt!=0 && first_pt==0)first_pt=$time;
    end
    ptbits=ptbits+1;
  end

  task boot;
    begin
      rst=1;measure=0;stim=0;flush=0;last_aperture=0;prior_internal_tick=0;
      repeat(6)@(negedge clk);rst=0;
      wait(top.key_calibrated && top.amp_ready);
      repeat(10)@(negedge clk);
      if(top.keys.baseline[key]!=4000 || top.key_fault)$fatal(1,"calibration failed");
    end
  endtask
  task check_meter(input integer id);
    integer difference_ns;
    begin
      if(monitor_view)begin
        difference_ns=$signed({1'b0,top.onset_us})*1000-$signed(first_i2s-accepted);
        if(top.onset_valid!==1 || mark_rise!=accepted || mark_fall!=first_i2s+20 ||
           difference_ns< -1000 || difference_ns>1000)
          $fatal(1,"onset meter invalid id=%0d valid=%b rise=%0d fall=%0d independent=%0d us_error_ns=%0d",
            id,top.onset_valid,mark_rise,mark_fall,first_i2s,difference_ns);
        $display("METER %0d %0d %0d %0d %0d",id,first_i2s-accepted,mark_fall-mark_rise,top.onset_us,difference_ns);
      end
    end
  endtask
  task run_note(input integer id,logical_key,wave_id,maximum,phase,rate,window);
    integer q14,expected;
    begin
      last_aperture=0;key=logical_key;volume=maximum;timbre=wave_id;
      // Start silently. A clear between independent trials clears previous tails,
      // but is never asserted between the modeled movement and the serial word.
      @(negedge clk);flush=1;@(negedge clk);flush=0;
      repeat(12)@(posedge top.tick);
      @(negedge clk);
      while(!(top.adc_soc && addr==target_channel && top.keys.conversion==2))@(negedge clk);
      repeat(phase)@(negedge clk);
      if(top.pcm!=0 || top.key_pressed!=0 || !top.amp_ready || top.output_stage.gain_q!=1024)
        $fatal(1,"test requires a silent warmed instrument");
      motion=$time;slope=rate;stim=(rate==0)?1:2;
      threshold=motion+(rate==0 ? 0 : (256*REVISIT_NS+rate-1)/rate);
      first_adc=0;accepted=0;routed=0;first_pcm=0;first_pt=0;first_i2s=0;first_i2s16=0;
      peak=0;words=0;mark_rise=0;mark_fall=0;measure=1;
      wait(first_i2s16!=0 && first_pt!=0 && words>=window);
      measure=0;
      if(first_adc<threshold || accepted<first_adc || routed<accepted || first_pcm<routed ||
         first_i2s<first_pcm || first_pt<first_pcm || first_i2s16-threshold>5000000 ||
         top.overrun || top.fx_overrun || top.limiter_overrun || top.key_fault)$fatal(1,"latency/order/error");
      q14=velocity*64;if(q14<4096)q14=4096;if(q14>16384)q14=16384;
      expected=(maximum*q14+8192)>>14;
      if(level!=expected)$fatal(1,"velocity %0d: %0d != %0d",velocity,level,expected);
      check_meter(id);
      $display("NOTE %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",id,key,timbre,volume,phase,rate,
         threshold-motion,first_adc-threshold,accepted-threshold,routed-threshold,first_pcm-threshold,
         first_pt-threshold,first_i2s-threshold,first_i2s16-threshold,velocity,level,peak);
      $fflush();
      stim=0;
      wait(top.key_pressed==0);repeat(4)begin @(negedge clk);while(!(top.adc_soc && addr==target_channel && top.keys.conversion==2))@(negedge clk);@(negedge clk);end
    end
  endtask
  // Cold session is a different boundary: keys are calibrated but scan.play
  // stays off until the player explicitly starts the amplifier. No acoustic
  // or analog settling time is supplied by the testbench.
  task cold_session;
    time ready_time;
    begin
      hold_open=0;key=14;timbre=4;volume=4588;repeat(6)@(negedge clk);rst=0;
      wait(top.key_calibrated);if(top.amp_ready || !top.PA_EN)$fatal(1,"PA must be shut down");
      @(negedge clk);while(!(top.adc_soc && addr==target_channel && top.keys.conversion==2))@(negedge clk);
      @(negedge clk);motion=$time;threshold=motion;stim=1;slope=0;
      first_adc=0;accepted=0;routed=0;first_pcm=0;first_pt=0;first_i2s=0;first_i2s16=0;
      words=0;peak=0;mark_rise=0;mark_fall=0;measure=1;hold_open=1;
      wait(top.amp_ready);ready_time=$time;
      wait(first_i2s16!=0 && first_pt!=0);measure=0;
      if(accepted<ready_time || ready_time-motion<2600000 || ready_time-motion>2622000 || first_i2s16<=first_i2s)
        $fatal(1,"cold arm/scan/I2S order");
      check_meter(18);
      $display("COLD %0d %0d %0d %0d %0d %0d %0d %0d",ready_time-motion,first_adc-motion,
        accepted-motion,routed-motion,first_pcm-motion,first_pt-motion,first_i2s-motion,first_i2s16-motion);
    end
  endtask
  integer n;
  initial begin
    if(!$value$plusargs("ADC_CYCLES=%d",conversion_clocks))conversion_clocks=20;
    force top.rst=rst;force top.clear_engine=flush;
    force top.adc_eoc=eoc;force top.adc_data=sample;force top.key_mode=2;force top.key_test=key;
    force top.key_wave=timbre;force top.key_level=volume;force top.key_recalibrate=0;
    force top.key_press=256;force top.key_release=128;force top.key_scale=64;
    force top.key_attack=attack;force top.key_decay=decay;
    force top.key_sustain=sustain;force top.key_tail=release_rate;
    force top.uart_amp_hold=hold_open;force top.gain_mode=1;force top.uart_panic=0;
    monitor_view=$test$plusargs("CHECK_METER");force top.monitor_demo=0;force top.monitor_open=monitor_view;force top.monitor_fade=0;
    force top.pt_bias=1577;force top.pt_mode=2;force top.pitch_offset=0;
    force top.control_live_flush=0;force top.loop_command_valid=0;force top.drum_hit_valid=0;force top.pc_pad_valid=0;
    force top.drum_mix=0;force top.drum_voices=0;force top.fx_cv=0;force top.fx_test_valid=0;force top.fx_monitor_mute=0;
    if($test$plusargs("COLD"))begin cold_session();$display("PASS cold session");$finish;end
    boot();
    run_note(0,14,4,4588,1,0,20);
    if($test$plusargs("METER_ONLY"))begin run_note(1,14,4,4588,0,0,20);$display("PASS meter pins");$finish;end
    if(!$test$plusargs("QUICK"))begin
      for(n=0;n<8;n=n+1)run_note(1+n,14,4,4588,n*3000,0,20);
      run_note(9,0,0,4588,1,0,32);run_note(10,31,0,4588,1,0,32);
      run_note(11,14,0,4588,5000,20,192);run_note(12,14,0,4588,5000,42,192);run_note(13,14,0,4588,5000,100,192);
      run_note(14,14,0,16384,5000,20,192);run_note(15,14,0,16384,5000,42,192);run_note(16,14,0,16384,5000,100,192);
      // Replay identical reset/clock/input alignment, without altering the serializer phase.
      key=14;timbre=4;volume=4588;@(negedge clk);boot();run_note(17,14,4,4588,1,0,20);
    end
    $display("PASS threshold to physical serial words; ADC model %0d clocks",conversion_clocks);$finish;
  end
  initial begin #300000000;$fatal(1,"simulation timeout");end
endmodule
