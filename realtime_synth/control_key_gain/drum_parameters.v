`timescale 1ns/1ps
module drum_parameters(input wire [3:0] pad,output reg [31:0] initial_step,body_step,second_step,
 output reg [15:0] tone_decay,noise_decay,output reg [2:0] fast_shift,slow_shift,output reg [3:0] pitch_shift);
always @*begin
 initial_step=0;body_step=0;second_step=0;tone_decay=0;noise_decay=0;fast_shift=0;slow_shift=0;pitch_shift=8;
 case(pad)
4'd0:begin initial_step=32'd16712577;body_step=32'd4573968;second_step=32'd9323859;tone_decay=16'd65528;noise_decay=16'd65368;fast_shift=2;slow_shift=5;pitch_shift=8;end
4'd1:begin initial_step=32'd18031991;body_step=32'd15393163;second_step=32'd29554873;tone_decay=16'd65518;noise_decay=16'd65524;fast_shift=1;slow_shift=4;pitch_shift=9;end
4'd2:begin initial_step=32'd0;body_step=32'd0;second_step=32'd0;tone_decay=16'd0;noise_decay=16'd65523;fast_shift=2;slow_shift=4;pitch_shift=8;end
4'd3:begin initial_step=32'd326335051;body_step=32'd326335051;second_step=32'd467072539;tone_decay=16'd65497;noise_decay=16'd65506;fast_shift=0;slow_shift=2;pitch_shift=8;end
4'd4:begin initial_step=32'd326335051;body_step=32'd326335051;second_step=32'd467072539;tone_decay=16'd65530;noise_decay=16'd65531;fast_shift=0;slow_shift=2;pitch_shift=8;end
4'd5:begin initial_step=32'd13194140;body_step=32'd7476679;second_step=32'd12050647;tone_decay=16'd65530;noise_decay=16'd65482;fast_shift=2;slow_shift=5;pitch_shift=10;end
4'd6:begin initial_step=32'd19351405;body_step=32'd11434921;second_step=32'd18207913;tone_decay=16'd65528;noise_decay=16'd65475;fast_shift=2;slow_shift=5;pitch_shift=10;end
4'd7:begin initial_step=32'd27707693;body_step=32'd17592186;second_step=32'd27883615;tone_decay=16'd65526;noise_decay=16'd65461;fast_shift=2;slow_shift=5;pitch_shift=9;end
4'd8:begin initial_step=32'd279803719;body_step=32'd279803719;second_step=32'd464345751;tone_decay=16'd65533;noise_decay=16'd65533;fast_shift=0;slow_shift=3;pitch_shift=8;end
4'd9:begin initial_step=32'd204333241;body_step=32'd204333241;second_step=32'd299682889;tone_decay=16'd65534;noise_decay=16'd65522;fast_shift=1;slow_shift=3;pitch_shift=8;end
4'd10:begin initial_step=32'd152172409;body_step=32'd152172409;second_step=32'd231337246;tone_decay=16'd65488;noise_decay=16'd65344;fast_shift=0;slow_shift=2;pitch_shift=8;end
4'd11:begin initial_step=32'd49522004;body_step=32'd49522004;second_step=32'd74326986;tone_decay=16'd65528;noise_decay=16'd0;fast_shift=0;slow_shift=2;pitch_shift=8;end
default:;endcase
end
endmodule
