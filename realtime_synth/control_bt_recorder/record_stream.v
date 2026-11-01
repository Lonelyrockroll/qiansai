// Binary recording extension to the JDY-31 text console. TREC frames are little endian.
// Payload: first signed-16 predictor + step index in header, then 128 low-first nibbles.
module record_stream #(parameter LEASE_TICKS=195312)(
 input wire clk,rst,audio_tick,input wire signed [15:0] pcm,input wire [15:0] period,
 input wire extension,input wire [7:0] operation,input wire ready,
 output reg send,output reg [7:0] out_byte,output wire owned);
 localparam DATA=1, FINISH=2, INFO=3;
 reg active,stopping,end_pending,info_pending;
 reg [1:0] reason;
 reg [17:0] lease;
 reg [31:0] sequence_number;
 reg [7:0] pos;
 reg bank;
 reg [15:0] seed_sample;
 reg [6:0] seed_index;
 reg [3:0] low_nibble;
 reg [7:0] payload[0:127] /* synthesis syn_ramstyle="registers" */;
 wire sample_valid,code_valid;wire signed [15:0] sample;
 wire [3:0] code;wire [6:0] step_index;
 wire seed=active && sample_valid && pos==0;
 wire encode=active && sample_valid && pos!=0;
 record_filter filter(.clk(clk),.rst(rst),.tick(audio_tick),.pcm(pcm),.valid(sample_valid),.sample(sample));
 ima_encoder encoder(.clk(clk),.rst(rst || !active),.seed(seed),.encode(encode),.sample(sample),
  .valid(code_valid),.code(code),.step_index(step_index));
 reg tx_busy,tx_bank;
 reg [1:0] kind;
 reg [31:0] frame_seq;
 reg [15:0] frame_seed,crc;
 reg [7:0] frame_index;
 reg [6:0] cursor;
 reg [3:0] crc_bits;
 wire [6:0] crc_pos=kind==DATA?78:14;
 reg [7:0] next_byte;
 always @*begin
  case(cursor)
   0:next_byte="T";1:next_byte="R";2:next_byte="E";3:next_byte="C";
   4:next_byte=1;5:next_byte=kind;
   6:next_byte=frame_seq[7:0];7:next_byte=frame_seq[15:8];8:next_byte=frame_seq[23:16];9:next_byte=frame_seq[31:24];
   10:next_byte=kind==DATA?129:0;11:next_byte=frame_seed[7:0];12:next_byte=frame_seed[15:8];13:next_byte=frame_index;
   default:if(cursor==crc_pos)next_byte=crc[7:0];
           else if(cursor==crc_pos+1'b1)next_byte=crc[15:8];
           else next_byte=payload[{tx_bank,cursor[5:0]-6'd14}];
  endcase
 end
 assign owned=active || tx_busy || end_pending || info_pending || send;
 task start_frame(input [1:0] packet_kind,input [15:0] predictor,input [7:0] ix);
 begin
  tx_busy<=1;kind<=packet_kind;frame_seq<=sequence_number;frame_seed<=predictor;
  frame_index<=ix;cursor<=0;crc<=16'hffff;crc_bits<=0;
 end endtask
 always @(posedge clk)begin
  if(rst)begin
   active<=0;stopping<=0;end_pending<=0;info_pending<=0;reason<=0;lease<=0;sequence_number<=0;
   pos<=0;bank<=0;seed_sample<=0;seed_index<=0;low_nibble<=0;
   send<=0;out_byte<=0;tx_busy<=0;tx_bank<=0;kind<=0;cursor<=0;crc<=16'hffff;crc_bits<=0;
   frame_seq<=0;frame_seed<=0;frame_index<=0;
  end else begin
   send<=0;
   if(active && audio_tick && !stopping)begin
    if(lease==LEASE_TICKS-1)begin stopping<=1;reason<=1;end
    else lease<=lease+1'b1;
   end
   if(extension)case(operation)
    "I":begin info_pending<=1;if(active)begin stopping<=1;reason<=0;end end
    "R":if(!owned)begin
      sequence_number<=0;pos<=0;bank<=0;lease<=0;stopping<=0;
      if(period>=350 && period<=460)begin active<=1;reason<=0;end
      else begin end_pending<=1;reason<=3;end
     end
    "K":if(active)lease<=0;
    "S":if(active)begin stopping<=1;reason<=0;end
    default:;
   endcase
   if(seed)begin seed_sample<=sample;seed_index<=step_index;pos<=1;end
   if(active && code_valid)begin
    if(pos[0])low_nibble<=code;
    else payload[{bank,pos[6:1]-6'd1}]<={code,low_nibble};
    if(pos!=128)pos<=pos+1'b1;
    else begin
     pos<=0;
     if(tx_busy)begin active<=0;reason<=2;end_pending<=1;end
     else begin
      start_frame(DATA,seed_sample,{1'b0,seed_index});tx_bank<=bank;
      bank<=~bank;sequence_number<=sequence_number+1'b1;
      if(stopping)begin active<=0;end_pending<=1;end
     end
    end
   end
   if(!tx_busy && !active)begin
    if(end_pending)begin start_frame(FINISH,0,{6'd0,reason});end_pending<=0;end
    else if(info_pending)begin start_frame(INFO,0,0);info_pending<=0;end
   end
   if(crc_bits!=0)begin
    crc<=(crc<<1)^(crc[15]?16'h1021:16'h0);crc_bits<=crc_bits-1'b1;
   end
   if(tx_busy && ready && !send && crc_bits==0)begin
    out_byte<=next_byte;send<=1;
    if(cursor>=4 && cursor<crc_pos)begin crc<=crc^{next_byte,8'h0};crc_bits<=8;end
    if(cursor==crc_pos+1'b1)tx_busy<=0;else cursor<=cursor+1'b1;
   end
  end
 end
endmodule
