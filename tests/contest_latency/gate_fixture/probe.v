`timescale 1ns/1ps
module probe(input wire clk,rst,recalibrate,play,ready,eoc,input wire[12:0] data,output wire [4:0] addr,physical,voice,output wire soc,cal,fault,valid,gate,
 output wire[31:0] mask,sensed,output wire[15:0] scans,level);
 keyboard_input keys(.clk(clk),.rst(rst),.recalibrate(recalibrate),.play(play),.mode(2'd2),.test_key(5'd14),.press_threshold(16'd256),.release_threshold(16'd128),.max_level(16'd4588),.velocity_scale(16'd64),.mux_addr(addr),.adc_soc(soc),.adc_eoc(eoc),.adc_data(data),.calibrated(cal),.fault(fault),.pressed_mask(mask),.scan_count(scans),.cfg_valid(valid),.cfg_ready(ready),.cfg_voice(voice),.cfg_gate(gate),.cfg_level(level),.sensed_mask(sensed),.scan_index(physical));
endmodule
