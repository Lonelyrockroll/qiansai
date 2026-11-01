`timescale 1ns/1ps
module tb_score_controller;
 reg clk=0,rst=1;always #5 clk=~clk;
 wire uart_out;
 reg inject_valid=0;reg [7:0] inject_data=0;
 reg score_valid=1,score_show_requested=1,score_visible=1,score_loading=0,score_reserved=1,score_ui_ready=1;
 reg [15:0] score_page_index=16'h1234,score_page_count=16'h5678;
 reg [31:0] score_received_compressed=32'h01020304,score_decoded_bytes=32'd65536;
 reg capture_busy=0,capture_ready=1;
 reg [15:0] capture_id=16'h2468,capture_count=64,capture_capacity=32768;
 wire [14:0] capture_read_address;reg [15:0] capture_read_data=0;
 wire capture_command_valid,capture_command_arm,score_ui_valid;wire [1:0] score_ui_action;
 reg ui_valid=0;reg [3:0] ui_action=0;reg [15:0] ui_value=0;wire ui_ready,amp_hold;
 wire guide_ui_valid;wire [3:0] guide_ui_action;
 `include "controller_instance.vh"
 always @(posedge clk)capture_read_data<={1'b0,capture_read_address}^16'ha55a;
 integer accepted=0,armed=0;reg [1:0] last_action=0;
 always @(posedge clk)if(!rst)begin
   if(score_ui_valid && score_ui_ready)begin accepted=accepted+1;last_action=score_ui_action;end
   if(capture_command_valid && capture_command_arm)armed=armed+1;
 end
 reg [7:0] wire_bytes[0:8191];integer wire_count=0,bitpos;reg [7:0] decoded;
 // Independent 8N1 decoder sees only the physical uart_out pin.
 initial forever begin
   @(negedge uart_out);repeat(15)@(posedge clk);#1;
   decoded=0;
   for(bitpos=0;bitpos<8;bitpos=bitpos+1)begin decoded[bitpos]=uart_out;repeat(10)@(posedge clk);#1;end
   if(uart_out!==1'b1)$fatal(1,"UART stop bit");
   wire_bytes[wire_count]=decoded;wire_count=wire_count+1;
 end
 reg [7:0] payload[0:19],request[0:27],reply[0:27];integer seqno=0,base=0,i,j,failures=0,checks=0,before_count;reg [7:0] xor_byte;
 task check(input condition,input [511:0] detail);begin
   checks=checks+1;if(condition!==1'b1)begin failures=failures+1;$display("FAIL %0s",detail);end
 end endtask
 task clear_payload;begin for(i=0;i<20;i=i+1)payload[i]=0;end endtask
 task send_byte(input [7:0] b);begin
   @(negedge clk);inject_data=b;inject_valid=1;@(negedge clk);inject_valid=0;
 end endtask
 task start_request(input [7:0] op);begin
   wait(dut.state==0 && dut.rx_index==0);base=wire_count;seqno=seqno+1;
   request[0]=8'ha5;request[1]=8'h5a;request[2]=1;request[3]=seqno;request[4]=op;request[5]=20;
   for(i=0;i<20;i=i+1)request[i+6]=payload[i];xor_byte=0;
   for(i=2;i<26;i=i+1)xor_byte=xor_byte^request[i];request[26]=xor_byte;request[27]=13;
   for(j=0;j<28;j=j+1)send_byte(request[j]);
 end endtask
 task finish_reply(input [7:0] op,input [7:0] expected);begin
   wait(wire_count>=base+28);for(i=0;i<28;i=i+1)reply[i]=wire_bytes[base+i];
   check(reply[0]==8'h5a && reply[1]==8'ha5 && reply[2]==1 && reply[3]==seqno && reply[4]==8'h80 && reply[5]==20 && reply[27]==13,"UART reply envelope");
   xor_byte=0;for(i=2;i<26;i=i+1)xor_byte=xor_byte^reply[i];check(reply[26]===xor_byte,"UART reply XOR");
   check(reply[6]===expected,"reply status");check(reply[24]==31 && reply[25]==op,"firmware/opcode unchanged");
   wait(dut.state==0);repeat(2)@(posedge clk);
 end endtask
 task transaction(input [7:0] op,input [7:0] expected);begin start_request(op);finish_reply(op,expected);end endtask
 function [15:0] word_at(input integer pos);begin word_at={reply[pos+1],reply[pos]};end endfunction
 task read_payload(input [15:0] tag,input [15:0] start,input [7:0] count);begin
   clear_payload();payload[0]=tag[7:0];payload[1]=tag[15:8];payload[2]=start[7:0];payload[3]=start[15:8];payload[4]=count;
 end endtask
 task pulse_ui(input [3:0] action);begin
   wait(ui_ready);@(negedge clk);ui_action=action;ui_valid=1;@(negedge clk);ui_valid=0;
 end endtask
 initial begin
   force dut.rx_valid=inject_valid;force dut.rx_data=inject_data;force dut.rx_error=1'b0;
   repeat(5)@(posedge clk);@(negedge clk);rst=0;
   clear_payload();transaction(32,0);
   check(reply[7]==8'h1b && word_at(8)==16'h1234 && word_at(10)==16'h5678,"score flags and page metadata");
   check({reply[15],reply[14],reply[13],reply[12]}==32'h01020304 && {reply[19],reply[18],reply[17],reply[16]}==65536,"score uint32 telemetry");
   check({reply[23],reply[22],reply[21],reply[20]}==0,"reserved score reply bytes");
   clear_payload();transaction(31,0);
   check(reply[7]==11 && reply[8]==2 && word_at(9)==84 && word_at(11)==12 && word_at(13)==125 && word_at(15)==2400,"old guide status retained");
   check({reply[20],reply[19],reply[18],reply[17]}==32'h4000,"old guide note mask");
   clear_payload();payload[0]=1;before_count=accepted;transaction(32,0);check(accepted==before_count+1 && last_action==0,"PC hide");
   clear_payload();payload[0]=2;before_count=accepted;transaction(32,0);check(accepted==before_count+1 && last_action==1,"PC show");
   clear_payload();payload[0]=3;before_count=accepted;transaction(32,0);check(accepted==before_count+1 && last_action==2,"PC clear");
   clear_payload();payload[0]=4;transaction(32,3);
   score_valid=0;payload[0]=2;before_count=accepted;transaction(32,4);check(accepted==before_count,"show unavailable rejected");score_valid=1;
   score_ui_ready=0;capture_busy=1;payload[0]=1;transaction(32,4);clear_payload();transaction(32,0);score_ui_ready=1;capture_busy=0;
   read_payload(score_page_index,10,6);transaction(33,0);
   check(word_at(7)==score_page_index && word_at(9)==10 && reply[11]==6,"page-tagged six-word header");
   for(i=0;i<6;i=i+1)check(word_at(12+i*2)==((10+i)^16'ha55a),"page data from synchronous capture port A");
   read_payload(score_page_index,32762,6);transaction(33,0);check(word_at(22)==(32767^16'ha55a),"last legal RAM address");
   read_payload(score_page_index,0,0);transaction(33,3);
   read_payload(score_page_index,0,7);transaction(33,3);
   read_payload(score_page_index,32768,1);transaction(33,3);
   read_payload(score_page_index,32767,2);transaction(33,3);
   read_payload(score_page_index+1,0,1);transaction(33,4);
   score_loading=1;read_payload(score_page_index,0,1);transaction(33,4);score_loading=0;
   score_valid=0;transaction(33,4);score_valid=1;
   read_payload(score_page_index,20,6);start_request(33);
   wait(dut.state==9 && dut.read_index==2);@(negedge clk);score_page_index=score_page_index+1;
   finish_reply(33,4);check(reply[11]==0,"mid-read page change discards words");
   read_payload(score_page_index,20,1);start_request(33);
   wait(dut.state==9);@(posedge clk);#1;score_page_index=score_page_index+1;score_valid=0;
   finish_reply(33,4);check(reply[11]==0,"page invalidation at BUILD discards words");score_valid=1;
   read_payload(capture_id,3,6);transaction(23,0);check(reply[11]==6 && word_at(12)==(3^16'ha55a),"ordinary PCM23 retained");
   read_payload(capture_id+1,3,6);transaction(23,4);capture_ready=0;read_payload(capture_id,3,6);transaction(23,4);capture_ready=1;
   clear_payload();payload[0]=1;payload[2]=8;before_count=armed;transaction(21,4);check(armed==before_count,"score-reserved blocks PCM arm");
   score_reserved=0;capture_busy=1;transaction(21,4);check(armed==before_count,"capture-busy blocks PCM arm");capture_busy=0;
   transaction(21,0);check(armed==before_count+1,"ordinary PCM arm retained");
   start_request(21);score_reserved=1;finish_reply(21,4);
   clear_payload();payload[0]=1;before_count=accepted;start_request(32);score_ui_ready=0;
   repeat(20)@(posedge clk);check(score_ui_valid && score_ui_action==0 && accepted==before_count,"PC score command held under ready backpressure");
   score_ui_ready=1;finish_reply(32,0);check(accepted==before_count+1,"held PC command accepted exactly once");
   before_count=accepted;score_ui_ready=0;score_visible=1;pulse_ui(2);
   repeat(20)@(posedge clk);check(accepted==before_count && !amp_hold && dut.ui_pending,"local exit waits without executing synth menu");
   @(negedge clk);score_ui_ready=1;wait(score_ui_valid);@(negedge clk);score_ui_ready=0;
   repeat(20)@(posedge clk);check(score_ui_valid && !amp_hold && accepted==before_count,"local exit valid survives same-cycle BT arbitration");
   @(negedge clk);score_ui_ready=1;repeat(3)@(posedge clk);#1;
   check(accepted==before_count+1 && last_action==0 && !amp_hold,"short B exits sheet only");
   score_visible=0;pulse_ui(2);repeat(4)@(posedge clk);#1;check(amp_hold,"short B normal synth action retained");
   pulse_ui(2);repeat(4)@(posedge clk);#1;check(!amp_hold,"normal short B stops performance");
   score_visible=1;score_ui_ready=0;pulse_ui(2);repeat(4)@(posedge clk);#1;
   check(dut.ui_pending && !amp_hold,"exit queued while sheet visible");
   score_visible=0;repeat(4)@(posedge clk);#1;
   check(!amp_hold,"queued sheet exit cannot become menu execute if Bluetooth hides sheet");
   if(failures!=0)$fatal(1,"FAIL controller %0d of %0d checks",failures,checks);
   $display("PASS score controller %0d checks, %0d UART replies: op32/33 bounds/tag races, PCM23/arm, local exit and backpressure",checks,seqno);$finish;
 end
 initial begin #20000000;$fatal(1,"controller timeout");end
endmodule
