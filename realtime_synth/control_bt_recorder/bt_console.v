// One printable command per transaction. Ignore line endings and training bytes.
// The host sends its next command after the LF response; an early command is counted.
module bt_console(input wire clk,rst,bt_rx,output wire bt_tx,input wire audio_tick,input wire signed [15:0] pcm,output wire locked,
 output wire [15:0] period,output reg [15:0] commands,dropped,
 output wire request,output reg [7:0] command,input wire accept,input wire settled,
 input wire [6:0] volume,input wire [2:0] timbre,fx,input wire [7:0] lamps,
 output wire trace_valid,output wire [7:0] trace_data);
 wire received,tx_ready,frame_error;wire [7:0] data;
 reg send;reg [7:0] reply;
 wire stream_send,stream_owned;wire [7:0] stream_byte;
 reg prefix;
 wire extension=received && prefix;
 bt_link link(.clk(clk),.rst(rst),.rx(bt_rx),.tx(bt_tx),.locked(locked),.period(period),.received(received),
  .data(data),.send(stream_send || send),.reply(stream_send?stream_byte:reply),.ready(tx_ready),.framing_error(frame_error));
 assign trace_valid=send;assign trace_data=reply;
 localparam IDLE=0,REQUEST=1,APPLY=2,SETTLE=3,REPLY=4;
 reg [2:0] state;reg [4:0] index;reg [6:0] v;reg [2:0] t,f;reg [7:0] lights;reg invalid;
 record_stream recorder(.clk(clk),.rst(rst),.audio_tick(audio_tick),.pcm(pcm),.period(period),
  .extension(extension && state==IDLE),.operation(data),.ready(tx_ready && !send),
  .send(stream_send),.out_byte(stream_byte),.owned(stream_owned));
 assign request=state==REQUEST;
 function [7:0] hexchar(input [3:0] n);begin hexchar=n<10?"0"+n:"A"+(n-10);end endfunction
 function [7:0] message(input [4:0] i);
  begin case(i)
   0:message=invalid?"E":"O";1:message=invalid?"R":"K";2,6,9,12,16:message=" ";
   3:message="V";4:message="0"+v/10;5:message="0"+v%10;7:message="T";8:message="0"+t;
   10:message="F";11:message="0"+f;13:message="L";14:message=hexchar(lights[7:4]);15:message=hexchar(lights[3:0]);
   17:message="B";18:message=hexchar(period[15:12]);19:message=hexchar(period[11:8]);
   20:message=hexchar(period[7:4]);21:message=hexchar(period[3:0]);22:message=13;default:message=10;
  endcase end
 endfunction
 always @(posedge clk)begin
  if(rst)begin prefix<=0;state<=IDLE;index<=0;command<=0;commands<=0;dropped<=0;send<=0;reply<=0;invalid<=0;v<=0;t<=0;f<=0;lights<=0;end
  else begin
   send<=0;
   if(received)prefix<=data=="~";
   if(frame_error)dropped<=dropped+1'b1;
   if(received && !prefix && !stream_owned && data!="~" && data!="U" && data!=13 && data!=10 && data!=" ")begin
    if(state!=IDLE)dropped<=dropped+1'b1;
    else begin command<=data;commands<=commands+1'b1;
     case(data)
      "?","L","+","-","T","F","M":begin invalid<=0;state<=REQUEST;end
      default:begin invalid<=1;state<=SETTLE;end
     endcase
    end
   end
   case(state)
    REQUEST:if(accept)state<=APPLY;
    APPLY:state<=SETTLE;
    SETTLE:if(settled)begin v<=volume;t<=timbre;f<=fx;lights<=lamps;index<=0;state<=REPLY;end
    REPLY:if(tx_ready && !send)begin send<=1;reply<=message(index);
     if(index==23)state<=IDLE;else index<=index+1'b1;
    end
   endcase
  end
 end
endmodule
