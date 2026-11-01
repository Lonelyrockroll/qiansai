`timescale 1ns/1ps
// Dedicated ADCV pins: NEO J11.2 = ADCV_P, J11.1 = ADCV_N (ground).
// Analog pins are hard-wired to the primitive, not ordinary digital top ports.
// UG298: CHEN=1 selects ADCV; result is offset binary, NOT a 0..8191 unipolar code.
module keyboard_adc(input wire clk,rst,soc,output wire eoc,output wire [12:0] data);
    ADC_SAR #(.BUF_EN(29'b0),.ADC_CLK_DIV(2'b00),.ADC_CLKDIV_EN(1'b0),
        .CLK_SRC_SEL(1'b1),.VREF_BUF_EN(1'b1),.COUNT_LEN(5'd20),
        .DAC_SAMPLE_END(5'd18),.DAC_SAMPLE_START(5'd13),
        .SH_SAMPLE_END(5'd11),.SH_SAMPLE_START(5'd1)) converter(
        .CLKI(clk),.CHEN(7'b0000001),.RSTN(!rst),.SOC(soc),.EOC(eoc),.ADCBIT(data),.CLKO(),
        .ADCMODE(1'b0),.VSENCTL(3'b0),.CLK(1'b0),.DRSTN(1'b0),.ADCREQI(1'b0),
        .MDRP_CLK(1'b0),.MDRP_WDATA(8'b0),.MDRP_A_INC(1'b0),.MDRP_OPCODE(2'b0),
        .ADCENI(1'b0),.ADCENO(),.ADCRDY(),.ADCVALUE(),.MDRP_RDATA(),.ADC1BIT(),.ADCCLKO());
endmodule
