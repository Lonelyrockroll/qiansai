`timescale 1ns/1ps
module uart_rx #(parameter CLK_HZ=50000000, parameter BAUD=115200)(
    input wire clk, input wire rst, input wire rx,
    output reg [7:0] data, output reg valid, output reg framing_error
);
    localparam DIV=(CLK_HZ+BAUD/2)/BAUD;
    reg rx_meta,rx_sync;
    reg [15:0] timer;
    reg [2:0] state,bit_index;
    reg [7:0] shift;
    always @(posedge clk) begin
        if(rst) begin rx_meta<=1;rx_sync<=1;end
        else begin rx_meta<=rx;rx_sync<=rx_meta;end
        if(rst) begin
            state<=0;timer<=0;bit_index<=0;shift<=0;data<=0;valid<=0;framing_error<=0;
        end else begin
            valid<=0;framing_error<=0;
            case(state)
                0: if(!rx_sync) begin timer<=DIV/2-1;state<=1;end
                1: if(timer!=0) timer<=timer-1'b1;
                   else if(rx_sync) state<=0;
                   else begin timer<=DIV-1;bit_index<=0;state<=2;end
                2: if(timer!=0) timer<=timer-1'b1;
                   else begin
                       shift[bit_index]<=rx_sync;timer<=DIV-1;
                       if(bit_index==7) state<=3;else bit_index<=bit_index+1'b1;
                   end
                3: if(timer!=0) timer<=timer-1'b1;
                   else if(rx_sync) begin data<=shift;valid<=1;state<=0;end
                   else begin framing_error<=1;state<=4;end
                4: if(rx_sync) state<=0;
                default:state<=0;
            endcase
        end
    end
endmodule
