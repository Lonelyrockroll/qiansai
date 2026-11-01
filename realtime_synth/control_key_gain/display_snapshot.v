`timescale 1ns/1ps
// Bundled-data mailbox. Source data is held from request until next frame;
// acknowledgement passes two pixel FFs before the bus is captured.
module display_snapshot #(parameter WIDTH=128)(input wire sys_clk,sys_rst,pixel_clk,pixel_rst,
    input wire frame_start,input wire [WIDTH-1:0] source,output reg [WIDTH-1:0] snapshot);
    reg request=0,ack=0;reg [1:0] req_sync=0,ack_sync=0;
    reg [WIDTH-1:0] held=0;
    always @(posedge sys_clk) begin
        req_sync<={req_sync[0],request};
        if(sys_rst) begin ack<=0;held<=0;end
        else if(req_sync[1]!=ack) begin held<=source;ack<=req_sync[1];end
    end
    always @(posedge pixel_clk) begin
        ack_sync<={ack_sync[0],ack};
        if(pixel_rst) begin request<=0;snapshot<=0;end
        else begin
            if(frame_start && ack_sync[1]==request) request<=!request;
            if(ack_sync[1]==request) snapshot<=held;
        end
    end
endmodule
