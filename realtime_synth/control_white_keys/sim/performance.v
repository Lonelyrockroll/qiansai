`timescale 1ns/1ps
// Conversion-level ADC model only; no claim of modeling the physical SAR accuracy.
module keyboard_adc(input wire clk,rst,soc,output reg eoc=0,output reg [12:0] data=0);
    reg [12:0] stimulus=5400;
    reg stall=0;
    integer cycles=0;
    always @(posedge clk) begin
        if(rst) begin cycles<=0;eoc<=0;end
        else if(!stall) begin
            if(soc) begin cycles<=28;eoc<=0;end
            else if(cycles>0) begin cycles<=cycles-1;if(cycles==1) begin data<=stimulus;eoc<=1;end end
        end
    end
endmodule

module native_usb_bridge(input sys_clk,rst,command_ready,drum_mode,drum_hit_ready,
 output reg drum_hit_valid=0,output reg [3:0] drum_hit_pad=0,input [15:0] current_level,input [2:0] current_timbre,
 inout usb_dp,usb_dm,output reg command_valid=0,output reg disconnect_pulse=0,output wire connected,
 output reg [3:0] command_action=0,output reg [15:0] command_value=0,
 output [31:0] event_count,output [4:0] last_event,output [63:0] diagnostic);
 assign connected=1;assign event_count=0;assign last_event=0;assign diagnostic=0;
endmodule
module display_pll(input clkin,output lock,clkout0,clkout1);
 assign lock=1;assign clkout0=clkin;assign clkout1=clkin;
endmodule
module DVI_TX_Top(input I_rst_n,I_serial_clk,I_rgb_clk,I_rgb_vs,I_rgb_hs,I_rgb_de,
 input [7:0] I_rgb_r,I_rgb_g,I_rgb_b,output O_tmds_clk_p,O_tmds_clk_n,
 output [2:0] O_tmds_data_p,O_tmds_data_n);
 assign O_tmds_clk_p=I_rgb_clk;assign O_tmds_clk_n=~I_rgb_clk;
 assign O_tmds_data_p=0;assign O_tmds_data_n=7;
endmodule
module panel_renderer(input clk,rst,drum_mode,input [9:0] loop_actual_cs,loop_position_cs,input [2:0] loop_layers,loop_notice,input [1:0] loop_duration,input loop_playing,loop_recording,loop_pending,input [6:0] loop_progress,input [10:0] x,y,input hs,vs,de,
 input [3:0] focus,input [2:0] fx,timbre,input [6:0] volume,input [5:0] voices,input [1:0] mode,
 input calibrated,fault,muted,ready,playing,pattern,input [3:0] notice,
 input [31:0] pressed,input [7:0] peak,output [23:0] rgb,output hs_out,vs_out,de_out);
 assign rgb=0;assign hs_out=hs;assign vs_out=vs;assign de_out=de;
endmodule


module tb_performance;
reg clk=0;always #10 clk=~clk;wire pa;
synth_display_top dut(.sys_clk(clk),.bt_rx(1'b1),.uart_rx(1'b1),.key0_n(1'b1),.key1_n(1'b1),.PA_EN(pa));
defparam dut.controller.WATCHDOG_CYCLES=200000;
defparam dut.looper.FRAMES_2=32;defparam dut.looper.FRAMES_4=64;defparam dut.looper.FRAMES_8=128;
defparam dut.looper.PREP_FRAMES=4;defparam dut.looper.MIN_FRAMES=4;
reg pv=0,pg=0;reg [4:0] pid=0;reg [2:0] pw=4;reg [31:0] ps=23018935;
integer p,music_nonzero=0,drum_nonzero=0,pcm_nonzero=0,mark,layer2_held;reg check_skip;reg signed [25:0] expected_mix;
always @(posedge clk)begin
 check_skip=dut.rst || dut.clear_engine;expected_mix=($signed(dut.music_mix)*4)+$signed(dut.drum_mix);
 if(dut.tick)begin if(dut.music_mix!=0)music_nonzero=music_nonzero+1;if(dut.drum_mix!=0)drum_nonzero=drum_nonzero+1;if(dut.pcm!=0)pcm_nonzero=pcm_nonzero+1;end
 #1;if(!check_skip && dut.mix_total!==expected_mix)$fatal(1,"music and drums are not mixed simultaneously");
end
task command(input [3:0] a,input [15:0] v);begin
wait(dut.native_ready);@(negedge clk);dut.native_usb.command_action=a;dut.native_usb.command_value=v;dut.native_usb.command_valid=1;
@(negedge clk);dut.native_usb.command_valid=0;repeat(8)@(negedge clk);
end endtask
task hit(input [3:0] id);begin
@(negedge clk);dut.native_usb.drum_hit_valid=1;dut.native_usb.drum_hit_pad=id;
@(posedge clk);while(!dut.drum_hit_ready)@(posedge clk);@(negedge clk);dut.native_usb.drum_hit_valid=0;
end endtask
task note(input [4:0] id,input g,input [2:0] wave,input [31:0] step);begin
@(negedge clk);pid=id;pg=g;pw=wave;ps=step;pv=1;@(posedge clk);while(!dut.cfg_ready)@(posedge clk);@(negedge clk);pv=0;
end endtask
initial begin
force dut.cfg_valid=pv;force dut.cfg_voice=pid;force dut.cfg_gate=pg;force dut.cfg_wave=pw;force dut.cfg_step=ps;
force dut.cfg_level=16'd8000;force dut.cfg_attack=16'd5000;force dut.cfg_decay=16'd100;
force dut.cfg_sustain=16'd40000;force dut.cfg_release=16'd1000;
wait(!dut.rst);repeat(10)@(negedge clk);
command(5,1);wait(dut.loop_recording);
note(0,1,4,23018935);
wait(dut.loop_position==4);hit(0);
wait(dut.loop_position==8);note(1,1,4,29002472);
wait(dut.loop_position==16);note(0,0,4,23018935);
wait(dut.loop_position==20);hit(3);
wait(dut.loop_position==24);note(1,0,4,29002472);
wait(dut.loop_position==40);command(5,7);if(dut.drum_mode || !dut.uart_amp_hold || !dut.loop_recording || dut.ui_focus!=1)$fatal(1,"page switch interrupted recording");hit(5);
wait(dut.loop_position==95);command(2,0);if(dut.loop_actual_length!=96 || dut.loop_layers!=1 || dut.loop_counts[8:0]!=7)$fatal(1,"8 max manually ended at 6 equivalent: len=%0d layers=%0d count=%0d focus=%0d rec=%0d",dut.loop_actual_length,dut.loop_layers,dut.loop_counts[8:0],dut.ui_focus,dut.loop_recording);
note(2,1,4,34489421);repeat(8000)@(negedge clk);if(dut.live_held_count!=1)$fatal(1,"live held note");
command(5,1);wait(dut.loop_recording);wait(dut.loop_position==4);note(0,1,0,23018935);wait(dut.loop_position==8);hit(11);
wait(dut.loop_position==59);command(2,0);
if(dut.loop_actual_length!=60 || dut.loop_layers!=2 || dut.loop_counts[17:9]!=2)$fatal(1,"second finish must globally shorten all layers");
repeat(100000)@(negedge clk);wait(dut.loop_position==2);repeat(220)@(negedge clk);
layer2_held=0;for(p=0;p<32;p=p+1)if(dut.router.held_mask[p] && dut.router.owner[p]==2)layer2_held=layer2_held+1;
if(layer2_held || dut.live_held_count!=2)$fatal(1,"boundary release killed live notes or left held replay note");
if(dut.looper.memory[0][114:112]!=4 || dut.looper.memory[256][114:112]!=0)$fatal(1,"timbres not saved per event");
note(0,0,0,23018935);note(2,0,4,34489421);repeat(10000)@(negedge clk);
if(dut.live_held_count!=0)$fatal(1,"live note offs");
command(5,7);if(!dut.drum_mode || !dut.loop_playing || !dut.uart_amp_hold)$fatal(1,"return page interrupted audio");
command(5,2);if(dut.loop_layers!=1)$fatal(1,"undo mixed layer");
command(5,5);repeat(10000)@(negedge clk);if(dut.loop_layers || dut.loop_actual_length || !dut.uart_amp_hold)$fatal(1,"clear should preserve live session");
// Real scanner path: enable and calibrate, then record a 32-note press/release plus drums.
command(11,0);wait(dut.key_calibrated);if(dut.key_mode!=2 || !dut.uart_amp_hold)$fatal(1,"scan setup stopped drums");
command(5,1);wait(dut.loop_recording);dut.adc.stimulus=6000;
wait(dut.key_pressed==32'hffffffff);wait(dut.live_held_count==32);hit(9);dut.adc.stimulus=5400;
wait(dut.key_pressed==0);wait(dut.live_held_count==0);
if(!dut.loop_recording)$fatal(1,"scanner events missed recording window");
command(2,0);if(dut.loop_counts[8:0]!=65 || dut.loop_layers!=1)$fatal(1,"scanner on/off plus pad not captured %0d",dut.loop_counts[8:0]);
dut.adc.stall=1;wait(dut.key_fault);mark=dut.drum_hits;hit(0);repeat(10000)@(negedge clk);
if(!dut.uart_amp_hold || !dut.loop_playing || dut.drum_hits<=mark)$fatal(1,"ADC fault disabled drum/recorded playback");
if(music_nonzero==0 || drum_nonzero==0 || pcm_nonzero==0 || dut.overrun || dut.drum_overrun)$fatal(1,"mixed audio absent or missed deadlines");
command(3,0);repeat(120000)@(negedge clk);
if(!pa || dut.held_count || dut.pcm!=0)$fatal(1,"all mute leaves stuck notes");
$display("PASS simultaneous piano+drums, full musical snapshots, live/layer ownership, variable global length, page continuity, real 32-key scanner recording and ADC fault isolation");$finish;
end
initial begin #120000000;$fatal(1,"performance timeout");end
endmodule
