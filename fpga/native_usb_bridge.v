`timescale 1ns/1ps
// USB is processed at 60 MHz. A stable-data toggle mailbox transfers reports to 50 MHz.
module native_usb_bridge(input wire sys_clk,rst,inout wire usb_dp,usb_dm,
 input wire [15:0] current_level,input wire [2:0] current_timbre,
 input wire drum_mode,drum_hit_ready,output wire drum_hit_valid,output wire [3:0] drum_hit_pad,
 input wire command_ready,output wire command_valid,output reg [3:0] command_action,
 output reg [15:0] command_value,output reg disconnect_pulse,
 output wire connected,output reg [31:0] event_count,output reg [4:0] last_event,output reg [63:0] diagnostic);
 wire uclk,locked;usb_host_pll usb_pll(.clkin(sys_clk),.lock(locked),.clkout0(uclk),.clkout1());
 reg [3:0] startup=0;always @(posedge uclk or negedge locked)if(!locked)startup<=0;else startup<={startup[2:0],1'b1};
 wire urst=!(&startup);wire dp,dm,oe,uc,err,busy,rv,packet_error;
 wire [511:0] raw;wire [6:0] len;wire [15:0] vid,pid;wire [9:0] ra;wire [3:0] rd;wire re;
 wire [127:0] host_debug;reg [63:0] diagnostic_meta;
 assign usb_dp=oe?dp:1'bz;assign usb_dm=oe?dm:1'bz;
 usb_hid_host_rom rom(.clk(uclk),.en(re),.addr(ra),.dout(rd));
 usb_hid_host_1189 host(.clk(uclk),.reset(urst),.cs(1'b1),.usb_dp_i(usb_dp),.usb_dm_i(usb_dm),
  .usb_dp_o(dp),.usb_dm_o(dm),.usb_oe(oe),.connerr(err),.busy(busy),.host_connected(uc),
  .device_vid(vid),.device_pid(pid),.raw_valid(rv),.raw_bytes(raw),.raw_strobes(len),.packet_error(packet_error),
  .debug_state(host_debug),
  .rom_addr(ra),.rom_dout(rd),.rom_en(re));
 reg request=0,ack=0,overflow=0,error_toggle=0;reg [1:0] ack_sync=0,request_sync=0,connect_sync=0,error_sync=0,overflow_sync=0;
 reg [127:0] held_data;reg [4:0] held_length;
 always @(posedge uclk)begin
  ack_sync<={ack_sync[0],ack};
  if(urst)begin request<=0;overflow<=0;error_toggle<=0;end
  else begin
   if(!uc)overflow<=0;
   if(packet_error && uc)error_toggle<=!error_toggle;
   if(rv && uc && len<=16)begin
    if(request==ack_sync[1])begin held_data<=raw[127:0];held_length<=len[4:0];request<=!request;end
    else overflow<=1;
   end
  end
 end
 reg report_valid=0;reg [127:0] report_data;reg [4:0] report_length;
 reg was_connected=0,previous_error=0,previous_fault=0;
 wire event_valid,event_ready,parser_fault;wire [4:0] event_id;
 assign connected=connect_sync[1] && !overflow_sync[1];
 always @(posedge sys_clk)begin
  diagnostic_meta<={locked,uc,overflow,err,packet_error,host_debug[66:64],host_debug[55:0]};diagnostic<=diagnostic_meta;
  request_sync<={request_sync[0],request};connect_sync<={connect_sync[0],uc};
  error_sync<={error_sync[0],error_toggle};overflow_sync<={overflow_sync[0],overflow};
  report_valid<=0;disconnect_pulse<=0;was_connected<=connected;previous_error<=error_sync[1];previous_fault<=parser_fault;
  if(rst)begin ack<=0;was_connected<=0;event_count<=0;last_event<=0;end
  else begin
   if(request_sync[1]!=ack)begin report_data<=held_data;report_length<=held_length;report_valid<=1;ack<=request_sync[1];end
   if((was_connected && !connected) || error_sync[1]!=previous_error || (parser_fault && !previous_fault))disconnect_pulse<=1;
   if(event_valid && event_ready)begin event_count<=event_count+1'b1;last_event<=event_id;end
  end
 end
 native_keypad_drums decoder(.clk(sys_clk),.rst(rst || disconnect_pulse),.connected(connected),.report_valid(report_valid),
  .mode_change(1'b0),
  .report_length(report_length),.report_data(report_data),.event_valid(event_valid),.event_ready(event_ready),.event_id(event_id),.fault(parser_fault));
 wire [15:0] volume_limit=drum_mode?16'd16384:16'd26214;
 always @*begin
  command_action=0;command_value=0;
  case(event_id)
   14:command_action=3;
   17:command_action=2;
   16:command_action=9;
   15:command_action=1;
   12,13:begin command_action=13;command_value={15'd0,event_id==12};end
   18,19:begin command_action=15;command_value={15'd0,event_id==18};end
   20:begin command_action=7;command_value=current_level < volume_limit-16'd1311 ? current_level+16'd1311 : volume_limit;end
   21:begin command_action=7;command_value=current_level>1311?current_level-16'd1311:16'd0;end
   default:;
  endcase
 end
 assign drum_hit_valid=event_valid && event_id<12;
 assign drum_hit_pad=event_id[3:0];
 assign command_valid=event_valid && command_action!=0 && !(event_id<12);
 assign event_ready=(event_id<12)?drum_hit_ready:(command_action==0 || command_ready);
endmodule
