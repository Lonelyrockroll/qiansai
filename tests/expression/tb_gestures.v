`timescale 1ns/1ps
module tb_gestures;
 reg clk=0,rst=1,conn=1,valid=0,ready=0;
 always #5 clk=~clk;
 reg [4:0] length;reg [127:0] data;
 wire ev,fault;wire [4:0] id;
 native_keypad_drums #(.CLK_HZ(1000)) parser(.clk(clk),.rst(rst),.connected(conn),.mode_change(1'b0),
    .report_valid(valid),.report_length(length),.report_data(data),.event_valid(ev),.event_ready(ready),.event_id(id),.fault(fault));
 task report(input [127:0] bits,input [4:0] len);
  begin @(negedge clk);valid=1;data=bits;length=len;@(negedge clk);valid=0;end
 endtask
 task mouse(input [2:0] buttons,input [7:0] wheel);
  begin report({88'd0,wheel,16'd0,5'd0,buttons,8'd2},5);end
 endtask
 task key(input ctrl,input [7:0] usage);
  begin report({96'd0,usage,8'd0,7'd0,ctrl,8'd1},9);end
 endtask
 task get(input [4:0] expected);
  begin @(negedge clk);if(!ev || id!==expected)$fatal(1,"expected event %d, got %d valid %b",expected,id,ev);
   ready=1;@(negedge clk);ready=0;end
 endtask
 reg [132:0] physical[0:25];
 integer i;
 task empty;
  begin @(negedge clk);if(ev || fault)$fatal(1,"spurious event/fault %d",id);end
 endtask
 initial begin
  repeat(4) @(negedge clk);rst=0;
  mouse(1,0);empty();mouse(1,2);mouse(1,-1);mouse(0,0);get(20);get(20);get(21);empty();
  mouse(2,0);key(1,0);mouse(2,2);mouse(2,-1);key(0,0);mouse(0,0);get(18);get(18);get(19);empty();
  key(1,0);mouse(0,-2);key(0,0);mouse(0,1);mouse(1,0);mouse(0,0);
  get(13);get(13);get(15);get(17);empty(); // plain B immediately after A, then execute
  key(1,0);key(0,0);mouse(0,1);get(12);mouse(0,-1);get(16);empty();
  mouse(1,0);mouse(0,1);mouse(0,0);mouse(0,0);get(20);empty();
  mouse(2,0);empty();mouse(0,0);get(14);empty();
  key(0,8'h68);key(0,8'h68);get(11);key(0,0);empty();
  mouse(1,0);@(negedge clk);conn=0;@(negedge clk);conn=1;mouse(0,0);empty();
  $readmemh("j18_gestures.hex",physical);
  for(i=0;i<26;i=i+1)report(physical[i][127:0],physical[i][132:128]);
  get(20);get(20);get(21);get(18);get(18);get(19);get(14);get(17);empty();
  $display("PASS encoder chords, tap-on-release, ordering, Ctrl tail, K12 and disconnect");$finish;
 end
endmodule
