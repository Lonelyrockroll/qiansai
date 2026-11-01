`timescale 1ns/1ps
// 32 independent DDS + ADSR voices. All state uses clk, never an audio clock.
module synth_engine_shared #(
    parameter VOICES = 32,
    parameter MIX_SHIFT = 5
)(
    input wire clk, input wire rst, input wire sample_tick,
    input wire cfg_valid, output wire cfg_ready,
    input wire [4:0] cfg_voice,
    input wire cfg_gate,cfg_restart, input wire [31:0] cfg_step,
    input wire [2:0] cfg_wave, input wire [15:0] cfg_level,
    input wire [15:0] cfg_attack, cfg_decay, cfg_sustain, cfg_release,
    output reg signed [15:0] pcm,
    output reg pcm_valid, output reg busy,
    output reg overrun, output reg clipped,
    output reg [31:0] voice_active_mask,output reg [5:0] active_voices,
    output reg signed [23:0] mix_sum
);
    localparam IDLE=0, LOAD=1, ROM_WAIT=2, ENV_MUL=3,
               LEVEL_MUL=4, ACCUM=5, OUTPUT=6, PIANO_ENV=9;
    localparam E_OFF=0, E_ATTACK=1, E_DECAY=2, E_SUSTAIN=3, E_RELEASE=4;
    reg [3:0] state;
    reg [4:0] voice;
    reg [5:0] active_work;reg [31:0] active_mask_work;reg active_pending;
    reg [31:0] phase [0:VOICES-1];
    reg [31:0] step [0:VOICES-1];
    reg gate [0:VOICES-1];
    reg [2:0] wave [0:VOICES-1];
    reg piano_retrigger[0:VOICES-1];
    wire piano_done,piano_active;
    wire signed [15:0] piano_sample;
    wire [15:0] piano_envelope;
    reg [15:0] level [0:VOICES-1];
    reg [15:0] env [0:VOICES-1];
    reg [2:0] env_state [0:VOICES-1];
    reg [15:0] attack [0:VOICES-1], decay [0:VOICES-1];
    reg [15:0] sustain [0:VOICES-1], release_step [0:VOICES-1];
    reg [15:0] env_next, env_work;
    reg [2:0] env_state_next;
    reg [11:0] rom_addr;
    wire signed [15:0] wave_sample;
    reg signed [32:0] env_product, level_product;
    reg signed [23:0] mix;
    wire signed [15:0] voice_sample = level_product[31:16];
    wire signed [23:0] scaled_mix = mix >>> MIX_SHIFT;
    integer i;
    assign cfg_ready = !rst && !busy && !sample_tick;
    waveform_rom tables(.clk(clk), .addr(rom_addr), .data(wave_sample));
    piano_modal_mixed #(.VOICES(VOICES)) piano(.clk(clk),.rst(rst),
        .start(state==LOAD && wave[voice]==4),.voice(voice),.gate(gate[voice]),
        .retrigger(piano_retrigger[voice]),.step(step[voice]),.level(level[voice]),
        .attack(attack[voice]),.release_step(release_step[voice]),
        .done(piano_done),.sample(piano_sample),.envelope(piano_envelope),.active(piano_active));

    always @* begin
        env_next = env[voice];
        env_state_next = env_state[voice];
        case (env_state[voice])
            E_ATTACK: begin
                if ({1'b0,env[voice]} + {1'b0,attack[voice]} >= 17'd65535) begin
                    env_next = 16'hffff;
                    env_state_next = E_DECAY;
                end else env_next = env[voice] + attack[voice];
            end
            E_DECAY: begin
                if (env[voice] <= sustain[voice] ||
                    env[voice] - sustain[voice] <= decay[voice]) begin
                    env_next = sustain[voice];
                    env_state_next = E_SUSTAIN;
                end else env_next = env[voice] - decay[voice];
            end
            E_SUSTAIN: env_next = sustain[voice];
            E_RELEASE: begin
                if (env[voice] <= release_step[voice]) begin
                    env_next = 0;
                    env_state_next = E_OFF;
                end else env_next = env[voice] - release_step[voice];
            end
            default: env_next = 0;
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; voice <= 0; busy <= 0; pcm <= 0; pcm_valid <= 0;
            overrun <= 0; clipped <= 0; mix <= 0; rom_addr <= 0;
            active_voices<=0; active_work<=0; active_mask_work<=0;active_pending<=0;voice_active_mask<=0;mix_sum<=0;
            env_work <= 0; env_product <= 0; level_product <= 0;
            for (i=0; i<VOICES; i=i+1) begin
                phase[i]<=0; step[i]<=0; gate[i]<=0; wave[i]<=0; level[i]<=0;
                env[i]<=0; env_state[i]<=E_OFF;
                piano_retrigger[i]<=0;
                attack[i]<=256; decay[i]<=16; sustain[i]<=32768; release_step[i]<=8;
            end
        end else begin
            pcm_valid <= 0;
            if (sample_tick && busy) overrun <= 1;
            // Commands are accepted only between frames: parameters cannot tear mid-mix.
            if (cfg_valid && cfg_ready && cfg_voice < VOICES) begin
                gate[cfg_voice] <= cfg_gate;
                // Highest table harmonic is 8: fundamental must stay below Fs/16.
                if(cfg_wave==4 && cfg_step>32'h0ff00000) step[cfg_voice]<=32'h0ff00000;
                else step[cfg_voice] <= (cfg_step > 32'h0fffffff) ? 32'h0fffffff : cfg_step;
                wave[cfg_voice] <= cfg_wave; level[cfg_voice] <= cfg_level;
                attack[cfg_voice] <= (cfg_attack == 0) ? 16'd1 : cfg_attack;
                decay[cfg_voice] <= (cfg_decay == 0) ? 16'd1 : cfg_decay;
                sustain[cfg_voice] <= cfg_sustain;
                release_step[cfg_voice] <= (cfg_release == 0) ? 16'd1 : cfg_release;
                if(cfg_gate && (cfg_restart || !gate[cfg_voice] || (cfg_wave==4 && wave[cfg_voice]!=4))) begin
                    env_state[cfg_voice]<=E_ATTACK;
                    if(cfg_restart)begin env[cfg_voice]<=0;phase[cfg_voice]<=0;end
                    if(cfg_wave==4) piano_retrigger[cfg_voice]<=1;
                end else if(!cfg_gate && gate[cfg_voice]) env_state[cfg_voice]<=E_RELEASE;
                if(cfg_wave!=4) piano_retrigger[cfg_voice]<=0;
            end
            case (state)
                IDLE: if (sample_tick) begin
                    busy<=1; voice<=0; mix<=0; active_work<=0;active_mask_work<=0;state<=LOAD;
                end
                LOAD: begin
                    rom_addr <= {wave[voice][1:0],phase[voice][31:22]};
                    if(wave[voice]==4) begin
                        piano_retrigger[voice]<=0;
                        state<=PIANO_ENV;
                    end else begin
                        env[voice] <= env_next; env_work <= env_next;
                        env_state[voice] <= env_state_next; state<=ROM_WAIT;
                        active_pending<=env_next != 0 && level[voice] != 0 && step[voice] != 0;
                        if (env_next != 0 && level[voice] != 0 && step[voice] != 0)begin
                            active_work <= active_work+1'b1;end
                    end
                    phase[voice] <= phase[voice] + step[voice];
                end
                PIANO_ENV:if(piano_done) begin
                    level_product<=$signed(piano_sample)*33'sd65536;
                    env[voice]<=piano_envelope;
                    env_state[voice]<=piano_active?(gate[voice]?E_DECAY:E_RELEASE):E_OFF;
                    active_pending<=piano_active;
                    if(piano_active)active_work<=active_work+1'b1;
                    state<=ACCUM;
                end
                ROM_WAIT: state<=ENV_MUL;
                ENV_MUL: begin
                    env_product <= wave_sample * $signed({1'b0,env_work});
                    state<=LEVEL_MUL;
                end
                LEVEL_MUL: begin
                    level_product <= $signed(env_product[31:16]) * $signed({1'b0,level[voice]});
                    state<=ACCUM;
                end
                ACCUM: begin
                    active_mask_work[voice]<=active_pending;
                    mix <= mix + {{8{voice_sample[15]}},voice_sample};
                    if (voice == VOICES-1) state<=OUTPUT;
                    else begin voice<=voice+1'b1; state<=LOAD; end
                end
                OUTPUT: begin
                    mix_sum<=mix;
                    if (scaled_mix > 32767) begin pcm<=32767; clipped<=1; end
                    else if (scaled_mix < -32768) begin pcm<=-32768; clipped<=1; end
                    else pcm<=scaled_mix[15:0];
                    pcm_valid<=1; busy<=0; active_voices<=active_work;voice_active_mask<=active_mask_work;state<=IDLE;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
