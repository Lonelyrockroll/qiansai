`timescale 1ns/1ps
// MIDI 1.0 channel stream. Real-time bytes never consume a data position.
module midi_decoder(
    input wire clk, rst, byte_valid, framing_error,
    input wire [7:0] data,
    output reg event_valid,
    output reg [2:0] event_kind,
    output reg [3:0] event_channel,
    output reg [6:0] event_a, event_b
);
    localparam NOTE_OFF=0, NOTE_ON=1, PEDAL=2, ALL_NOTES=3,
               ALL_SOUND=4, RESET_CONTROLLERS=5, RESET_SYSTEM=6;
    reg [7:0] running_status;
    reg first_received;
    reg [6:0] first_data;
    always @(posedge clk) begin
        if(rst) begin
            running_status<=0;first_received<=0;first_data<=0;
            event_valid<=0;event_kind<=0;event_channel<=0;event_a<=0;event_b<=0;
        end else begin
            event_valid<=0;
            if(framing_error)begin running_status<=0;first_received<=0;end
            else if(byte_valid)begin
                if(data>=8'hf8)begin
                    if(data==8'hff)begin
                        running_status<=0;first_received<=0;
                        event_valid<=1;event_kind<=RESET_SYSTEM;event_channel<=0;event_a<=0;event_b<=0;
                    end
                end else if(data[7])begin
                    first_received<=0;
                    running_status<=data<8'hf0 ? data : 8'd0;
                end else if(running_status!=0)begin
                    if(running_status[7:4]==4'hc || running_status[7:4]==4'hd)
                        first_received<=0; // Consume one-byte channel messages.
                    else if(!first_received)begin first_data<=data[6:0];first_received<=1;end
                    else begin
                        first_received<=0;event_channel<=running_status[3:0];
                        event_a<=first_data;event_b<=data[6:0];
                        case(running_status[7:4])
                            4'h8:begin event_valid<=1;event_kind<=NOTE_OFF;end
                            4'h9:begin event_valid<=1;event_kind<=data==0?NOTE_OFF:NOTE_ON;end
                            4'hb:case(first_data)
                                64:begin event_valid<=1;event_kind<=PEDAL;end
                                120:begin event_valid<=1;event_kind<=ALL_SOUND;end
                                121:begin event_valid<=1;event_kind<=RESET_CONTROLLERS;end
                                123,124,125,126,127:begin event_valid<=1;event_kind<=ALL_NOTES;end
                                default:;
                            endcase
                            default:;
                        endcase
                    end
                end
            end
        end
    end
endmodule
