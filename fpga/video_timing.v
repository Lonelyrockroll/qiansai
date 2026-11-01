`timescale 1ns/1ps
// Physical EDID captured 2026-10-26: MPI7005, 49 MHz, -H +V.
module video_timing(input wire clk,rst,output reg [10:0] x,y,
    output wire hs,vs,de,frame_start);
    always @(posedge clk) begin
        if(rst) begin x<=0;y<=0;end
        else if(x==1311) begin x<=0;y<=y==621?0:y+1'b1;end
        else x<=x+1'b1;
    end
    assign de=x<1024 && y<600;
    assign hs=!(x>=1029 && x<1042);
    assign vs=y>=602 && y<605;
    assign frame_start=x==0 && y==600;
endmodule
