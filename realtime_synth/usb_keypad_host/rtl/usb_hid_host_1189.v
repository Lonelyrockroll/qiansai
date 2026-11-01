// ---------------------------------------------------------------------------
// Copyright 2023 nand2mario
// Copyright 2026 Mateusz Nalewajski
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0
// ---------------------------------------------------------------------------

`default_nettype none
`timescale 1ns / 1ps
module usb_hid_host_1189 #(
  parameter FULL_SPEED = 1,
  parameter KEYBOARD_SUPPORT = 1,
  parameter MOUSE_SUPPORT = 1,
  parameter GAME_SUPPORT = 1,
  parameter XINPUT_SWAP_AB_XY = 0,  // swap A/B and X/Y for all XInput devices
  parameter FORCE_ARDUINO_KEYBOARD = 0  // assume CDC + Keyboard for Arduino/SparkFun VIDs
) (
  input wire clk,    // 60MHz clock when FULL_SPEED=1, otherwise 12MHz
  input wire reset,  // reset
  input wire cs,     // chip select

  input  wire usb_dm_i, usb_dp_i,  // USB D- and D+
  output wire usb_dm_o, usb_dp_o,  // USB D- and D+
  output wire usb_oe,              // USB OE

  // key_*, mouse_*, game_* valid depending on typ
  output reg  [1:0] typ,    // device type. 0: no device, 1: keyboard, 2: mouse, 3: gamepad
  output reg  full_report,  // pulse after full report received from device
  output wire connerr,      // connection or protocol error
  output wire busy,

  // keyboard
  output reg [7:0] key_modifiers,
  output reg [7:0] key_0, key_1, key_2, key_3, key_4, key_5,

  // mouse
  output reg [2:0] mouse_btn,        // middle, right, left
  output reg signed [7:0] mouse_dx,  // signed 8-bit, valid during full_report pulse
  output reg signed [7:0] mouse_dy,  // signed 8-bit, valid during full_report pulse

  // gamepad
  output reg       game_l, game_r, game_u, game_d,                      // left right up down
  output reg       game_a, game_b, game_x, game_y, game_sel, game_sta,  // buttons
  output reg [3:0] game_extra,                                          // extra buttons

  // debug
  output wire [63:0] dbg_hid_report,  // last HID report
  output wire [63:0] dbg_hid_regs,    // internal regs

  // Diagnostic capture: sampled bytes may include CRC tail. No CRC acceptance claim.
  output wire host_connected,output wire [15:0] device_vid,device_pid,
  output wire [127:0] debug_state,
  output reg raw_valid,output reg [511:0] raw_bytes,output reg [6:0] raw_strobes,
  output wire packet_error,

  // rom
  output wire [9:0] rom_addr,
  input  wire [3:0] rom_dout,
  output wire       rom_en
);

wire packet_valid;wire [7:0] packet_pid;wire [6:0] packet_length;wire [511:0] packet_payload;
wire       ukprdy;
wire       ukpstb;
wire       ukpstart;
wire [7:0] ukpdat;
wire [3:0] addra;
wire [3:0] addrb;
wire       save;
wire       load;
wire       connected;
wire       full_speed;

reg [10:0] load_data;

ukp_1189 #(
  .FULL_SPEED(FULL_SPEED)
) ukp (
  .reset(reset),
  .clk(clk),
  .cs(cs),
  .usb_dp_i(usb_dp_i),
  .usb_dm_i(usb_dm_i),
  .usb_dp_o(usb_dp_o),
  .usb_dm_o(usb_dm_o),
  .usb_oe(usb_oe),
  .packet_valid(packet_valid),.packet_pid(packet_pid),.packet_length(packet_length),.packet_payload(packet_payload),.packet_error(packet_error),
  .ukprdy(ukprdy),
  .ukpstb(ukpstb),
  .ukpstart(ukpstart),
  .ukpdat(ukpdat),
  .addra(addra),
  .addrb(addrb),
  .save(save),
  .load(load),
  .load_data(load_data),
  .descriptor_active(descriptor_active),
  .debug_state(ukp_debug),
  .connected(connected),
  .full_speed(full_speed),
  .connerr(connerr),
  .busy(busy),
  .rom_addr(rom_addr),
  .rom_dout(rom_dout),
  .rom_en(rom_en)
);

reg        hid_device;         // indicates if device is a valid HID device
reg  [7:0] in_payload  [0:1];  // USB IN request payload data for endpoint specific to a given VID, PID
reg  [7:0] out_payload [0:1];  // USB OUT request payload data for endpoint specific to a given VID, PID
reg        x_input;            // indicates if pad should be polled in X-Input mode
reg  [3:0] polling_interval;   // polling interval in ms
reg [15:0] report_mask;        // bit mask which allows to selectively pick bytes from report

