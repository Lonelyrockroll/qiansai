`timescale 1ns/1ps
module tb_layout;
 localparam BIT_CLOCKS=434, N=14;
 reg clk=0,rst=1,rx=1,safe=1;reg [4:0] scan=0;wire [4:0] pitch;wire tx,locked;
 always #10 clk=~clk;
 bt_console dut(.clk(clk),.rst(rst),.bt_rx(rx),.bt_tx(tx),.audio_tick(1'b0),.pcm(16'd0),.locked(locked),
  .accept(1'b1),.settled(1'b1),.volume(7'd7),.timbre(3'd4),.fx(3'd0),.lamps(8'd0),
  .layout_safe(safe),.scan_key(scan),.pitch_key(pitch),.guide_ui_valid(1'b0),.guide_ui_action(4'd0),
  .score_video_visible(1'b0),.capture_busy(1'b0),.capture_ready(1'b0),.score_ui_valid(1'b0),.score_ui_action(2'd0));
 reg [7:0] host[0:N*28-1],reply[0:23],value;integer fd,got=0,bitno;
 initial forever begin
  @(negedge tx);
  if(!rst)begin
   repeat(BIT_CLOCKS+BIT_CLOCKS/2)@(posedge clk);value=0;
   for(bitno=0;bitno<8;bitno=bitno+1)begin value[bitno]=tx;repeat(BIT_CLOCKS)@(posedge clk);end
   if(tx!==1'b1)$fatal(1,"TX stop bit");reply[got%24]=value;got=got+1;$fdisplay(fd,"%02x",value);
  end
 end
 task send_byte(input [7:0] b);integer k;begin
  @(negedge clk);rx=0;repeat(BIT_CLOCKS)@(negedge clk);
  for(k=0;k<8;k=k+1)begin rx=b[k];repeat(BIT_CLOCKS)@(negedge clk);end
  rx=1;repeat(BIT_CLOCKS)@(negedge clk);
 end endtask
 task wait_reply(input integer total);integer timeout;begin
  timeout=0;while(got<total && timeout<150000)begin @(negedge clk);timeout=timeout+1;end
  if(got!=total || {reply[0],reply[1],reply[2],reply[3]}!==32'h544b414b)$fatal(1,"TKAK timeout/header");
 end endtask
 integer model[0:31];integer i,j,a,b,tmp;
 task check_scan;integer k;begin
  for(k=0;k<32;k=k+1)begin @(negedge clk);scan=k[4:0];@(posedge clk);#1;
   if(pitch!==model[k][4:0])$fatal(1,"physical key %d expected %d got %d",k,model[k],pitch);
  end
 end endtask
 initial begin
  for(i=0;i<32;i=i+1)model[i]=i;
  $readmemh("key-requests.hex",host);fd=$fopen("key-wire.hex","w");
  repeat(6)@(negedge clk);rst=0;repeat(1000)@(negedge clk);
  for(i=0;i<4;i=i+1)send_byte("U");if(!locked)$fatal(1,"auto-baud not locked");
  send_byte("~");send_byte("J");wait_reply(24);check_scan();
  for(i=0;i<N;i=i+1)begin
   safe= !(i==5 || i==7);
   for(j=0;j<28;j=j+1)send_byte(host[i*28+j]);wait_reply((i+2)*24);
   if(i==1 || i==6)begin a=host[i*28+6];b=host[i*28+7];tmp=model[a];model[a]=model[b];model[b]=tmp;end
   if(i==8)for(j=0;j<32;j=j+1)model[j]=j;
   check_scan();
  end
  $fclose(fd);$display("PASS 15 real 8N1 TKAKs; all 32 mapped scan outputs after every request");$finish;
 end
endmodule
