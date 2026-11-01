`timescale 1ns/1ps
// 50 MHz / 1024 = 48828.125 frames/s. No fractional clock-enable jitter.
// I2S: 32-bit slots, 16 significant bits, MSB one BCLK after LRCLK edge.
// PT8211: 16-bit slots, WS=0 right / WS=1 left, no I2S one-bit delay.
// PT_BIAS is only for an AC-coupled PT8211 path; standard I2S remains unbiased.
module audio_tx #(parameter integer PT_BIAS=0)(
    input wire clk, input wire rst,
    input wire signed [15:0] pcm_left, pcm_right,
    output wire sample_tick,
    output wire i2s_bclk, i2s_lrclk, output reg i2s_data,
    output wire hp_bck, hp_ws, output reg hp_din
);
    reg [9:0] count;
    reg [15:0] left_frame, right_frame;
    reg [15:0] pt_left_frame,pt_right_frame;
    wire signed [16:0] pt_left_sum=$signed(pcm_left)+PT_BIAS;
    wire signed [16:0] pt_right_sum=$signed(pcm_right)+PT_BIAS;
    wire [15:0] pt_left=(pt_left_sum>32767)?16'h7fff:(pt_left_sum< -32768)?16'h8000:pt_left_sum[15:0];
    wire [15:0] pt_right=(pt_right_sum>32767)?16'h7fff:(pt_right_sum< -32768)?16'h8000:pt_right_sum[15:0];
    wire [5:0] next_i2s_bit = count[9:4] + 6'd1;
    wire [4:0] next_pt_bit = count[9:5] + 5'd1;
    assign sample_tick = !rst && (count == 1023);
    assign i2s_bclk = count[3];
    assign i2s_lrclk = count[9];
    assign hp_bck = count[4];
    assign hp_ws = count[9];
    always @(posedge clk) begin
        if (rst) begin
            count<=0; left_frame<=0; right_frame<=0; pt_left_frame<=0;pt_right_frame<=0;i2s_data<=0; hp_din<=0;
        end else begin
            count <= count + 1'b1;
            if (count == 1023) begin
                left_frame<=pcm_left; right_frame<=pcm_right;
                pt_left_frame<=pt_left;pt_right_frame<=pt_right;
            end
            // Change data on BCLK falling edges, sample at the following rising edge.
            if (count[3:0] == 15) begin
                if (next_i2s_bit[4:0] >= 1 && next_i2s_bit[4:0] <= 16) begin
                    if (!next_i2s_bit[5]) i2s_data <= left_frame[16-next_i2s_bit[4:0]];
                    else i2s_data <= right_frame[16-next_i2s_bit[4:0]];
                end else i2s_data <= 0;
            end
            if (count[4:0] == 31) begin
                if (count == 1023) hp_din <= pt_right[15];
                else if (!next_pt_bit[4]) hp_din <= pt_right_frame[15-next_pt_bit[3:0]];
                else hp_din <= pt_left_frame[15-next_pt_bit[3:0]];
            end
        end
    end
endmodule
