`timescale 1ns/1ps
module tb_midi;
    parameter BIT_CYCLES=32;
    reg clk=0;always #10 clk=~clk;
    reg rst=1,rx=1,enabled=1,session=1,clear=0,clear_counters=0;
    reg stall=0;wire valid,ready,panic_request;wire [122:0] data;
    wire [31:0] bytes,messages,white_keys;
    wire [15:0] frame_errors,overflows,ignored,steals,pedals;
    wire [6:0] last_note,last_velocity;wire [3:0] last_channel;
    wire [5:0] held,sounding;wire [4:0] queued;
    midi_input #(.CLK_HZ(BIT_CYCLES*31250)) dut(
        .clk(clk),.rst(rst),.rx(rx),.enabled(enabled),.session(session),.clear(clear),.clear_counters(clear_counters),
        .timbre(3'd1),.level(16'd16384),.attack(16'd269),.decay(16'd6),.sustain(16'd40000),.release_step(16'd5),
        .event_valid(valid),.event_ready(ready),.event_data(data),.panic_request(panic_request),.rx_high(),
        .byte_count(bytes),.message_count(messages),.framing_errors(frame_errors),.overflows(overflows),
        .ignored_offs(ignored),.steals(steals),.last_note(last_note),.last_velocity(last_velocity),.last_channel(last_channel),
        .pedal_mask(pedals),.held_count(held),.sounding_count(sounding),.queued(queued),.white_keys(white_keys));
    wire router_ready,cfg_valid,cfg_gate,cfg_restart;
    wire [4:0] voice;wire [31:0] step;wire [2:0] wave;
    wire [15:0] level,attack,decay,sustain,release_step;
    wire [31:0] held_mask;reg [31:0] active=0;
    assign ready=router_ready && !stall;
    performance_router router(.clk(clk),.rst(rst),.clear(clear || panic_request),.cancel(1'b0),
        .event_valid(valid && !stall),.event_ready(router_ready),.event_data(data),.event_source(3'd0),
        .drum_valid(),.drum_ready(1'b1),.drum_pad(),.cfg_valid(cfg_valid),.cfg_ready(!stall),
        .cfg_voice(voice),.cfg_gate(cfg_gate),.cfg_restart(cfg_restart),.cfg_step(step),.cfg_wave(wave),
        .cfg_level(level),.cfg_attack(attack),.cfg_decay(decay),.cfg_sustain(sustain),.cfg_release(release_step),
        .voice_active_mask(active),.held_mask(held_mask),.held_count(),.live_held_count(),
        .events_applied(),.notes_applied(),.steals(),.ignored_offs());
    integer checks=0,ons=0,offs=0,kills=0,restarts=0,faults=0;
    integer last_level=0;reg [31:0] steps[0:31];
    always @(posedge clk)begin
        if(rst || clear || panic_request)active<=0;
        else if(cfg_valid && !stall)begin
            if(cfg_gate)begin
                ons=ons+1;active[voice]<=1;steps[voice]<=step;last_level=level;
                if(cfg_restart)restarts=restarts+1;
                if(wave>4)$fatal(1,"reserved waveform escaped the router");
            end else begin
                offs=offs+1;
                if(level==0)begin kills=kills+1;active[voice]<=0;end
                else if(wave!=1 || release_step!=5 || attack!=269)$fatal(1,"release profile lost");
            end
        end
        if(panic_request)faults=faults+1;
    end
    task check(input condition,input [639:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"%0s",message);end
    endtask
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task send_byte(input [7:0] value);
        integer bit_number;
        begin
            @(negedge clk);#3;rx=0;clocks(BIT_CYCLES);
            for(bit_number=0;bit_number<8;bit_number=bit_number+1)begin rx=value[bit_number];clocks(BIT_CYCLES);end
            rx=1;clocks(BIT_CYCLES);
        end
    endtask
    task note(input [7:0] status,input [6:0] pitch,velocity);
        begin send_byte(status);send_byte({1'b0,pitch});send_byte({1'b0,velocity});end
    endtask
    task cc(input [3:0] channel,input [6:0] number,value);
        begin send_byte({4'hb,channel});send_byte({1'b0,number});send_byte({1'b0,value});end
    endtask
    task settle;begin clocks(3500);check(queued==0 && dut.state==0,"event queue drained");end endtask
    task reset_notes;
        begin clear=1;clocks(4);clear=0;settle();end
    endtask
    integer before_on,before_off,before_kill,i;reg [15:0] ignored_before;
    initial begin
        clocks(6);rst=0;clocks(4);
        // Actual 8N1 serial line, with a real-time byte between note and velocity.
        send_byte(8'h90);send_byte(60);send_byte(8'hf8);send_byte(100);settle();
        check(ons==1 && held==1 && sounding==1 && white_keys==32'h4000,"C4 and realtime insertion");
        check(last_level==12928 && restarts==1,"velocity scaling and fresh envelope");
        send_byte(64);send_byte(90);send_byte(67);send_byte(80);settle();
        check(ons==3 && held==3 && white_keys==32'h54000,"running-status chord");
        send_byte(60);send_byte(0);settle();check(held==2 && offs==1,"velocity zero releases");
        // Repeated note-on must re-trigger once, then one note-off releases it.
        before_on=ons;before_off=offs;note(8'h90,64,110);settle();
        check(ons==before_on+1 && offs==before_off+1 && restarts==ons,"repeated note retriggers");
        note(8'h80,64,64);note(8'h80,64,0);settle();check(held==1 && ignored>0,"extra off is harmless");
        // Pedal ownership is per channel, and All Notes Off respects it.
        cc(0,64,127);note(8'h80,67,0);settle();
        check(held==0 && sounding==1 && pedals==1,"pedal holds released note");
        note(8'h91,67,100);note(8'h81,67,0);settle();check(sounding==1,"other channel pedal is independent");
        cc(0,64,0);settle();check(sounding==0,"pedal-up releases sustained voice");
        note(8'h90,60,70);cc(0,64,127);cc(0,123,0);settle();check(held==0 && sounding==1,"CC123 respects pedal");
        cc(0,121,0);settle();check(pedals==0 && sounding==0,"CC121 releases deferred notes");
        // CC120 must also silence a release tail, without touching another channel.
        note(8'h90,60,80);note(8'h91,62,80);note(8'h80,60,0);settle();
        before_kill=kills;cc(0,120,0);settle();check(kills>before_kill && held==1,"CC120 kills tails on its channel");
        cc(1,120,0);settle();check(held==0 && sounding==0,"CC120 clears selected channel");
        // Unsupported channel and system common/SysEx messages must not become notes.
        before_on=ons;send_byte(8'hc0);send_byte(4);send_byte(5);send_byte(8'he0);send_byte(0);send_byte(64);
        send_byte(8'hf0);send_byte(8'h7d);send_byte(8'hf8);send_byte(60);send_byte(100);send_byte(8'hf7);
        send_byte(60);send_byte(100);settle();check(ons==before_on,"unsupported data consumed without phantom notes");
        // Every MIDI pitch, including black keys and the two extremes, reaches DDS.
        reset_notes();note(8'h90,0,1);note(8'h90,61,127);note(8'h90,127,100);settle();
        check(held==3 && sounding==3 && last_note==127,"full 128-note identity range");
        send_byte(8'hff);settle();check(held==0 && sounding==0 && pedals==0,"system reset clears voices and pedal");
        reset_notes();note(8'h90,60,100);note(8'h80,60,0);settle();
        note(8'h90,61,100);settle();
        check(dut.assigned[1:0]==2'b11 && active[1:0]==2'b11,"new pitch uses a free voice while previous release tail remains");
        // 33 notes exercise deterministic stealing; old off cannot release replacement.
        reset_notes();for(i=36;i<69;i=i+1)note(8'h90,i,100);settle();
        check(held==32 && sounding==32 && steals>0,"full-polyphony replacement");
        ignored_before=ignored;note(8'h80,36,0);settle();check(held==32 && ignored==ignored_before+1,"stolen note off is ignored");
        for(i=37;i<69;i=i+1)note(8'h80,i,0);settle();check(held==0 && sounding==0 && held_mask==0,"all 32 releases reach router");
        // Session idle has no MIDI timeout. Backpressure must retain the payload.
        note(8'h90,60,100);settle();clocks(30000);check(held==1 && sounding==1,"long silence in MIDI stream preserves note");
        reset_notes();stall=1;for(i=0;i<8;i=i+1)note(8'h90,60+i,90);clocks(200);
        check(queued>0 && faults==0,"FIFO buffers bounded backpressure");stall=0;settle();check(held==8,"queued notes delivered");
        reset_notes();stall=1;for(i=0;i<24;i=i+1)note(8'h90,40+i,90);clocks(200);
        check(overflows>0 && faults>0,"overflow requests explicit panic");clear=1;clocks(4);clear=0;stall=0;settle();
        // A malformed stop bit never creates a note and raises one recoverable fault.
        before_on=ons;@(negedge clk);rx=0;clocks(BIT_CYCLES*11);rx=1;clocks(BIT_CYCLES*2);settle();
        check(frame_errors==1 && ons==before_on,"bad stop bit counted and suppressed");
        reset_notes();note(8'h90,60,100);settle();check(held==1,"recovery after framing error");
        session=0;settle();check(held==0 && sounding==0,"mute clears note ownership");
        before_on=ons;note(8'h90,62,100);session=1;settle();check(ons==before_on,"muted notes never replay on arm");
        clear_counters=1;clocks(2);clear_counters=0;clocks(2);check(bytes==0 && messages==0 && frame_errors==0 && overflows==0,"diagnostic counters clear");
        $display("PASS MIDI %0d checks, %0d note-ons, %0d offs, %0d immediate kills, bit clocks %0d",checks,ons,offs,kills,BIT_CYCLES);
        $finish;
    end
    initial begin #2000000000;$fatal(1,"MIDI test timeout");end
endmodule
