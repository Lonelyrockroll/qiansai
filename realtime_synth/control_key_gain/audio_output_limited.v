`timescale 1ns/1ps
// Gain is applied to the full mix before 16-bit quantization.
// PA_EN is active HIGH for amplifier shutdown on NEO 31004.
module audio_output #(
    parameter WARMUP_FRAMES=128,
    parameter QUIET_FRAMES=256,
    parameter DRAIN_FRAMES=3,
    parameter GAIN_SLEW=16
)(
    input wire clk,rst,sample_tick,panic,wake_request,hold_open,
    input wire [5:0] active_voices,
    input wire signed [23:0] mix_sum,
    input wire [1:0] gain_mode,
    output wire signed [15:0] pcm,
    output reg pa_disable,output wire ready,output wire muting,
    output reg clear_engine,output reg clipped,
    output wire limited,limiter_overrun,output wire [16:0] limiter_gain,
    output wire [31:0] limited_frames
);
    localparam OFF=0,WARM=1,LIVE=2,FADE=3,DRAIN=4;
    reg [2:0] state;
    reg [15:0] count,quiet;
    reg forced;
    reg [12:0] gain_q;
    wire [12:0] target_gain = gain_mode==2 ? 13'd2048 : gain_mode==1 ? 13'd1024 : 13'd256;
    wire requested = wake_request || (active_voices!=0) || hold_open;
    reg signed [37:0] product;
    reg product_valid;
    wire signed [37:0] scaled = product >>> 13;
    wire signed [23:0] limiter_input=scaled>8388607?24'sh7fffff:scaled< -8388608?24'sh800000:scaled[23:0];
    wire signed [15:0] limited_pcm;
    pcm_peak_limiter limiter(.clk(clk),.rst(rst || clear_engine),.sample_valid(product_valid),.sample_in(limiter_input),
      .recover_enable(!forced && !panic),
      .pcm(limited_pcm),.valid(),.limited(limited),.overrun(limiter_overrun),.gain_q(limiter_gain),.limited_frames(limited_frames));
    assign pcm=(state==OFF || state==WARM)?16'sd0:limited_pcm;
    assign ready=(state==LIVE);
    assign muting=forced || clear_engine;
    always @(posedge clk) begin
        if(rst) begin
            state<=OFF;count<=0;quiet<=0;forced<=0;gain_q<=0;
            pa_disable<=1;clear_engine<=0;clipped<=0;product<=0;product_valid<=0;
        end else begin
            clear_engine<=0;
            product_valid<=sample_tick;
            if(sample_tick) product<=mix_sum*$signed({1'b0,gain_q});
            // Actual hard-overflow indication; ordinary peak reduction has its
            // own status and is not reported as digital clipping.
            if(product_valid && !forced && (scaled>8388607 || scaled< -8388608))clipped<=1;
            if(panic) begin
                forced<=1;state<=FADE;clipped<=0;
            end else if(state==OFF) begin
                gain_q<=0;
                if(requested && !clear_engine) begin
                    pa_disable<=0;count<=WARMUP_FRAMES;state<=WARM;
                end
            end else if(sample_tick) begin
                case(state)
                    WARM: begin
                        gain_q<=0;
                        if(count<=1) begin state<=LIVE;quiet<=0;end
                        else count<=count-1'b1;
                    end
                    LIVE: begin
                        if(gain_q<target_gain) begin
                            if(target_gain-gain_q<=GAIN_SLEW) gain_q<=target_gain;
                            else gain_q<=gain_q+GAIN_SLEW;
                        end else if(gain_q>target_gain) begin
                            if(gain_q-target_gain<=GAIN_SLEW) gain_q<=target_gain;
                            else gain_q<=gain_q-GAIN_SLEW;
                        end
                        if(requested) quiet<=0;
                        else if(quiet>=QUIET_FRAMES-1) begin
                            gain_q<=0;state<=DRAIN;count<=DRAIN_FRAMES;
                        end else quiet<=quiet+1'b1;
                    end
                    FADE: begin
                        if(gain_q<=GAIN_SLEW) begin gain_q<=0;state<=DRAIN;count<=DRAIN_FRAMES;end
                        else gain_q<=gain_q-GAIN_SLEW;
                    end
                    DRAIN: begin
                        gain_q<=0;
                        if(requested && !forced) begin state<=LIVE;quiet<=0;end
                        else if(count<=1) begin
                            if(hold_open) begin state<=LIVE;quiet<=0;end
                            else begin pa_disable<=1;state<=OFF;end
                            if(forced) clear_engine<=1;
                            forced<=0;
                        end else count<=count-1'b1;
                    end
                    default:begin state<=OFF;pa_disable<=1;gain_q<=0;end
                endcase
            end
        end
    end
endmodule
