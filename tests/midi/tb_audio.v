`timescale 1ns/1ps
// Production MIDI -> live arbitration -> Loop -> router -> synth -> I2S.
// Idle peripheral controls are tied off; no replacement audio or MIDI models.
module tb_midi_audio;
    reg clk=0,rst=1,rx=1,hold_open=0,panic=0;
    always #10 clk=~clk;
    wire bclk,lrclk,sdata;
    synth_display_top top(.sys_clk(clk),.midi_rx(rx),.bt_rx(1'b1),.uart_rx(1'b1),
        .key0_n(1'b1),.key1_n(1'b1),.i2s_bclk(bclk),.i2s_lrclk(lrclk),.i2s_data(sdata));
    integer samples=0,peak=0,word_bits=0,value=0;
    reg [15:0] word=0;reg started=0;
    always @(posedge clk)if(rst)started<=0;else if(top.tick)begin started<=1;word_bits=0;end
    always @(posedge bclk)if(started && !rst)begin
        if(word_bits>=1 && word_bits<=16)word={word[14:0],sdata};
        if(word_bits==16)begin
            if(^word===1'bx || word!==top.tx.left_frame)$fatal(1,"I2S sample differs from final PCM");
            value=$signed(word);if(value<0)value=-value;
            if(value>peak)peak=value;
            samples=samples+1;
        end
        word_bits=word_bits+1;
    end
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task byte_out(input [7:0] data);
        integer i;
        begin
            @(negedge clk);#4;rx=0;clocks(1600);
            for(i=0;i<8;i=i+1)begin rx=data[i];clocks(1600);end
            rx=1;clocks(1600);
        end
    endtask
    initial begin
        force top.rst=rst;force top.key_mode=3;force top.key_wave=0;force top.key_level=4588;
        force top.key_attack=65535;force top.key_decay=65535;force top.key_sustain=65535;force top.key_tail=65535;
        force top.key_recalibrate=0;force top.midi_clear_counters=0;
        force top.uart_amp_hold=hold_open;force top.gain_mode=1;force top.uart_panic=panic;
        force top.monitor_demo=0;force top.monitor_open=0;force top.monitor_fade=0;
        force top.pt_bias=1577;force top.pt_mode=2;force top.pitch_offset=0;
        force top.control_live_flush=0;force top.loop_command_valid=0;force top.drum_hit_valid=0;force top.pc_pad_valid=0;
        force top.drum_mix=0;force top.drum_voices=0;force top.fx_cv=0;force top.fx_test_valid=0;force top.fx_monitor_mute=0;
        clocks(6);rst=0;hold_open=1;wait(top.amp_ready);clocks(20);
        byte_out(8'h90);byte_out(60);byte_out(100);clocks(60000);
        if(top.midi_held!=1 || top.held_count!=1 || peak<100)$fatal(1,"MIDI C4 did not reach output, held=%d router=%d peak=%d",top.midi_held,top.held_count,peak);
        byte_out(60);byte_out(0);clocks(12000);
        if(top.held_count!=0 || top.music_voices!=0 || top.pcm!==16'sd0)$fatal(1,"normal release without pedal left audio running");
        byte_out(60);byte_out(100);clocks(2000);
        byte_out(61);byte_out(80);clocks(25000);
        if(top.midi_held!=2 || top.held_count!=2 || top.midi_pressed!=32'h4000)$fatal(1,"chromatic input and white-key feedback");
        byte_out(8'hb0);byte_out(64);byte_out(127);
        byte_out(8'h90);byte_out(60);byte_out(0);byte_out(61);byte_out(0);clocks(5000);
        if(top.midi_held!=0 || top.held_count!=2)$fatal(1,"pedal did not hold the actual router voices");
        byte_out(8'hb0);byte_out(64);byte_out(0);clocks(12000);
        if(top.held_count!=0 || top.music_voices!=0 || top.pcm!==16'sd0)$fatal(1,"pedal release left audio running");
        if(top.overrun || top.clipped || top.limiter_overrun)$fatal(1,"audio engine unhealthy");
        $display("PASS full MIDI audio path, %0d decoded I2S samples, peak %0d, normal key release and pedal release both reach silence",samples,peak);
        $finish;
    end
    initial begin #30000000;$fatal(1,"audio integration timeout");end
endmodule