reg [7:0] dat  [0:7];          // data in last response (up to 8 bytes, wraps-around)
reg [7:0] regs [0:7];          // 0 (VID_L), 1 (VID_H), 2 (PID_L), 3 (PID_H), 4 (INTERFACE_CLASS), 5 (INTERFACE_SUBCLASS), 6 (INTERFACE_PROTOCOL), 7 (UNUSED)
reg [3:0] rcvct;
reg [2:0] dat_idx;
reg [1:0] crc_tail;
reg [1:0] typ_next;
reg       ukprdy_r;
reg       connected_r;

wire [15:0] vid = {regs[1], regs[0]};
wire [15:0] pid = {regs[3], regs[2]};

// Assume standard AVR CDC + Keyboard firmware for Arduino/SparkFun VIDs.
// HID uses IN endpoint 4 and report ID 2 followed by an eight-byte key report.
// The captured CDC IAD bytes distinguish this layout from Caterina's 02/02/01.
// Sample before endpoint loads, which follow descriptor saving and recovery.
reg arduino_keyboard;
always @(posedge clk) begin
  arduino_keyboard <= FORCE_ARDUINO_KEYBOARD && KEYBOARD_SUPPORT &&
                      (vid == 16'h2341 || vid == 16'h1b4f) &&
                      {regs[4], regs[5], regs[6]} == 24'h020000;
end

assign dbg_hid_report = {dat[7], dat[6], dat[5], dat[4], dat[3], dat[2], dat[1], dat[0]};
assign dbg_hid_regs   = {regs[7], regs[6], regs[5], regs[4], regs[3], regs[2], regs[1], regs[0]};

// Complete CRC-checked packets. Enumeration data is exported for descriptor verification.
assign host_connected=connected && profile_ok;
wire descriptor_active,profile_ok;wire [127:0] ukp_debug;
assign debug_state={61'd0,descriptor_active,profile_ok,connected,ukp_debug[63:0]};
usb_profile_check profile(.clk(clk),.reset(reset || connerr),.descriptor_active(descriptor_active),
 .packet_valid(packet_valid && (packet_pid==8'hc3 || packet_pid==8'h4b)),.length(packet_length),.payload(packet_payload),.profile_ok(profile_ok));
assign device_vid=vid;assign device_pid=pid;
reg expected_toggle;reg was_connected;
always @(posedge clk) begin
  raw_valid<=0;was_connected<=connected;
  if(reset || connerr || !connected)expected_toggle<=0;
  if(reset || connerr) begin raw_bytes<=0;raw_strobes<=0;was_connected<=0;end
  else if(packet_valid && (packet_pid==8'hc3 || packet_pid==8'h4b)) begin
    if(!connected || (was_connected && packet_pid[3]==expected_toggle && packet_length<=16)) begin
      raw_bytes<=packet_payload;raw_strobes<=packet_length;raw_valid<=1;
      if(connected)expected_toggle<=!expected_toggle;
    end
  end
end

reg [15:0] frame_timer;reg [10:0] frame_number;
function [4:0] token_crc(input [10:0] value);
 reg [4:0] c;integer b;begin c=31;for(b=0;b<11;b=b+1)c=(c>>1)^((c[0]^value[b])?5'h14:0);token_crc=~c;end
endfunction
always @(posedge clk)begin
 if(reset)begin frame_timer<=0;frame_number<=0;end
 else if(frame_timer==59999)begin frame_timer<=0;frame_number<=frame_number+1'b1;end
 else frame_timer<=frame_timer+1'b1;
end
integer i;

// handle save and load instructions
always @(posedge clk) begin
  if (reset || connerr) begin
    for (i = 0; i < 8; i = i + 1)
      regs[i] <= 8'b0;

  end else if (save) begin
    regs[addra[2:0]] <= dat[addrb[2:0]];

  end else if (load) begin
    case (addra)
      4'd4: load_data <= {3'd0,frame_number[7:0]};
      4'd5: load_data <= {3'd0,token_crc(frame_number),frame_number[10:8]};
      4'd6: load_data <= {10'd0,profile_ok};
      4'd7: load_data <= 11'd1656; // 207 descriptor bytes
      4'd8: load_data <= in_payload[0];
      4'd9: load_data <= in_payload[1];
      4'd10: load_data <= out_payload[0];
      4'd11: load_data <= out_payload[1];
      4'd12: load_data <= x_input ? 8'b1 : 8'b0;
      4'd13: load_data <= {4'b0, polling_interval};
      4'd14: load_data <= {7'b0, hid_device};
      default: load_data <= regs[addra[2:0]];
    endcase
  end
end

integer j;

