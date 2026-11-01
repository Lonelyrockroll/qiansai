`timescale 1ns/1ps
// KEY.1 selects; release KEY.0 activates; holding KEY.0 mutes once.
module panel_buttons #(parameter DEBOUNCE=500000,parameter HOLD=40000000)(
    input wire clk,rst,input wire next_n,apply_n,
    output reg valid,output reg [3:0] action);
    reg [1:0] next_sync=3,apply_sync=3;
    reg next_down,apply_down,held;
    reg [25:0] nd,ad,hold_count;
    always @(posedge clk) begin
        next_sync<={next_sync[0],next_n};apply_sync<={apply_sync[0],apply_n};
        valid<=0;
        if(rst) begin next_down<=0;apply_down<=0;held<=0;nd<=0;ad<=0;hold_count<=0;action<=0;end
        else begin
            if(next_down==!next_sync[1]) nd<=0;
            else if(nd==DEBOUNCE-1) begin
                next_down<=!next_sync[1];nd<=0;
                if(!next_sync[1]) begin valid<=1;action<=1;end
            end else nd<=nd+1'b1;
            if(apply_down==!apply_sync[1]) ad<=0;
            else if(ad==DEBOUNCE-1) begin
                apply_down<=!apply_sync[1];ad<=0;
                if(apply_sync[1] && !held) begin valid<=1;action<=2;end
                if(!apply_sync[1]) begin hold_count<=0;held<=0;end
            end else ad<=ad+1'b1;
            if(apply_down && !held) begin
                if(hold_count==HOLD-1) begin valid<=1;action<=3;held<=1;end
                else hold_count<=hold_count+1'b1;
            end
        end
    end
endmodule
