// HC-05 transmits 8N1. A capital U supplies nine equal intervals from start to stop.
// Measure its bit period once per configuration. Serial bytes are ignored until trained.
module bt_link(input wire clk,rst,rx,output wire tx,output reg locked,
 output reg [15:0] period,output wire received,output wire [7:0] data,
 input wire send,input wire [7:0] reply,output wire ready,output wire framing_error);
 reg meta,sync,prev;
 reg [15:0] elapsed,last;
 reg [3:0] run;
 always @(posedge clk)begin
  if(rst)begin meta<=1;sync<=1;prev<=1;locked<=0;period<=5208;elapsed<=0;last<=0;run<=0;end
  else begin
   meta<=rx;sync<=meta;prev<=sync;
   if(!locked)begin
    if(sync!=prev)begin
     elapsed<=1;
     if(elapsed>=350 && elapsed<=12000)begin
      last<=elapsed;
      if(last!=0 && elapsed>=last-(last>>5) && elapsed<=last+(last>>5))begin
       run<=run+1'b1;
       if(run>=7 && sync)begin period<=elapsed;locked<=1;end
      end else run<=0;
     end else begin last<=0;run<=0;end
    end else if(elapsed!=65535)elapsed<=elapsed+1'b1;
   end
  end
 end
 bt_uart_rx receiver(.clk(clk),.rst(rst || !locked),.divisor(period),.rx(rx),.data(data),.valid(received),.framing_error(framing_error));
 bt_uart_tx transmitter(.clk(clk),.rst(rst || !locked),.divisor(period),.tx(tx),.data(reply),.valid(send),.ready(ready));
endmodule
