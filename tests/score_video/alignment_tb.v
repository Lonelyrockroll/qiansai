`timescale 1ns/1ps
// Real legacy panel renderer, real score renderer/RAM, shared pixel inputs.
module score_alignment_tb;
 reg clk=0,rst=1,request=0;always #5 clk=~clk;
 reg [10:0] x=0,y=0;reg hs=0,vs=0,de=0,frame_start=0;
 wire [23:0] panel_rgb,score_rgb;wire panel_hs,panel_vs,panel_de,selected,visible;
 wire [14:0] address;wire [15:0] data;
 score_capture_ram ram(.sys_clk(clk),.sys_write(1'b0),.sys_address(15'd0),.sys_data(16'd0),.sys_q(),
  .pixel_clk(clk),.pixel_address(address),.pixel_q(data));
 score_renderer score(.clk(clk),.rst(rst),.show_requested(request),.x(x),.y(y),.de(de),.frame_start(frame_start),
  .read_address(address),.read_data(data),.visible(visible),.select_page(selected),.rgb(score_rgb));
 panel_renderer panel(.clk(clk),.rst(rst),.x(x),.y(y),.hs(hs),.vs(vs),.de(de),
  .bend_position(4'd4),.focus(4'd0),.vibrato_depth(3'd0),.fx(3'd0),.timbre(3'd0),.volume(7'd7),.voices(6'd0),.mode(2'd0),
  .calibrated(1'b1),.fault(1'b0),.muted(1'b1),.ready(1'b1),.playing(1'b0),.pattern(1'b1),
  .loop_actual_cs(10'd0),.loop_position_cs(10'd0),.loop_layers(3'd0),.loop_notice(3'd0),.loop_duration(2'd0),
  .loop_playing(1'b0),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd0),.drum_mode(1'b0),
  .notice(4'd0),.pressed(32'd0),.peak(8'd0),.guide_valid(1'b0),.guide_playing(1'b0),.guide_loading(1'b0),.guide_demo(1'b0),
  .guide_time_cs(16'd0),.guide_duration_cs(16'd0),.guide_count(10'd0),.guide_index(10'd0),.guide_speed(2'd2),
  .guide_target(32'd0),.guide_onset(32'd0),.guide_next(32'd0),.guide_colors(64'd0),.actual_keys(32'd0),
  .rgb(panel_rgb),.hs_out(panel_hs),.vs_out(panel_vs),.de_out(panel_de));
 wire [23:0] mux_rgb=selected?score_rgb:panel_rgb;
 function [15:0] pattern_word(input integer a);
 begin pattern_word=((a*16'h1021)^(a>>3)^16'ha6d3)&16'hffff;end endfunction
 function [23:0] expected_panel(input integer px,py);
 begin
  case((px>>7)&7)
   0:expected_panel=24'hffffff;1:expected_panel=24'hffff00;2:expected_panel=24'h00ffff;3:expected_panel=24'h00ff00;
   4:expected_panel=24'hff00ff;5:expected_panel=24'hff0000;6:expected_panel=24'h0000ff;7:expected_panel=24'h101820;
  endcase
  if(px<4 || px>=1020 || py<4 || py>=596 || px==511 || px==512 || py==299 || py==300)expected_panel=24'hffffff;
 end endfunction
 reg eh[0:2],ev[0:2],ed[0:2],es[0:2],valid[0:2];reg [23:0] ep[0:2],ec[0:2];
 integer i,j,samples=0;
 always @(posedge clk)begin
  if(rst)begin for(j=0;j<3;j=j+1)valid[j]=0;end
  else begin
   for(j=2;j>0;j=j-1)begin eh[j]=eh[j-1];ev[j]=ev[j-1];ed[j]=ed[j-1];es[j]=es[j-1];ep[j]=ep[j-1];ec[j]=ec[j-1];valid[j]=valid[j-1];end
   eh[0]=hs;ev[0]=vs;ed[0]=de;es[0]=visible;ep[0]=expected_panel(x,y);valid[0]=1;
   ec[0]=((pattern_word(address)>>(15-x[3:0]))&1)?24'h000000:24'hffffff;
   #1;
   if(valid[2])begin
    samples=samples+1;
    if(panel_hs!==eh[2] || panel_vs!==ev[2] || panel_de!==ed[2])$fatal(1,"Legacy sync/DE latency");
    if(panel_rgb!==ep[2])$fatal(1,"Legacy RGB latency");
    if(selected!==es[2] || score_rgb!==ec[2])$fatal(1,"Score select/RGB latency");
    if(mux_rgb!==(es[2]?ec[2]:ep[2]))$fatal(1,"Final page mux latency");
   end
  end
 end
 initial begin
  for(i=0;i<32768;i=i+1)ram.memory[i]=pattern_word(i);
  repeat(4)@(negedge clk);rst=0;
  for(i=0;i<1200;i=i+1)begin
   @(negedge clk);x=(i*37)%1023;y=(i*11)%600;de=(i%5)!=0;hs=i[0];vs=i[2];frame_start=0;
   if(i==50 || i==650)begin #2;request=~request;end
   if(i==100 || i==700)begin x=0;y=600;de=0;frame_start=1;end
  end
  repeat(4)@(negedge clk);
  $display("PASS alignment samples=%0d real_panel_rgb_hs_vs_de_score_select_and_mux",samples);$finish;
 end
endmodule
