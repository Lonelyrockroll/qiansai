`timescale 1ns/1ps
// Four pipelined lanes evaluate 16 independent modes per struck note.
// Twelve stiff-string partials + four slower, detuned companion modes.
module piano_modal_mixed #(parameter VOICES=32)(
    input wire clk,rst,start,
    input wire [4:0] voice,
    input wire gate,retrigger,
    input wire [31:0] step,
    input wire [15:0] level,attack,release_step,
    output reg done,output reg signed [15:0] sample,
    output reg [15:0] envelope,output reg active
);
    localparam IDLE=0,READ=1,CALC=2,ENV=3,MUL=4,ADD=5,SCALE=6,LEVEL=7,DONE=8;
    reg [3:0] state;
    reg [1:0] group;
    reg [4:0] current_voice;
    reg [31:0] current_step;
    reg [15:0] current_level,gain;
    reg restart;
    reg [2:0] band;
    reg [15:0] gains[0:VOICES-1];
    // A short, filtered hammer transient; exactly silent after 385 samples.
    reg [23:0] noise_state[0:VOICES-1],hammer_amps[0:VOICES-1];
    reg signed [15:0] noise_filter[0:VOICES-1];
    reg [8:0] hammer_age[0:VOICES-1];
    reg signed [15:0] hammer_sample;
    reg [23:0] hammer_amp;
    reg signed [32:0] hammer_product;
    wire [23:0] seed=retrigger?((step[23:0]^24'h6d2b79^{19'd0,voice})|24'd1):noise_state[voice];
    wire signed [17:0] noise_raw=$signed(seed[23:8]);
    wire signed [17:0] previous_noise=retrigger?18'sd0:$signed(noise_filter[voice]);
    wire signed [17:0] filtered_noise=previous_noise+((noise_raw-previous_noise)>>>2);
    wire [23:0] hammer_loss=(hammer_amps[voice]>>6)==0?24'd1:(hammer_amps[voice]>>6);
    wire [23:0] hammer_decayed=hammer_amps[voice]>hammer_loss?hammer_amps[voice]-hammer_loss:24'd0;
    wire [15:0] hammer_initial=16'd1800+(level>>6);
    wire [6:0] index={current_voice,group};
    wire [73:0] c0,c1,c2,c3;
    piano_modal_tables coefficients(.band(band),.group(group),.c0(c0),.c1(c1),.c2(c2),.c3(c3));
    wire [73:0] coeff[0:3];
    assign coeff[0]=c0;assign coeff[1]=c1;assign coeff[2]=c2;assign coeff[3]=c3;
    wire signed [15:0] sine[0:3];
    wire [11:0] address[0:3];
    wire signed [32:0] products[0:3];
    wire [3:0] alive;
    genvar lane;
    generate for(lane=0;lane<4;lane=lane+1) begin: lanes
        reg [31:0] phases[0:VOICES*4-1];
        reg [23:0] amplitudes[0:VOICES*4-1];
        reg [31:0] phase_read,phase_next;
        reg [24:0] loss_q;
        reg [23:0] amp_read,amp_next;
        reg [73:0] params;
        reg [51:0] step_product;
        reg [31:0] velocity_product;
        reg signed [32:0] product;
        wire [19:0] ratio=params[73:54];
        wire [15:0] soft_gain=params[53:38],hard_gain=params[37:22];
        wire [4:0] shift1=params[21:17],shift2=params[16:12];
        wire [24:0] raw_loss={1'b0,(amp_read>>shift1)}+{1'b0,(amp_read>>shift2)};
        wire [24:0] loss=raw_loss==0?25'd1:raw_loss;
        wire [16:0] initial_amp={1'b0,soft_gain}+{1'b0,velocity_product[31:16]};
        wire [23:0] decayed=amp_read>loss_q ? amp_read-loss_q : 24'd0;
        assign address[lane]=phase_read[31:20];
        assign products[lane]=product;
        assign alive[lane]=amp_next[23:8]!=0;
        integer j;
        always @(posedge clk) begin
            if(rst) begin
                phase_read<=0;phase_next<=0;loss_q<=0;amp_read<=0;amp_next<=0;params<=0;step_product<=0;velocity_product<=0;product<=0;
                for(j=0;j<VOICES*4;j=j+1) begin phases[j]<=0;amplitudes[j]<=0;end
            end else case(state)
                READ:begin
                    params<=coeff[lane];amp_read<=amplitudes[index];
                    phase_read<=restart?{coeff[lane][11:0],20'd0}:phases[index];
                end
                CALC:begin
                    loss_q<=loss;
                    step_product<=current_step*ratio;
                    velocity_product<=(hard_gain-soft_gain)*current_level;
                end
                ENV:begin
                    // Suppress every mode above 7/16 Fs, retaining Nyquist margin.
                    if(current_step==0 || step_product[51:16]>=36'h070000000 || gain==0)
                        amp_next<=0;
                    else if(restart) amp_next<={initial_amp[15:0],8'd0};
                    else amp_next<=decayed[23:8]==0?24'd0:decayed;
                end
                MUL:begin
                    phase_next<=phase_read+step_product[47:16];
                    amplitudes[index]<=amp_next;
                    product<=sine[lane]*$signed({1'b0,amp_next[23:8]});
                end
                ADD:phases[index]<=phase_next;
            endcase
        end
    end endgenerate
    piano_sine4 sine_table(.clk(clk),.a0(address[0]),.a1(address[1]),.a2(address[2]),.a3(address[3]),
        .y0(sine[0]),.y1(sine[1]),.y2(sine[2]),.y3(sine[3]));
    wire signed [31:0] pair_sum=($signed(products[0])>>>15)+($signed(products[1])>>>15)
                                             +($signed(products[2])>>>15)+($signed(products[3])>>>15);
    reg signed [31:0] sum;
    reg signed [48:0] gain_product,level_product;
    wire signed [32:0] output_value=level_product>>>16;
    reg any_alive;
    integer i;
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;group<=0;current_voice<=0;current_step<=0;current_level<=0;gain<=0;restart<=0;band<=0;
            done<=0;sample<=0;envelope<=0;active<=0;sum<=0;gain_product<=0;level_product<=0;any_alive<=0;
            hammer_sample<=0;hammer_amp<=0;hammer_product<=0;
            for(i=0;i<VOICES;i=i+1) begin gains[i]<=0;noise_state[i]<=1;noise_filter[i]<=0;hammer_amps[i]<=0;hammer_age[i]<=384;end
        end else begin
            done<=0;
            case(state)
                IDLE:if(start) begin
                    current_voice<=voice;current_step<=step;current_level<=level;restart<=retrigger;group<=0;sum<=0;any_alive<=0;
                    if(retrigger || hammer_age[voice]<384) begin
                        noise_state[voice]<={seed[22:0],seed[23]^seed[22]^seed[21]^seed[16]};
                        noise_filter[voice]<=filtered_noise[15:0];hammer_sample<=filtered_noise[15:0];
                        hammer_amps[voice]<=retrigger?{hammer_initial,8'd0}:hammer_decayed;
                        hammer_amp<=retrigger?{hammer_initial,8'd0}:hammer_decayed;
                        hammer_age[voice]<=retrigger?9'd0:hammer_age[voice]+1'b1;
                    end else begin hammer_amp<=0;hammer_amps[voice]<=0;hammer_sample<=0;noise_filter[voice]<=0;end
                    if(step<11506199) band<=0;
                    else if(step<23012398) band<=1;
                    else if(step<46024797) band<=2;
                    else if(step<92049593) band<=3;
                    else if(step<184099186) band<=4;else band<=5;
                    if(gate) begin
                        if(retrigger) gain<=attack;
                        else if({1'b0,gains[voice]}+{1'b0,attack}>=65535) gain<=65535;
                        else gain<=gains[voice]+attack;
                    end else gain<=gains[voice]>release_step?gains[voice]-release_step:16'd0;
                    state<=READ;
                end
                READ:begin
                    hammer_product<=current_step==0?33'sd0:hammer_sample*$signed({1'b0,hammer_amp[23:8]});
                    state<=CALC;
                end
                CALC:state<=ENV;
                ENV:state<=MUL;
                MUL:state<=ADD;
                ADD:begin
                    sum<=sum+pair_sum;any_alive<=any_alive || (|alive);
                    if(group==3) state<=SCALE;
                    else begin group<=group+1'b1;state<=READ;end
                end
                SCALE:begin gain_product<=(sum+($signed(hammer_product)>>>15))*$signed({1'b0,gain});state<=LEVEL;end
                LEVEL:begin level_product<=($signed(gain_product)>>>16)*$signed({1'b0,current_level});state<=DONE;end
                DONE:begin
                    if(output_value>32767) sample<=32767;
                    else if(output_value< -32768) sample<=-32768;else sample<=output_value[15:0];
                    gains[current_voice]<=gain;
                    envelope<=any_alive?gain:16'd0;
                    active<=any_alive && gain!=0 && current_level!=0 && current_step!=0;
                    done<=1;state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
