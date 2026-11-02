`timescale 1ns/1ps
// 32 Hall sensors -> ADG732 -> discard + average two ADC conversions.
// A key permanently owns its corresponding voice. Host and keys are exclusive sources.
module keyboard_input #(
    parameter SLOT_CYCLES=750, SETTLE_CYCLES=250, ADC_TIMEOUT=100,
    parameter STARTUP_CYCLES=500000
)(
    input wire clk,rst,recalibrate,play,
    input wire [1:0] mode, input wire [4:0] test_key,
    input wire [15:0] press_threshold,release_threshold,max_level,velocity_scale,
    output reg [4:0] mux_addr,output wire mux_cs_n,mux_wr_n,
    output reg adc_soc,input wire adc_eoc,input wire [12:0] adc_data,
    output reg calibrated,fault,output reg [31:0] pressed_mask,
    output reg [15:0] scan_count,last_raw,last_base,last_delta,last_velocity,
    output reg [4:0] last_key,
    output reg cfg_valid,input wire cfg_ready,
    output reg [4:0] cfg_voice,output reg cfg_gate,
    output reg [15:0] cfg_level,output reg [31:0] sensed_mask,output wire [4:0] scan_index,output wire [31:0] cfg_step
);
    localparam START=0,SELECT=1,SETTLE=2,REQUEST=3,CONVERT=4,AVERAGE=5,
        READ_KEY=6,DELTA=7,DECIDE=8,LEVEL=9,EMIT=10,END_SLOT=11,SCALE=12;
    reg [3:0] state;
    reg [19:0] timer;
    reg [15:0] slot_time;
    reg [4:0] key;
    reg [3:0] cal_round;
    reg [1:0] conversion;
    reg seen_low;
    reg [12:0] first_sample,sample,base_read,old_read,delta_work,speed_work;
    reg [16:0] sum_read;
    reg [31:0] level_product;
    // Q14 touch range is independent of the user's volume setting. Use a
    // separate cycle for volume scaling; quiet playing keeps its dynamics.
    wire [14:0] touch_q14 = level_product>=16384 ? 15'd16384 :
                             level_product<4096 ? 15'd4096 : level_product[14:0];
    reg [16:0] sums[0:31];
    reg [12:0] baseline[0:31],history0[0:31],history1[0:31],history2[0:31];
    reg [12:0] peak_speed[0:31];
    reg [15:0] held_level[0:31];
    wire [13:0] sample_sum={1'b0,first_sample}+{1'b0,adc_data};
    wire [16:0] calibration_sum=sum_read+{4'b0,sample};
    assign scan_index=key;
    wire [6:0] note;
    white_key_map pitch(.key(cfg_voice),.note(note));
    note_rom notes(.note(note),.step(cfg_step));
    assign mux_cs_n=(mode==0 || rst || fault);
    assign mux_wr_n=1'b0; // ADG732 transparent mode: /CS=0, /WR=0, EN tied low on PCB.
    function [4:0] channel(input [4:0] k);
        begin channel=k<16?k:(k<28?6'd43-{1'b0,k}:k);end
    endfunction
    integer i;
    always @(posedge clk) begin
        if(rst || recalibrate || mode==0) begin
            state<=START;timer<=0;slot_time<=0;key<=0;cal_round<=0;conversion<=0;
            adc_soc<=0;seen_low<=0;calibrated<=0;fault<=0;pressed_mask<=0;sensed_mask<=0;
            cfg_valid<=0;cfg_voice<=0;cfg_gate<=0;cfg_level<=0;mux_addr<=0;
            scan_count<=0;last_key<=0;last_raw<=0;last_base<=0;last_delta<=0;last_velocity<=0;
            first_sample<=0;sample<=0;base_read<=0;old_read<=0;sum_read<=0;
            delta_work<=0;speed_work<=0;level_product<=0;
            for(i=0;i<32;i=i+1) begin
                sums[i]<=0;baseline[i]<=0;history0[i]<=0;history1[i]<=0;history2[i]<=0;
                peak_speed[i]<=0;held_level[i]<=0;
            end
        end else begin
            adc_soc<=0;
            if(slot_time<16'hffff) slot_time<=slot_time+1'b1;
            if(!play || fault) begin pressed_mask<=0;cfg_valid<=0;end
            if(!fault) case(state)
                START: if(timer==STARTUP_CYCLES-1) begin timer<=0;state<=SELECT;end
                       else timer<=timer+1'b1;
                SELECT: begin
                    mux_addr<=channel(mode==1?test_key:key);timer<=0;slot_time<=0;state<=SETTLE;
                end
                SETTLE: if(timer==SETTLE_CYCLES-1) begin conversion<=0;state<=REQUEST;end
                        else timer<=timer+1'b1;
                REQUEST: begin adc_soc<=1;seen_low<=!adc_eoc;timer<=0;state<=CONVERT;end
                CONVERT: begin
                    if(!adc_eoc) seen_low<=1;
                    if(adc_eoc && seen_low) begin
                        if(conversion==0) begin conversion<=1;state<=REQUEST;end
                        else if(conversion==1) begin first_sample<=adc_data;conversion<=2;state<=REQUEST;end
                        else begin sample<=sample_sum[13:1];state<=READ_KEY;end
                    end else if(timer==ADC_TIMEOUT-1) begin fault<=1;cfg_valid<=0;pressed_mask<=0;end
                    else timer<=timer+1'b1;
                end
                READ_KEY: begin
                    base_read<=baseline[key];old_read<=history2[key];sum_read<=sums[key];state<=DELTA;
                end
                DELTA: begin
                    delta_work<=sample>=base_read?sample-base_read:base_read-sample;
                    state<=DECIDE;
                end
                DECIDE: begin
                    // Report the selected logical key in both scan and single-input modes.
                    if(key==test_key) begin last_key<=key;last_raw<={3'b0,sample};last_base<={3'b0,base_read};last_delta<={3'b0,delta_work};end
                    if(!calibrated) begin
                        sums[key]<=calibration_sum;
                        if(cal_round==15) baseline[key]<=calibration_sum[16:4];
                        state<=END_SLOT;
                    end else begin
                        // Keep the released/pressed decision even while the PA is muted.
                        if(mode==2 || key==test_key)begin
                            if(delta_work>=press_threshold)sensed_mask[key]<=1;
                            else if(delta_work<=release_threshold)sensed_mask[key]<=0;
                        end else sensed_mask[key]<=0;
                        history2[key]<=history1[key];history1[key]<=history0[key];history0[key]<=delta_work;
                        if(!play || (mode==1 && key!=test_key)) begin peak_speed[key]<=0;state<=END_SLOT;end
                        else if(!pressed_mask[key]) begin
                            if(delta_work>old_read && delta_work-old_read>peak_speed[key])
                                peak_speed[key]<=delta_work-old_read;
                            if(delta_work>=press_threshold) begin
                                speed_work<=(delta_work>old_read && delta_work-old_read>peak_speed[key])?
                                    delta_work-old_read:peak_speed[key];
                                cfg_voice<=key;cfg_gate<=1;state<=LEVEL;
                            end else begin
                                if(delta_work<=release_threshold) peak_speed[key]<=0;
                                state<=END_SLOT;
                            end
                        end else if(delta_work<=release_threshold) begin
                            cfg_voice<=key;cfg_gate<=0;cfg_level<=held_level[key];cfg_valid<=1;state<=EMIT;
                            pressed_mask[key]<=0;peak_speed[key]<=0;
                        end else state<=END_SLOT;
                    end
                end
                LEVEL: begin
                    // Relative Hall-motion velocity proxy, not calibrated force or mm/s.
                    level_product<=speed_work*velocity_scale;state<=AVERAGE;
                end
                AVERAGE: begin
                    level_product<=max_level*touch_q14;state<=SCALE;
                end
                SCALE: begin
                    cfg_level<=level_product[29:14]+level_product[13];
                    if(key==test_key) last_velocity<={3'b0,speed_work};
                    cfg_valid<=play;state<=EMIT;
                end
                EMIT: begin
                    if(!play) begin cfg_valid<=0;state<=END_SLOT;end
                    else if(cfg_valid && cfg_ready) begin
                        cfg_valid<=0;pressed_mask[key]<=cfg_gate;
                        if(cfg_gate) held_level[key]<=cfg_level;
                        state<=END_SLOT;
                    end
                end
                END_SLOT: if(slot_time>=SLOT_CYCLES-1) begin
                    if(key==31) begin
                        key<=0;scan_count<=scan_count+1'b1;
                        if(!calibrated) begin
                            if(cal_round==15) calibrated<=1;
                            else cal_round<=cal_round+1'b1;
                        end
                    end else key<=key+1'b1;
                    state<=SELECT;
                end
                default: state<=START;
            endcase
        end
    end
endmodule
