`timescale 1ns/1ps
module bt_uart_tx(input wire [15:0] divisor,
    input wire clk,input wire rst,input wire valid,input wire [7:0] data,
    output wire ready,output reg tx
);
    reg [15:0] timer;
    reg [3:0] bit_index;
    reg [9:0] shift;
    reg busy;
    assign ready=!busy;
    always @(posedge clk) begin
        if(rst) begin tx<=1;busy<=0;timer<=0;bit_index<=0;shift<=10'h3ff;end
        else if(!busy) begin
            if(valid) begin
                shift<={1'b1,data,1'b0};tx<=0;timer<=divisor-1;bit_index<=0;busy<=1;
            end
        end else if(timer!=0) timer<=timer-1'b1;
        else if(bit_index==9) begin busy<=0;tx<=1;end
        else begin
            shift<={1'b1,shift[9:1]};tx<=shift[1];timer<=divisor-1;bit_index<=bit_index+1'b1;
        end
    end
endmodule
