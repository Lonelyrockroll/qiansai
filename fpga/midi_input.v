`timescale 1ns/1ps
// DIN MIDI receiver and 32 logical-note owners for the existing live/Loop path.
// Off events use reserved wave 5 (stored release profile) or 7 (immediate silence).
module midi_input #(
    parameter CLK_HZ=50000000, BAUD=31250, FIFO_BITS=4
)(
    input wire clk,rst,rx,enabled,session,clear,clear_counters,
    input wire [2:0] timbre,
    input wire [15:0] level,attack,decay,sustain,release_step,
    output wire event_valid,input wire event_ready,output wire [122:0] event_data,
    output wire panic_request,output wire rx_high,
    output reg [31:0] byte_count,message_count,
    output reg [15:0] framing_errors,overflows,ignored_offs,steals,
    output reg [6:0] last_note,last_velocity,output reg [3:0] last_channel,
    output reg [15:0] pedal_mask,output reg [5:0] held_count,sounding_count,
    output wire [FIFO_BITS:0] queued,
    output reg [31:0] white_keys
);
    localparam NOTE_OFF=0, NOTE_ON=1, PEDAL=2, ALL_NOTES=3,
               ALL_SOUND=4, RESET_CONTROLLERS=5, RESET_SYSTEM=6;
    localparam IDLE=0, SEARCH=1, CHOOSE=2, SEND_OFF=3, SEND_ON=4, CONTROL_SCAN=5;
    localparam DEPTH=1<<FIFO_BITS;
    wire [7:0] rx_data;
    wire rx_valid,rx_error;
    uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) receiver(
        .clk(clk),.rst(rst),.rx(rx),.data(rx_data),.valid(rx_valid),.framing_error(rx_error));
    reg [1:0] line_sync;
    always @(posedge clk)if(rst)line_sync<=3;else line_sync<={line_sync[0],rx};
    assign rx_high=line_sync[1];
    wire decoded_valid;
    wire [2:0] decoded_kind;
    wire [3:0] decoded_channel;
    wire [6:0] decoded_a,decoded_b;
    midi_decoder decoder(.clk(clk),.rst(rst),.byte_valid(rx_valid),.framing_error(rx_error),.data(rx_data),
        .event_valid(decoded_valid),.event_kind(decoded_kind),.event_channel(decoded_channel),
        .event_a(decoded_a),.event_b(decoded_b));

    reg [20:0] fifo[0:DEPTH-1];
    reg [FIFO_BITS-1:0] read_pointer,write_pointer;
    reg [FIFO_BITS:0] count;
    reg overflow_pulse;
    reg [2:0] state;
    wire accept_mode=enabled && session;
    wire pop=accept_mode && !clear && state==IDLE && count!=0;
    wire push=decoded_valid && accept_mode;
    wire overflow=push && count==DEPTH && !pop;
    wire [20:0] head=fifo[read_pointer];
    assign queued=count;
    assign panic_request=accept_mode && (rx_error || overflow_pulse);
    always @(posedge clk)begin
        overflow_pulse<=0;
        if(rst || !accept_mode || clear || rx_error || overflow)begin
            read_pointer<=0;write_pointer<=0;count<=0;
            if(!rst && overflow)overflow_pulse<=1;
        end else begin
            if(push)begin
                fifo[write_pointer]<={decoded_kind,decoded_channel,decoded_a,decoded_b};
                write_pointer<=write_pointer+1'b1;
            end
            if(pop)read_pointer<=read_pointer+1'b1;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:;
            endcase
        end
    end

    reg [31:0] assigned,key_down,sounding;
    reg [6:0] notes[0:31];reg [3:0] channels[0:31];
    reg [2:0] request_kind;
    reg [3:0] request_channel;
    reg [6:0] request_note,request_velocity;
    reg [5:0] scan;
    reg matched,free_found,vacant_found;
    reg [4:0] match_slot,free_slot,vacant_slot,replace_cursor,slot;
    reg retrigger,hard_off,control_off;
    reg [23:0] velocity_product;
    reg [2:0] note_timbre;
    reg [15:0] note_attack,note_decay,note_sustain,note_release;
    wire [31:0] note_step;
    note_rom frequencies(.note(request_note),.step(note_step));
    wire [4:0] search_slot=scan[4:0]+replace_cursor;
    // Keep distinct logical IDs for new pitches while unused slots remain,
    // allowing the audio router to finish released voices naturally.
    wire [4:0] selected=matched?match_slot:(vacant_found?vacant_slot:(free_found?free_slot:replace_cursor));
    wire [114:0] on_profile={note_timbre,note_step,velocity_product[22:7],note_attack,note_decay,note_sustain,note_release};
    assign event_valid=(state==SEND_ON || state==SEND_OFF) && accept_mode && !clear && !panic_request;
    assign event_data=state==SEND_ON?{2'b01,1'b1,slot,on_profile}:
        {2'b01,1'b0,slot,(hard_off?3'd7:3'd5),112'd0};

    // Rebuild display aggregates over 32 clocks, away from the audio handshake.
    reg [4:0] visual_index;
    reg [31:0] visual_keys;
    reg [5:0] visual_held,visual_sounding;
    function [31:0] white_bit(input [6:0] note);
        begin
            case(note)
                36:white_bit=32'h1;38:white_bit=32'h2;40:white_bit=32'h4;41:white_bit=32'h8;
                43:white_bit=32'h10;45:white_bit=32'h20;47:white_bit=32'h40;48:white_bit=32'h80;
                50:white_bit=32'h100;52:white_bit=32'h200;53:white_bit=32'h400;55:white_bit=32'h800;
                57:white_bit=32'h1000;59:white_bit=32'h2000;60:white_bit=32'h4000;62:white_bit=32'h8000;
                64:white_bit=32'h10000;65:white_bit=32'h20000;67:white_bit=32'h40000;69:white_bit=32'h80000;
                71:white_bit=32'h100000;72:white_bit=32'h200000;74:white_bit=32'h400000;76:white_bit=32'h800000;
                77:white_bit=32'h1000000;79:white_bit=32'h2000000;81:white_bit=32'h4000000;83:white_bit=32'h8000000;
                84:white_bit=32'h10000000;86:white_bit=32'h20000000;88:white_bit=32'h40000000;89:white_bit=32'h80000000;
                default:white_bit=0;
            endcase
        end
    endfunction
    wire [31:0] visual_bit=key_down[visual_index]?white_bit(notes[visual_index]):32'd0;
    always @(posedge clk)begin
        if(rst || clear || !accept_mode || panic_request)begin
            visual_index<=0;visual_keys<=0;visual_held<=0;visual_sounding<=0;
            white_keys<=0;held_count<=0;sounding_count<=0;
        end else begin
            visual_index<=visual_index+1'b1;
            if(visual_index==31)begin
                white_keys<=visual_keys|visual_bit;
                held_count<=visual_held+key_down[visual_index];
                sounding_count<=visual_sounding+sounding[visual_index];
                visual_keys<=0;visual_held<=0;visual_sounding<=0;
            end else begin
                visual_keys<=visual_keys|visual_bit;
                visual_held<=visual_held+key_down[visual_index];
                visual_sounding<=visual_sounding+sounding[visual_index];
            end
        end
    end
    always @(posedge clk)begin
        if(rst || clear_counters)begin
            byte_count<=0;message_count<=0;framing_errors<=0;overflows<=0;
        end else begin
            if(rx_valid)byte_count<=byte_count+1'b1;
            if(decoded_valid)message_count<=message_count+1'b1;
            if(rx_error)framing_errors<=framing_errors+1'b1;
            if(overflow)overflows<=overflows+1'b1;
        end
    end
    integer i;
    always @(posedge clk)begin
        if(rst || clear_counters)begin ignored_offs<=0;steals<=0;end
        if(rst || clear || !accept_mode || panic_request)begin
            state<=IDLE;assigned<=0;key_down<=0;sounding<=0;pedal_mask<=0;
            scan<=0;matched<=0;free_found<=0;vacant_found<=0;match_slot<=0;free_slot<=0;vacant_slot<=0;replace_cursor<=0;slot<=0;
            request_kind<=0;request_channel<=0;request_note<=0;request_velocity<=0;
            retrigger<=0;hard_off<=0;control_off<=0;velocity_product<=0;
            note_timbre<=0;note_attack<=1;note_decay<=1;note_sustain<=0;note_release<=1;
            if(rst)begin
                last_note<=0;last_velocity<=0;last_channel<=0;
                for(i=0;i<32;i=i+1)begin notes[i]<=0;channels[i]<=0;end
            end
        end else case(state)
            IDLE:if(pop)begin
                request_kind<=head[20:18];request_channel<=head[17:14];
                request_note<=head[13:7];request_velocity<=head[6:0];
                scan<=0;matched<=0;free_found<=0;vacant_found<=0;control_off<=0;retrigger<=0;hard_off<=0;
                if(head[20:18]==NOTE_ON || head[20:18]==NOTE_OFF)begin
                    last_note<=head[13:7];last_channel<=head[17:14];
                    if(head[20:18]==NOTE_ON)last_velocity<=head[6:0];
                    velocity_product<=level*({1'b0,head[6:0]}+8'd1);
                    note_timbre<=timbre;note_attack<=attack;note_decay<=decay;note_sustain<=sustain;note_release<=release_step;
                    state<=SEARCH;
                end else if(head[20:18]==PEDAL && head[6])pedal_mask<=pedal_mask | (16'h1 << head[17:14]);
                else begin
                    if(head[20:18]==RESET_SYSTEM)pedal_mask<=0;
                    else if(head[20:18]==PEDAL || head[20:18]==RESET_CONTROLLERS)pedal_mask<=pedal_mask & ~(16'h1 << head[17:14]);
                    state<=CONTROL_SCAN;
                end
            end
            SEARCH:begin
                if(assigned[search_slot] && notes[search_slot]==request_note && channels[search_slot]==request_channel)
                    begin matched<=1;match_slot<=search_slot;end
                if(!vacant_found && !assigned[search_slot])begin vacant_found<=1;vacant_slot<=search_slot;end
                if(!free_found && !sounding[search_slot] && !key_down[search_slot])begin free_found<=1;free_slot<=search_slot;end
                if(scan==31)state<=CHOOSE;else scan<=scan+1'b1;
            end
            CHOOSE:begin
                if(request_kind==NOTE_ON)begin
                    slot<=selected;replace_cursor<=selected+1'b1;
                    if(sounding[selected])begin
                        retrigger<=1;hard_off<=!matched;state<=SEND_OFF;
                        if(!matched && !clear_counters)steals<=steals+1'b1;
                    end else state<=SEND_ON;
                end else if(matched && key_down[match_slot])begin
                    key_down<=key_down & ~(32'h1 << match_slot);
                    if(!pedal_mask[request_channel] && sounding[match_slot])begin slot<=match_slot;state<=SEND_OFF;end
                    else state<=IDLE;
                end else begin if(!clear_counters)ignored_offs<=ignored_offs+1'b1;state<=IDLE;end
            end
            SEND_ON:if(event_ready)begin
                assigned<=assigned | (32'h1 << slot);key_down<=key_down | (32'h1 << slot);sounding<=sounding | (32'h1 << slot);
                notes[slot]<=request_note;channels[slot]<=request_channel;state<=IDLE;
            end
            SEND_OFF:if(event_ready)begin
                sounding<=sounding & ~(32'h1 << slot);
                if(hard_off)begin assigned<=assigned & ~(32'h1 << slot);key_down<=key_down & ~(32'h1 << slot);end
                if(retrigger)begin retrigger<=0;state<=SEND_ON;end
                else if(control_off)begin scan<=scan+1'b1;state<=CONTROL_SCAN;end
                else state<=IDLE;
            end
            CONTROL_SCAN:begin
                if(scan==32)state<=IDLE;
                else if(assigned[scan[4:0]] && (request_kind==RESET_SYSTEM || channels[scan[4:0]]==request_channel))begin
                    if(request_kind==ALL_NOTES || request_kind==ALL_SOUND || request_kind==RESET_SYSTEM)key_down<=key_down & ~(32'h1 << scan[4:0]);
                    if(request_kind==ALL_SOUND || request_kind==RESET_SYSTEM ||
                       (sounding[scan[4:0]] && ((request_kind==ALL_NOTES && !pedal_mask[request_channel]) ||
                         ((request_kind==PEDAL || request_kind==RESET_CONTROLLERS) && !key_down[scan[4:0]]))))begin
                        slot<=scan[4:0];hard_off<=request_kind==ALL_SOUND || request_kind==RESET_SYSTEM;
                        control_off<=1;state<=SEND_OFF;
                    end else scan<=scan+1'b1;
                end else scan<=scan+1'b1;
            end
            default:state<=IDLE;
        endcase
    end
endmodule