// handle ukp data from packets
always @(posedge clk) begin
  if (reset || connerr) begin
    for (j = 0; j < 8; j = j + 1)
      dat[j] <= 8'b0;

    ukprdy_r    <= 0;
    connected_r <= 0;
    typ         <= 0;
    full_report <= connerr;  // send empty report on connection error
    rcvct       <= 0;
    dat_idx     <= 0;
    crc_tail    <= 0;

  end else if (ukpstart) begin
    rcvct       <= 0;  // mark start of read transaction
    dat_idx     <= 0;
    crc_tail    <= 0;
    full_report <= 0;

  end else if (ukprdy) begin
    ukprdy_r    <= ukprdy;
    full_report <= 0;

    if (ukpstb) begin
      rcvct <= rcvct + 1;

      if (crc_tail != 0)
        crc_tail <= crc_tail - 1;

      // record byte from a packet
      if (report_mask[rcvct]) begin
        dat[dat_idx] <= ukpdat;
        dat_idx      <= dat_idx + 1;
        crc_tail     <= crc_tail != 2 ? crc_tail + 1 : 2;
      end
    end
  end else begin
    ukprdy_r    <= ukprdy;
    connected_r <= connected;
    full_report <= 0;

    // individual packet received, ukprdy is not asserted
    if (ukprdy_r) begin
      // ignore CRC16, important when packets are split
      rcvct   <= rcvct - 2;
      // adjust dat index and cut-off CRC bytes
      dat_idx <= dat_idx - crc_tail;

      if (connected) begin  // change typ after a first valid report
        typ         <= typ_next;
        full_report <= 1;
      end
    end

    // send empty report on connection state change
    if (connected && !connected_r) begin
      for (j = 0; j < 8; j = j + 1)
        dat[j] <= 8'b0;

      full_report <= 1;
    end
  end
end

// classify by INTERFACE_CLASS, INTERFACE_SUBCLASS, INTERFACE_PROTOCOL
reg x_input_i;

