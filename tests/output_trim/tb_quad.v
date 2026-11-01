`timescale 1ns/1ps
module tb_quad;
 reg clk=0,rst=1;always #10 clk=!clk;
 reg signed [15:0] left=1234,right=-309;
 reg [11:0] trim=1637;reg [1:0] mode=0;
 wire tick,ib,iw,id,hb,hw,hd;
 audio_tx #(.USE_PT_TRIM(1)) dut(.clk(clk),.rst(rst),.pcm_left(left),.pcm_right(right),
    .pt_trim(trim),.pt_mode(mode),.sample_tick(tick),.i2s_bclk(ib),.i2s_lrclk(iw),.i2s_data(id),
    .hp_bck(hb),.hp_ws(hw),.hp_din(hd));
 integer frame=0,clocks=0,last=0,ptbits=0,ibits=0,route=0,latched_l=0,latched_r=0,latched_trim=0;
 reg [15:0] word_value,iw_l=0,iw_r=0;
 function integer addend(input integer sub,input integer route0);
   begin if(route0!=2)addend=0;
   else case(sub) 0:addend=140;1:addend=-140;2:addend=36;default:addend=-38;endcase end
 endfunction
 function [15:0] clipped(input integer v);begin clipped=v>32767?16'h7fff:v< -32768?16'h8000:v[15:0];end endfunction
 always @(posedge clk)begin
   clocks=clocks+1;
   if(!rst && tick)begin
    if(frame)begin
      if(clocks-last!=1024 || ptbits!=(route!=0?128:32) || ibits!=64) $fatal(1,"clock/bit count");
      if(iw_l!==latched_l[15:0] || iw_r!==latched_r[15:0])$fatal(1,"I2S changed");
    end
    latched_l=left;latched_r=right;latched_trim=trim;route=mode;frame=frame+1;last=clocks;ptbits=0;ibits=0;
   end
 end
 always @(posedge ib)if(!rst && frame)begin
    if(iw!==(ibits>=32))$fatal(1,"I2S WS");
    if((ibits%32)>=1 && (ibits%32)<=16)begin
      if(ibits<32)iw_l={iw_l[14:0],id};else iw_r={iw_r[14:0],id};
    end else if(id!==0)$fatal(1,"I2S padding");
    ibits=ibits+1;
 end
 always @(posedge hb)if(!rst && frame)begin
    if(hw!==((ptbits%32)>=16))$fatal(1,"PT WS");
    word_value={word_value[14:0],hd};
    if(ptbits%16==15 && word_value!==clipped((hw?latched_l:latched_r)+latched_trim+addend(ptbits/32,route)))
      $fatal(1,"PT data frame %d bit %d got %h",frame,ptbits,word_value);
    ptbits=ptbits+1;
 end
 task upcoming(input [1:0] m,input [11:0] b,input signed [15:0] a,c);
 begin @(negedge clk);while(dut.count!=1000)@(negedge clk);mode=m;trim=b;left=a;right=c;end endtask
 initial begin
   repeat(5)@(negedge clk);rst=0;
   wait(frame==3);upcoming(1,1577,-1601,12204);
   wait(frame==7);upcoming(2,1577,-201,200);
   wait(frame==12);upcoming(2,4095,32767,-32768);
   wait(frame==15);upcoming(0,789,28000,-28000);
   wait(frame==18);$display("PASS I2S supplies original 16-bit samples and PT words decode correctly in 1x, 4x, four-offset, saturation and mode changes");$finish;
 end
 initial begin #450000; $fatal(1,"timeout");end
endmodule
