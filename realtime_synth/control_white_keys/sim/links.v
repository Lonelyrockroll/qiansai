// Independent PC and BT wire-level receivers. PC transactions overlap an SPP command.
`timescale 1ns/1ps
module tb_links;
 reg clk=0,pc=1,bt=1;always #10 clk=~clk;
 wire bt_tx,pc_tx;wire [7:0] leds;
 synth_display_top dut(.sys_clk(clk),.uart_rx(pc),.uart_tx(pc_tx),.bt_rx(bt),.bt_tx(bt_tx),
  .led_n(leds),.key0_n(1'b1),.key1_n(1'b1));
 defparam dut.indicators.STEP=40;
 reg [7:0] frame[0:279],host_reply[0:279],phone_reply[0:143];
 wire pv,bv;wire [7:0] pd,bd;integer np=0,nb=0;
 uart_rx pc_monitor(.clk(clk),.rst(dut.rst),.rx(pc_tx),.data(pd),.valid(pv));
 uart_rx bt_monitor(.clk(clk),.rst(dut.rst),.rx(bt_tx),.data(bd),.valid(bv));
 always @(posedge clk)begin if(pv)begin host_reply[np]=pd;np=np+1;end if(bv)begin phone_reply[nb]=bd;nb=nb+1;end end
 task automatic sendbyte(input is_bt,input [7:0] b);integer i;reg [9:0] bits;begin
  bits={1'b1,b,1'b0};for(i=0;i<10;i=i+1)begin
   @(negedge clk);if(is_bt)bt=bits[i];else pc=bits[i]; repeat(433)@(negedge clk);
  end
 end endtask
 task pc_frame(input integer n);integer i;begin for(i=0;i<28;i=i+1)sendbyte(0,frame[28*n+i]);end endtask
 task complete(input [7:0] c,input integer n);begin sendbyte(1,c);wait(nb==24*n);end endtask
 defparam dut.output_stage.WARMUP_FRAMES=4;
 integer i,j;reg [7:0] sum;
 initial begin
  $readmemh("sim/pc.hex",frame);wait(!dut.rst);
  // The normal silent output is dark, including after boot. Force only the audio
  // bus/mute here to verify the actual top-level tap, then request the old chase.
  @(negedge clk);if(dut.pmod_testing || leds!==8'hff)$fatal(1,"meter idle");
  force dut.PA_EN=0;force dut.pcm=-16'sd2068;
  @(posedge dut.tick);repeat(5)@(negedge clk);if(leds!==8'h07)$fatal(1,"post-FX physical pins");
  force dut.PA_EN=1;@(negedge clk);@(negedge clk);if(leds!==8'hff)$fatal(1,"mute");
  release dut.PA_EN;release dut.pcm;
  force dut.pmod_test=1;@(negedge clk);release dut.pmod_test;
  for(i=0;i<8;i=i+1)begin wait(dut.indicators.testing && dut.indicators.index==i);
    #1;if(leds!==~(8'b1<<i))$fatal(1,"LED polarity/order i=%d pins=%h",i,leds);end
  wait(!dut.indicators.testing);
  sendbyte(1,"U");sendbyte(1,"U");if(!dut.bt_locked || dut.bt_period!=434)$fatal(1,"autobaud");
  fork pc_frame(0);begin wait(dut.controller.rx_index==8);complete("F",1);end join
  wait(np==28);if(dut.ui_focus!=8 || dut.fx_status_mask!=1 || phone_reply[11]!="1")
   $fatal(1,"arbitration/effect focus=%d mask=%d phone[0,11]=%h,%h commands=%d last=%h dropped=%d PC result=%d",dut.ui_focus,dut.fx_status_mask,phone_reply[0],phone_reply[11],dut.bt_count,dut.bt_command,dut.bt_dropped,host_reply[6]);
  complete("+",2);if(dut.drum_level!=2622 || phone_reply[29]!="4")$fatal(1,"volume");
  complete("T",3);if(dut.key_wave!=0 || phone_reply[56]!="0")$fatal(1,"tone");
  complete("?",4);complete("x",5);if(phone_reply[96]!="E" || dut.bt_dropped!=0)$fatal(1,"invalid input");
  pc_frame(1);wait(np==56);pc_frame(2);wait(np==84);
  fork pc_frame(3);begin
   wait(dut.indicators.testing && dut.indicators.hold_one);
   repeat(300)begin @(negedge clk);if(leds!==8'hdf)$fatal(1,"single lamp must only light L6");end
   wait(!dut.indicators.testing);
  end join
  wait(np==112);
  wait(dut.controller.ui_ready);force dut.button_valid=1;force dut.button_action=2;
  @(negedge clk);@(negedge clk);release dut.button_valid;release dut.button_action;
  wait(dut.fx_status_mask==2);
  if(host_reply[35]!=1 || host_reply[39]!=5 || host_reply[63]!=1)$fatal(1,"USB readback");
  for(j=0;j<4;j=j+1)begin sum=0;for(i=2;i<26;i=i+1)sum=sum^host_reply[j*28+i];
   if(host_reply[j*28]!=8'h5a || host_reply[j*28+3]!=17 || host_reply[j*28+24]!=26 ||
     host_reply[j*28+26]!=sum || host_reply[j*28+27]!=13)$fatal(1,"PC reply corruption");end
  pc_frame(4);wait(np==140);wait(dut.amp_ready);
  pc_frame(5);wait(np==168);if(dut.panel_keys!==32'h00004000)$fatal(1,"middle C did not light H15");
  pc_frame(6);wait(np==196);if(dut.panel_keys!==32'h80004000)$fatal(1,"F6 did not light H32");
  pc_frame(7);wait(np==224);if(dut.panel_keys!==32'h80004000)$fatal(1,"raw diagnostic lit a key");
  pc_frame(8);wait(np==252);if(dut.panel_keys!==32'h80000000)$fatal(1,"releasing C4 changed the wrong key");
  pc_frame(9);wait(np==280);if(dut.panel_keys!==0)$fatal(1,"panic did not clear screen keys");
  $display("PASS independent UART replies, simultaneous PC/SPP requests, effect menu and mask, keypad volume/tone, 8 active-low lights");$finish;
 end
 initial begin #120000000;$fatal(1,"links test timeout nb=%0d np=%0d fx=%d",nb,np,dut.fx_status_mask);end
endmodule