always @(*) begin
  typ_next = 0;
  x_input_i  = 0;

  casez ({regs[4], regs[5], regs[6]})
    {8'h03, 8'h01, 8'h01}: if (KEYBOARD_SUPPORT) typ_next = 1;  // keyboard
    {8'h03, 8'h01, 8'hzz}: if (MOUSE_SUPPORT)    typ_next = 2;  // mouse
    {8'h03, 8'hzz, 8'hzz}: if (GAME_SUPPORT)     typ_next = 3;  // other (incl. 8BitDo, D-Input)
    {8'hff, 8'h5d, 8'h01},
    {8'hff, 8'h5d, 8'h81}: begin
      if (GAME_SUPPORT) typ_next = 3;
      x_input_i  = 1;
    end  // Xbox 360 (incl. 8BitDo, X-Input); wired - protocol 1, wireless - protocol 129
  endcase

  // The fixed configuration read sees CDC's IAD instead of the HID interface.
  if (arduino_keyboard) begin
    typ_next = 1;
    x_input_i = 0;
  end
end

// sample values to improve timing and optimize resource usage
always @(posedge clk) begin
  hid_device <= (vid==16'h1189 && pid==16'h8840 && regs[4]==8'h03);
  x_input    <= x_input_i;
end

// set in_payload and out_payload payload depending on VID, PID
// ref: https://rayslogic.com/Propeller/USB.htm#USB%20Token
always @(*) begin
  casez ({vid, pid})
    {16'h1189,16'h8840}: begin
      in_payload[0]=8'h01;in_payload[1]=8'hc1; // address 1, interrupt IN endpoint 2
      out_payload[0]=8'h01;out_payload[1]=8'hc1;
    end
    {16'h2dc8, 16'h301c},
    {16'h2dc8, 16'h310a}: begin
      in_payload[0] = 8'h01;   // IN endpoint 4 (01 ba)
      in_payload[1] = 8'hba;

      out_payload[0] = 8'h81;  // OUT endpoint 5 (81 0a)
      out_payload[1] = 8'h0a;
    end  // 8BitDo Ultimate 2C
    default: begin
      in_payload[0] = arduino_keyboard ? 8'h01 : 8'h81;  // IN endpoint 4 or default 1
      in_payload[1] = arduino_keyboard ? 8'hba : 8'h58;

      out_payload[0] = 8'h01;  // OUT endpoint 2 (01 c1) - default
      out_payload[1] = 8'hc1;
    end
  endcase
end

// set report_mask
always @(posedge clk) begin
  if (!connected || reset) begin  // Wrap-around when enumeration didn't finish
      report_mask <= 16'b1111111111111111;

  end else if (arduino_keyboard) begin
    report_mask <= 16'b0000000111111110;  // skip report ID; pack modifiers/reserved/six keys

  end else begin
    casez ({typ_next, x_input, vid, pid})
      {2'b11, 1'b0, 16'h2dc8, 16'h9020}: begin  // 8BitDo Micro in D-Input mode
        report_mask <= 16'b0000001100000010;
      end
      {2'b11, 1'b1, 16'hzzzz, 16'hzzzz}: begin  // X-Input
        report_mask <= 16'b0000001010111101;
      end
      default: begin                            // By default assume only 8 bytes in HID report
        report_mask <= 16'b0000000011111111;
      end
    endcase
  end
end

// set polling interval depending on typ_next, full_speed, x_input, VID, PID
always @(posedge clk) begin
  casez ({typ_next, full_speed, x_input, vid, pid})
    {2'bzz,1'b1,1'bz,16'h1189,16'h8840}:polling_interval<=4'd1;
    {2'bzz, 1'b0, 1'bz, 16'hzzzz, 16'hzzzz}: begin
      polling_interval <= 4'd10;  // 10ms for low-speed devices
    end
    {2'b10, 1'b1, 1'b0, 16'hzzzz, 16'hzzzz}: begin
      polling_interval <= 4'd2;   // 2ms for full-speed mouse
    end
    {2'b01, 1'b1, 1'b0, 16'hzzzz, 16'hzzzz}: begin
      polling_interval <= 4'd1;   // 1ms for full-speed keyboard
    end
    {2'b11, 1'b1, 1'bz, 16'h2dc8, 16'hzzzz}: begin
      polling_interval <= 4'd2;   // 2ms for 8BitDo
    end
    {2'b11, 1'b1, 1'b1, 16'hzzzz, 16'hzzzz}: begin
      polling_interval <= 4'd4;   // 4ms for other Xbox-compatible controllers
    end
    default: begin
      polling_interval <= 4'd8;   // 8ms by default
    end
  endcase
end

// module outputs
reg [2:0] hat;

always @(*) begin
  {key_modifiers, key_0, key_1, key_2, key_3, key_4, key_5} = {8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00, 8'h00};
  {mouse_btn, mouse_dx, mouse_dy} = {3'b000, 8'h00, 8'h00};
  {game_l, game_r, game_u, game_d} = {1'b0, 1'b0, 1'b0, 1'b0};
  {game_y, game_x, game_b, game_a} = {1'b0, 1'b0, 1'b0, 1'b0};
  {game_sel, game_sta} = {1'b0, 1'b0};
  game_extra = 4'b0;
  hat = 3'b0;

  if (KEYBOARD_SUPPORT && typ == 1) begin
    {key_modifiers, key_0, key_1, key_2, key_3, key_4, key_5} = {dat[0], dat[2], dat[3], dat[4], dat[5], dat[6], dat[7]};

  end else if (MOUSE_SUPPORT && typ == 2) begin
    {mouse_btn, mouse_dx, mouse_dy} = {dat[0][2:0], dat[1], dat[2]};

  end else if (GAME_SUPPORT && typ == 3) begin
    casez ({x_input, vid, pid})
      {1'b0, 16'h2dc8, 16'h9020}: begin  // 8BitDo Micro in D-Input mode
        {game_y, game_x, game_b, game_a} = {dat[1][4:3], dat[1][1:0]};  // buttons
        {game_sel, game_sta} = {dat[2][2], dat[2][3]};                  // - +

        if (dat[0][3] == 1'b0) begin
          hat = dat[0][2:0];  // circular pattern
          game_u = (hat == 3'd0 || hat == 3'd1 || hat == 3'd7);
          game_d = (hat == 3'd3 || hat == 3'd4 || hat == 3'd5);
          game_l = (hat == 3'd5 || hat == 3'd6 || hat == 3'd7);
          game_r = (hat == 3'd1 || hat == 3'd2 || hat == 3'd3);
        end

        // L2, L, R2, R
        game_extra = {dat[2][0], dat[1][6], dat[2][1], dat[1][7]};
      end
      {1'b0, 16'h2dc8, 16'hzzzz}: begin  // 8BitDo, assume generic D-Input
        {game_y, game_x, game_b, game_a} = {dat[1][4:3], dat[1][1:0]};  // buttons
        {game_sel, game_sta} = {dat[2][2], dat[2][3]};                  // - +

        if (dat[3][3:0] != 4'hf) begin
          hat = dat[3][2:0];  // circular pattern
          game_u = (hat == 3'd0 || hat == 3'd1 || hat == 3'd7);
          game_d = (hat == 3'd3 || hat == 3'd4 || hat == 3'd5);
          game_l = (hat == 3'd5 || hat == 3'd6 || hat == 3'd7);
          game_r = (hat == 3'd1 || hat == 3'd2 || hat == 3'd3);
        end

        // lt, lb, rt, rb
        game_extra = {dat[2][0], dat[1][6], dat[2][1], dat[1][7]};
      end
      {1'b1, 16'hzzzz, 16'hzzzz}: begin  // Xbox 360 - compatible (X-Input)
        if (dat[0] == 8'h00) begin  // valid pad data
          if (XINPUT_SWAP_AB_XY)
            {game_x, game_y, game_a, game_b} = dat[2][7:4];  // swap X/Y and A/B
          else
            {game_y, game_x, game_b, game_a} = dat[2][7:4];  // buttons
          {game_sel, game_sta} = {dat[1][5], dat[1][4]};   // - +

          {game_r, game_l, game_d, game_u} = {dat[1][3:0]};  // d-pad

          // map analog stick as d-pad
          game_r = game_r || (dat[5][7] == 1'b0 &&  |dat[5][6:5]);
          game_l = game_l || (dat[5][7] == 1'b1 && ~&dat[5][6:5]);
          game_u = game_u || (dat[6][7] == 1'b0 &&  |dat[6][6:5]);
          game_d = game_d || (dat[6][7] == 1'b1 && ~&dat[6][6:5]);

          // l2, l1, r2, r1
          game_extra = {(|dat[3]), dat[2][0], (|dat[4]), dat[2][1]};
        end
      end
      {1'b0, 16'h0738, 16'h2217}: begin  // SpeedLink COMPETITION PRO Extra
        {game_y, game_x, game_b, game_a} = {dat[0][2], dat[0][0], dat[0][3], dat[0][1]};

        {game_l, game_r} = {dat[1][7:6] == 2'b00, dat[1][7:6] == 2'b11};
        {game_u, game_d} = {dat[2][7:6] == 2'b00, dat[2][7:6] == 2'b11};
      end
      default: begin
        // A typical report layout:
        // - d[3] is X axis (0: left, 255: right)
        // - d[4] is Y axis
        // - d[5][7:4] is buttons YBAX
        // - d[6][5:4] is buttons START, SELECT

        {game_l, game_r} = {dat[3][7:6] == 2'b00, dat[3][7:6] == 2'b11};
        {game_u, game_d} = {dat[4][7:6] == 2'b00, dat[4][7:6] == 2'b11};

        {game_a, game_b} = {dat[5][5], dat[5][6]};
        {game_x, game_y} = {dat[5][4], dat[5][7]};

        {game_sel, game_sta} = {dat[6][4], dat[6][5]};
      end
    endcase
  end
end

endmodule

module ukp_1189 #(
  parameter FULL_SPEED = 1
) (
  input wire clk,
  input wire reset,
  input wire cs,

  input  wire usb_dm_i, usb_dp_i, // USB D- and D+
  output wire usb_dm_o, usb_dp_o, // USB D- and D+
  output wire usb_oe,             // USB OE

  output wire packet_valid,packet_error,output wire [7:0] packet_pid,output wire [6:0] packet_length,output wire [511:0] packet_payload,
  output reg        ukprdy,   // data frame is outputing
  output reg        ukpstb,   // strobe for a byte within the frame
  output reg        ukpstart, // marks start of read transaction
  output reg  [7:0] ukpdat,   // output data when ukpstb = 1

  output reg  [3:0] addra,
  output reg  [3:0] addrb,
  output reg        save,
  output reg        load,
  input  wire [10:0] load_data,

  output wire [9:0] rom_addr,
  input  wire [3:0] rom_dout,
  output wire       rom_en,

  output reg descriptor_active,output wire [127:0] debug_state,
  output reg  connected,
  output reg  full_speed,
  output wire connerr,
  output wire busy
);

// input filter parameters
localparam RX_FILTER  = 3;  // last 3 samples
localparam EOP_FILTER = 3;
localparam SUM_WIDTH  = $clog2(RX_FILTER + 1) + 1;  // +/- 3 range

wire [3:0] inst;
wire       polarity;
wire       sample;
wire       transmission;
wire       data01;
wire       payload;
wire       di;
wire       dbit;
wire       timing_0, timing_1, timing_rx;

reg  [3:0] insth;  // current instruction
reg [10:0] wk;  // W register
reg  [7:0] sb;  // out value
reg  [2:0] sadr;  // out4 / outb write ptr
reg  [3:0] lb4;  // instruction operand
reg  [7:0] data;  // received data
reg  [2:0] nrztxct, nrzrxct;  // NRZI trans/recv count for bit stuffing
reg [9:0] bitaddr;  // 0~512
reg  [2:0] timing;  // T register (0~7)
reg  [2:0] prescaler;  // clock prescaler for low-speed
reg [15:0] interval = 1;  // frame interval counter
reg  [7:0] delay    = 1;  // inter-packet delay counter
reg  [9:0] conct;  // watchdog counter

reg eop, ug, up, um, did, dis, cond, eot, nak, stall;

reg [RX_FILTER-1:0] dpi, dmi;

reg signed [SUM_WIDTH-1:0] dsum, sum;

reg [4:0] state, state_next;
reg [9:0] pc, pc_next;
reg [1:0] pc_step;
reg pc_override;
reg [9:0] wpc [0:1];

`ifdef VERILATOR
wire interval_frame = interval == 30;
`else
wire interval_frame = interval == (FULL_SPEED ? 60000 : 12000);
`endif

`ifdef VERILATOR
wire timeout = 0;
`else
wire timeout = delay >= (FULL_SPEED && full_speed ? 90 : 144);  // 18 x bit time
`endif

wire checked_done,checked_ok;
reg [4:0] previous_state;reg physical_bad,packet_aligned;
always @(posedge clk) begin
 previous_state<=state;
 if(reset || state==S_RX0)begin physical_bad<=0;packet_aligned<=0;end
 else if(sample)begin
  if(!eop && nrzrxct==6 && dis==di)physical_bad<=1;
  if(eop && (|dpi[EOP_FILTER-1:0]))physical_bad<=1;
  if(eop)packet_aligned<=bitaddr[2:0]==0;
 end
end
usb_packet_check check_rx(.clk(clk),.reset(reset),.start(state==S_RX0),
 .byte_valid(sample && nrzrxct!=6 && bitaddr!=0 && bitaddr[2:0]==0),.byte_data(data),
 .finish(state==S_SYNC && (previous_state==S_RX1 || previous_state==S_RX0)),
 .physical_error(physical_bad),.aligned(packet_aligned),.done(checked_done),.ok(checked_ok),
 .valid(packet_valid),.error(packet_error),.pid(packet_pid),.length(packet_length),.payload(packet_payload));
assign debug_state={64'd0,6'd0,conct,6'd0,pc,3'd0,state,wk[7:0],bitaddr[7:0],
  usb_dp_i,usb_dm_i,ug,up,um,di,eop,full_speed};
assign polarity = full_speed;

assign usb_dp_o = up;
assign usb_dm_o = um;
assign usb_oe   = ug;

assign connerr = (&conct) && (di || connected);

integer i;

always @(*) begin
  sum = 0;

  for (i = 0; i < RX_FILTER; i = i + 1)
    sum = sum
      + {{(SUM_WIDTH-1){1'b0}}, dpi[i]}
      - {{(SUM_WIDTH-1){1'b0}}, dmi[i]};
end

always @(posedge clk) begin
  dpi <= {dpi[RX_FILTER-2:0], usb_dp_i};
  dmi <= {dmi[RX_FILTER-2:0], usb_dm_i};

  dsum <= sum;
  eop  <= dpi[EOP_FILTER-1:0] == dmi[EOP_FILTER-1:0];
end

assign di   = (dsum < 0) ^ polarity;
assign dbit = sb[7 - sadr[2:0]];

// state machine
localparam S_OPCODE = 0;
localparam S_SYNC   = 1;
localparam S_WAIT   = 2;
localparam S_LDI0   = 3;
localparam S_LDI1   = 4;
localparam S_BX     = 5;
localparam S_B0     = 6;
localparam S_B1     = 7;
localparam S_B2     = 8;
localparam S_HIZ    = 9;
localparam S_RX0    = 10;
localparam S_RX1    = 11;
localparam S_TX0    = 12;
localparam S_TX1    = 13;
localparam S_TX2    = 14;
localparam S_SAVE0  = 15;
localparam S_SAVE1  = 16;
localparam S_LOAD0  = 17;
localparam S_LOAD1  = 18;
localparam S_LOAD2  = 19;

assign inst     = rom_dout;
assign rom_addr = pc_next;
assign rom_en   = state_next != S_SYNC &&
                  state_next != S_WAIT &&
                  state_next != S_HIZ &&
                  state_next != S_RX0 &&
                  state_next != S_RX1 &&
                  state_next != S_TX2 &&
                  state_next != S_LOAD1 &&
                  state_next != S_LOAD2;

assign timing_0  = timing == 0 && prescaler == 0;
assign timing_1  = timing == 1 && prescaler == 0;
assign timing_rx = timing == 2 && prescaler == 0;

assign sample       = state == S_RX1 && timing_rx;
assign transmission = state == S_TX2 && timing_0;

// following flags have to be combined with sample
assign data01  = bitaddr == 16 && (data[3:0] == 4'b0011 || data[3:0] == 4'b1011);
assign payload = nrzrxct != 6 && bitaddr > 15 && !eop;

assign busy = insth != 14;  // op!=WAIT

// branch condition
always @(*) begin
  case (inst)
    0: cond = eop || (connected && !di) || (!FULL_SPEED && (|dpi));  // op=BE
    1: cond = connected;  // op=BC
    2: cond = nak;  // op=BNAK
    3: cond = stall;  // op=BSTALL
    4: cond = wk > 0;  // op=BNZ
    5: cond = wk == 0;  // op=BZ
    6: cond = !FULL_SPEED || !full_speed;  // op=BNF
    7: cond = 1;  // op=BJMP
    default: cond = 0;
  endcase
end

// state machine sequential
always @(posedge clk) begin
  state <= state_next;
  pc    <= pc_next;
end

// state machine combinational
always @(*) begin
  pc_step = 2'd1;
  pc_override = 0;
  pc_next = 0;
  if (reset || (&conct)) begin
    state_next = S_OPCODE;
    pc_override = 1;
    pc_next    = 0;

  end else begin
    state_next = state;


    case (state)
      S_OPCODE: begin
        case (inst)
          0: ;  // op=NOP
          1: state_next = S_LDI0;  // op=LDI
          2: ;  // op=START
          3: state_next = S_TX0;  // op=OUT4
          4: ;
          5: begin
            state_next = S_HIZ;
            pc_step = 2'd0;
          end  // op=HIZ
          6: state_next = S_TX0;  // op=OUTB
          7: begin pc_override = 1; pc_next = wpc[0]; end  // op=RET
          8: state_next = S_B0;  // op=CALL
          9: state_next = S_BX;  // op=BX
          10: state_next = S_LOAD0;  // op=OUTR
          11: ;  // op=DEC
          12: state_next = S_SAVE0;  // op=SAVE
          13: begin
            state_next = S_RX0;
            pc_step = 2'd0;
          end  // op=IN
          14: begin
            state_next = S_WAIT;
            pc_step = 2'd0;
          end  // op=WAIT
          15: state_next = S_LOAD0;  // op=LOAD
          default: ;
        endcase
      end
      S_SYNC: begin
        if (timing_1)
          state_next = S_OPCODE;
        else
          pc_step = 2'd0;
      end
      S_WAIT: begin
        if (interval_frame)
          state_next = S_OPCODE;
        else
          pc_step = 2'd0;
      end
      S_LDI0: state_next = S_LDI1;
      S_LDI1: state_next = S_OPCODE;
      S_BX: begin
        if (cond)
          state_next = S_B0;
        else begin
          state_next = S_OPCODE;
          pc_step = 2'd3;
        end
      end
      S_B0: state_next = S_B1;
      S_B1: begin
        state_next = S_OPCODE;
        pc_override = 1;
        pc_next    = {inst, lb4, 2'b0};
      end
      S_RX0: begin
        // dsum == 0 is undefined
        if (!di && dsum != 0)
          state_next = S_RX1;
        else if (timeout)  // timeout
          state_next = S_SYNC;
        else
          pc_step = 2'd0;
      end
      S_HIZ: begin
        pc_step = 2'd0;
        if (timing_0)
          state_next = S_SYNC;
      end
      S_RX1: begin
        if (timing_rx && eop)
          state_next = S_SYNC;
        else
          pc_step = 2'd0;
      end
      S_TX0: state_next = S_TX1;
      S_TX1: begin
        state_next = S_TX2;
        pc_step = 2'd0;
      end
      S_TX2: begin
        if (sadr == 0 && timing_0)
          state_next = S_OPCODE;
        else
          pc_step = 2'd0;
      end
      S_SAVE0: state_next = S_SAVE1;
      S_SAVE1: state_next = S_OPCODE;
      S_LOAD0: begin
        state_next = S_LOAD1;
        pc_step = 2'd0;
      end
      S_LOAD1: begin
        state_next = S_LOAD2;
        pc_step = 2'd0;
      end
      S_LOAD2: begin
        if (insth == 10) begin  // op=OUTR
          state_next = S_TX2;
          pc_step = 2'd0;
        end else
          state_next = S_OPCODE;
      end
      default: state_next = S_OPCODE;
    endcase
  end
  if (!pc_override)
    pc_next = pc + {8'b0, pc_step};
end

always @(posedge clk) begin
  if (reset || (&conct)) begin
    conct <= 0;
    connected <= 0;descriptor_active<=0;
    timing <= 0;
    prescaler <= 0;
    bitaddr <= 0;
    nak <= 0;
    stall <= 1;
    eot <= 0;
    ug <= 0;
    interval <= 1;
    delay <= 1;
    full_speed <= FULL_SPEED;
    save <= 0;
    load <= 0;
    ukpstb <= 0;
    ukprdy <= 0;
    ukpstart <= 0;

  end else if (cs) begin
    // ensure strobe
    save <= 0;
    load <= 0;
    ukpstb <= 0;
    ukpstart <= 0;

    // div-5 prescaler for low-speed (60MHz -> 12MHz)
    if (FULL_SPEED && !full_speed)
      prescaler <= (prescaler == 4) ? 0 : prescaler + 1;
    else
      prescaler <= 0;

    // oversampling - 8 for low-speed, 5 for high-speed
    // dsum == 0 is undefined
    did <= di;
    if (!ug && did != di && dsum != 0)
      timing <= 1;
    else if (prescaler == 0) begin
      timing <= timing + 1;

      if (FULL_SPEED && full_speed && timing == 4)
        timing <= 0;
    end

    // framing
    if (interval_frame)
      interval <= 1;
    else
      interval <= interval + 1;

    // inter-packet delay
    if (!timeout && prescaler == 0)
      delay <= delay + 1;

    // WDT (data byte valid or connected and NAK)
    if (ukpstb || (connected && nak))
      conct <= 0;
    else if (interval_frame)
      conct <= conct + 1;

    // state machine register outputs
    case (state)
      S_OPCODE: begin
        insth <= inst;
        case (inst)
          0: ;  // op=NOP
          1: ;  // op=LDI
          2: begin
            ukpstart <= 1;
          end  // op=START
          3: begin
            sadr <= 3;
          end  // op=OUT4
          4: ;
          5: ;  // op=HIZ
          6: begin
            sadr <= 7;
          end  // op=OUTB
          7: begin
            wpc[0] <= wpc[1];
          end  // op=RET
          8: begin
            wpc[0] <= pc + 3;
            wpc[1] <= wpc[0];
          end  // op=CALL
          9: ;  // op=BX
          10: begin
            sadr <= 7;
          end  // op=OUTR
          11: begin
            if (wk > 0)
              wk <= wk - 1;
          end  // op=DEC
          12: ;  // op=SAVE
          13: ;  // op=IN
          14: ;  // op=WAIT
          15: ;  // op=LOAD
          default: ;
        endcase
      end
      S_SYNC: begin
        if (timing_0)
          ukprdy <= 0;
      end
      S_WAIT: ;
      S_LDI0: begin
        wk[3:0] <= inst;wk[10:8]<=0;
      end
      S_LDI1: begin
        wk[7:4] <= inst;
      end
      S_BX: begin
        case (inst)
          0: begin
            if (!cond && !connected && FULL_SPEED)
              full_speed <= dpi[0];
          end  // op=BE
          default: ;
        endcase
      end
      S_B0: begin
        lb4 <= inst;
      end
      S_B1: ;
      S_HIZ: begin
        if (timing_0) begin
          ug <= 0;
        end
      end
      S_RX0: begin
        bitaddr <= 0;
        nak     <= 0;
        stall   <= 1;
        eot     <= 0;
        nrzrxct <= 0;
        timing  <= 0;
        ukprdy  <= 0;
        dis     <= 1;
      end
      S_RX1: begin
        if (timing_rx) begin
          if (data01) begin
            wk     <= wk - 1 + 16;  // increase by size of CRC16
            ukprdy <= 1;            // mark valid packet bytes
          end else if (payload && wk > 0)
            wk <= wk - 1;
          else if (eot) begin
            ukprdy <= 0;
            delay  <= 1;
          end
        end
      end
      S_TX0: begin
        sb[3:0] <= inst;
      end
      S_TX1: begin
        sb[7:4] <= inst;
      end
      S_TX2: begin
        delay <= 1;
      end
      S_SAVE0: begin
        addra <= inst;
      end
      S_SAVE1: begin
        addrb <= inst;
        if(addra==14) descriptor_active<=inst!=0;
        else if (addra == 15) begin
          connected <= inst != 0;
          conct     <= 0;
        end else
          save <= 1;
      end
      S_LOAD0: begin
        addra <= inst;
        load  <= 1;
      end
      S_LOAD1: ;
      S_LOAD2: begin
        if(insth==15)wk <= load_data; // OUTR must preserve transfer/frame counters
        sb <= load_data;
      end
      default: ;
    endcase

    // Sampling
    if (sample) begin
      ug <= 0;
      dis <= di;
      eot <= (eop || wk == 0);  // eop or packet length
      if (bitaddr == 16) begin
        nak   <= data[3:0] == 4'b1010;
        stall <= data[3:0] == 4'b1110;
      end
      if (nrzrxct != 6 && !(&bitaddr)) begin  // ensure bitaddr won't overflow
        data[6:0] <= data[7:1];
        data[7]   <= dis == di;  // testing bit equality
        bitaddr   <= bitaddr + 1;
      end
      if (dis == di)
        nrzrxct <= nrzrxct + 1;
      else
        nrzrxct <= 0;
      // A stuffed bit holds bitaddr; defer the byte strobe to the next data bit.
      if (ukprdy && nrzrxct != 6 && bitaddr[2:0] == 3'b000) begin
        ukpdat <= data;
        if (wk >= 15)  // ignore last two bytes (CRC of last part-packet)
          ukpstb <= 1;
      end
    end

    // Microcode branches only after the complete PID/CRC/length result is available.
    if(checked_done)begin
      nak<=checked_ok && packet_pid==8'h5a;
      stall<=!checked_ok || packet_pid==8'h1e;
    end
    // Transmission
    if (transmission) begin
      ug <= 1;
      if (!ug)  // clear nrztxct when packet is initiated
        nrztxct <= 0;
      else if (dbit)
        nrztxct <= nrztxct + 1;
      else
        nrztxct <= 0;
      if (insth == 6 || insth == 10) begin  // op=OUTB, op=OUTR
        if (nrztxct != 6) begin
          up <= dbit ?  up : ~up;
          um <= dbit ? ~up :  up;
        end else begin
          up <= ~up;
          um <= up;
          nrztxct <= 0;
        end
      end else begin  // op=OUT4
        up <= sb[{sadr[2] | ~polarity, sadr[1:0]}];
        um <= sb[{sadr[2] |  polarity, sadr[1:0]}];
      end
      if (nrztxct != 6 && sadr > 0)
        sadr <= sadr - 1;
    end
  end
end

endmodule
`default_nettype wire
// vim:ts=2 sw=2 tw=120 et
