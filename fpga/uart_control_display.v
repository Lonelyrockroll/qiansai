`timescale 1ns/1ps
// Fixed 28-byte packets; stop-and-wait request/response protocol.
module uart_control_display #(
    parameter CLK_HZ=50000000, parameter BAUD=115200,
    parameter WATCHDOG_CYCLES=150000000,parameter DEFAULT_DRUM_MODE=1,
    parameter [11:0] DEFAULT_PT_BIAS=12'd1577
)(
    input wire clk,input wire rst,input wire uart_in,output wire uart_out,
    input wire bt_request,input wire [7:0] bt_command,input wire bt_locked,pmod_testing,
    input wire [15:0] bt_period,bt_count,bt_dropped,input wire [7:0] pmod_lamps,
    output wire bt_accept,output reg pmod_test,pmod_single,output reg [2:0] pmod_select,
    input wire output_limited,limiter_overrun,input wire [16:0] limiter_gain,input wire [31:0] limited_frames,
    output reg fx_command_valid,fx_monitor_mute,fx_test_valid,
    output reg [2:0] fx_mask,output reg [7:0] fx_reverb_mix,fx_delay_mix,fx_chorus_mix,fx_feedback,
    output reg [1:0] fx_delay_time,fx_room,fx_rate,fx_depth,output reg [15:0] fx_test_value,
    input wire [2:0] fx_status_mask,input wire [7:0] fx_status_reverb,fx_status_delay,fx_status_chorus,fx_status_feedback,
    input wire [1:0] fx_status_time,fx_status_room,fx_status_rate,fx_status_depth,
    input wire fx_pending,fx_busy,fx_tail,fx_overrun,fx_clipped,input wire [31:0] fx_frames,input wire [23:0] fx_clip_frames,
    output reg capture_command_valid,capture_command_arm,capture_trigger_nonzero,
    output reg [15:0] capture_length,output reg [31:0] capture_delay,
    output reg [14:0] capture_read_address,input wire [15:0] capture_read_data,
    input wire capture_busy,capture_ready,input wire [7:0] capture_flags,
    input wire [15:0] capture_id,capture_count,capture_target,capture_capacity,
    input wire [31:0] capture_first_frame,capture_checksum,
    output reg led_command_valid,output reg [1:0] led_command,
    input wire [1:0] led_mode,led_color,input wire [4:0] led_index,input wire led_preparing,led_busy,
    input wire [31:0] led_latched_mask,led_frames,
    output reg diag_command_valid,output reg [1:0] diag_command,
    input wire [1:0] diag_mode,diag_phase,input wire [5:0] diag_seconds,
    input wire sample_tick,input wire [5:0] active_voices,
    input wire signed [15:0] pcm,input wire overrun,clipped,
    output reg [11:0] pt_bias,output reg [1:0] pt_mode,
    input wire amp_muted,amp_ready,output reg [1:0] gain_mode,output reg amp_hold,
    output reg monitor_open,monitor_fade,input wire engine_cleared,output reg [1:0] monitor_demo,output reg [4:0] missing_voice,
    input wire [5:0] measured_peaks,input wire [319:0] spectrum_levels,input wire monitor_overrun,
    input wire onset_valid,input wire [15:0] onset_us,orphan_flush_count,
    input wire [4:0] measured_key,input wire [15:0] measurement_count,
    input wire [23:0] physical_ons,physical_offs,
    output reg guide_ui_valid,output reg [3:0] guide_ui_action,
    output reg score_ui_valid,output reg [1:0] score_ui_action,input wire score_ui_ready,
    input wire score_valid,score_show_requested,score_visible,score_loading,score_reserved,
    input wire [15:0] score_page_index,score_page_count,
    input wire [31:0] score_received_compressed,score_decoded_bytes,
    input wire guide_valid,guide_playing,guide_loading,guide_demo,
    input wire [15:0] guide_time_cs,guide_duration_cs,input wire [9:0] guide_count,guide_index,
    input wire [1:0] guide_speed,input wire [31:0] guide_current,
    input wire ui_valid,input wire [3:0] ui_action,input wire [15:0] ui_value,
    output reg express_adjust,express_depth,express_up,
    input wire [3:0] bend_position,input wire [2:0] vibrato_depth,
    output wire ui_ready,input wire native_panic,native_connected,input wire [4:0] native_last_event,input wire video_locked,
    input wire [63:0] native_diagnostic,input wire [31:0] native_events,
    output reg loop_command_valid,output reg [2:0] loop_command,
    input wire loop_playing,loop_recording,loop_pending,loop_full,input wire [2:0] loop_layers,loop_notice,
    input wire [1:0] loop_duration,input wire [18:0] loop_position,input wire [35:0] loop_counts,input wire [31:0] loop_replayed,
    output wire pc_pad_valid,output reg [3:0] pc_pad,input wire pc_pad_ready,
    input wire [18:0] loop_actual_length,input wire [9:0] loop_actual_cs,loop_position_cs,
    output reg live_piano_flush,output reg [15:0] drum_level,
    input wire [5:0] router_held,router_live_held,input wire [31:0] router_held_mask,router_notes,router_steals,router_ignored,
    output reg drum_mode,input wire [31:0] drum_hits,drum_limit_frames,
    input wire [11:0] drum_mask,input wire [3:0] drum_last_pad,input wire drum_overrun,drum_limited,
    input wire [5:0] drum_voices,
    output reg [3:0] ui_focus,output reg ui_pattern,ui_local,
    output reg [2:0] ui_page,output reg [3:0] ui_cursor,output reg ui_confirm,
    output wire [6:0] ui_volume,output reg [3:0] ui_notice,
    input wire key_calibrated,key_fault,input wire [31:0] key_pressed,output wire [31:0] pc_key_pressed,
    input wire [4:0] key_last,input wire [15:0] key_raw,key_base,key_delta,key_velocity,key_scans,
    output reg [1:0] key_mode,output reg [4:0] key_test,
    output reg [2:0] key_wave,output reg key_recalibrate,
    output reg [15:0] key_level,key_press,key_release,key_attack,key_decay,key_sustain,key_tail,key_scale,
    output reg panic,output wire cfg_valid,input wire cfg_ready,
    output reg [4:0] cfg_voice,output reg cfg_gate,
    output reg [31:0] cfg_step,output reg [2:0] cfg_wave,
    output reg [15:0] cfg_level,cfg_attack,cfg_decay,cfg_sustain,cfg_release
);
    localparam COLLECT=0,APPLY=1,BUILD=2,SEND=3,DRAIN=4,CLEAR=5,PAD_APPLY=6,CAP_ADDR=7,CAP_WAIT=8,CAP_LATCH=9,CHECKSUM=10,UI_APPLY=11;
    wire [7:0] rx_data;wire rx_valid,rx_error,tx_ready;
    reg [7:0] tx_data;reg tx_valid;
    uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) receiver(
        .clk(clk),.rst(rst),.rx(uart_in),.data(rx_data),.valid(rx_valid),.framing_error(rx_error));
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) transmitter(
        .clk(clk),.rst(rst),.data(tx_data),.valid(tx_valid),.ready(tx_ready),.tx(uart_out));
    reg [3:0] state;
    reg [5:0] rx_index,tx_index;
    reg [7:0] rx_buf[0:25];
    reg [7:0] tx_buf[0:27];
    reg [7:0] checksum;
    reg crc_ok;
    reg [7:0] seq,opcode,result_code;
    reg [31:0] gate_mask,command_count,frame_count;
    // CONFIG payload byte 17 tags virtual-piano events: 0x80 | physical white-key index.
    // Engineering tones remain untagged. Capture the tag for the pending APPLY handshake.
    reg panel_tagged;
    reg [4:0] panel_key;
    assign pc_key_pressed=gate_mask;
    reg [27:0] watchdog,rx_timeout;
    reg armed,timed_out;
    reg [5:0] gated_count;
    reg [7:0] response_xor;
    integer i,k;
    reg [15:0] read_capture_id,read_start;
    reg [2:0] read_count,read_index;
    reg [95:0] capture_words;
    reg ui_pending,pending_score_exit;reg [3:0] pending_action;
    reg pending_navigation,legacy_selection;
    // Changes whenever a local/host navigation intent is accepted. Short host
    // transactions can reject a click superseded by a physical control action.
    reg [7:0] ui_epoch;
    reg monitor_wait_clear;
    reg [3:0] pending_focus;reg pending_from_host;
    reg [15:0] pending_value;
    assign ui_ready=!ui_pending && state==COLLECT && rx_index==0 && !rx_valid;
    wire [3:0] action_focus=pending_action==5?pending_focus:ui_focus;
    wire [15:0] view_level=drum_mode?drum_level:key_level;
    wire [31:0] volume_product=view_level*32'd100+32'd32768;
    assign ui_volume=volume_product[22:16];
    task change_timbre(input [2:0] new_wave);
      begin
        key_wave<=new_wave;live_piano_flush<=1;gate_mask<=0;
        if(new_wave==4) begin key_attack<=672;key_decay<=2;key_sustain<=0;key_tail<=8;end
        else begin key_attack<=269;key_decay<=6;key_sustain<=40000;key_tail<=5;end
      end
    endtask
    // Direct choices and the legacy cycle share the same FX2 presets.
    task select_effect(input [2:0] new_mask);
      begin
        fx_mask<=new_mask;
        fx_reverb_mix<=0;fx_delay_mix<=0;fx_chorus_mix<=0;fx_feedback<=112;
        fx_delay_time<=3;fx_room<=2;fx_rate<=2;fx_depth<=2;
        case(new_mask)
         1:fx_reverb_mix<=128;
         2:fx_delay_mix<=128;
         4:fx_chorus_mix<=128;
         7:begin fx_reverb_mix<=64;fx_delay_mix<=64;fx_chorus_mix<=112;end
         default:begin fx_reverb_mix<=48;fx_delay_mix<=64;fx_chorus_mix<=80;
           fx_feedback<=96;fx_delay_time<=2;fx_room<=1;fx_rate<=1;fx_depth<=1;end
        endcase
        fx_command_valid<=1;
      end
    endtask
    task next_effect;
      begin
        case(fx_mask)
         0:select_effect(1);1:select_effect(2);2:select_effect(4);4:select_effect(7);default:select_effect(0);
        endcase
      end
    endtask
    // A PC request owns the binary port through its full reply. One independent
    // Bluetooth command can wait for that boundary without mixing bytes or replies.
    assign bt_accept=bt_request && ui_ready && !ui_valid && !native_panic;
    wire [15:0] view_level_limit=drum_mode?16'd16384:16'd26214;
    wire [15:0] higher_level=view_level>=view_level_limit-16'd1311 ? view_level_limit : view_level+16'd1311;
    wire [15:0] lower_level=view_level<=1311 ? 16'd0 : view_level-16'd1311;
    task switch_input_mode;
      begin drum_mode<=!drum_mode;ui_focus<=(loop_recording || loop_pending)?1:0;ui_pattern<=0;end
    endtask
    task scan_toggle;
      begin key_mode<=key_mode==0?2:0;key_recalibrate<=1;live_piano_flush<=1;gate_mask<=0;end
    endtask
    task calibrate_keys;
      begin if(key_mode==0)ui_notice<=1;else begin key_recalibrate<=1;live_piano_flush<=1;gate_mask<=0;end end
    endtask
    task loop_play_toggle;
      begin loop_command_valid<=1;loop_command<=3;
        if(!loop_playing && loop_layers!=0)begin amp_hold<=1;armed<=1;watchdog<=0;timed_out<=0;ui_local<=!pending_from_host;end
      end
    endtask
    task mute_home;
      begin
        panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;
        ui_page<=0;ui_cursor<=0;ui_confirm<=0;legacy_selection<=0;
        ui_pattern<=0;
        if(score_visible || score_show_requested)begin
          if(score_ui_ready && !score_ui_valid)begin score_ui_valid<=1;score_ui_action<=0;end
          else begin ui_pending<=1;pending_score_exit<=1;end
        end
      end
    endtask
    task toggle_performance;
      begin
        if(amp_hold)begin panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
        else begin amp_hold<=1;armed<=1;watchdog<=0;timed_out<=0;ui_local<=!pending_from_host;end
      end
    endtask
    task record_loop;
      begin
        loop_command_valid<=1;loop_command<=1;
        if(loop_layers<4 && !loop_recording && !loop_pending)begin
          amp_hold<=1;armed<=1;watchdog<=0;timed_out<=0;ui_local<=!pending_from_host;
        end
      end
    endtask
    task navigation_back;
      begin
        if(ui_page!=0)begin ui_page<=0;ui_cursor<={1'b0,ui_page};end
        ui_confirm<=0;legacy_selection<=0;
      end
    endtask
    task navigation_enter;
      begin
        legacy_selection<=0;
        if(ui_page!=0 && ui_cursor==0)navigation_back();
        else case(ui_page)
          0:if(ui_cursor==0)toggle_performance();
            else begin ui_page<=ui_cursor[2:0];ui_cursor<=1;ui_confirm<=0;end
          1:case(ui_cursor)
              1:change_timbre(4);2:change_timbre(0);3:change_timbre(1);4:change_timbre(2);5:change_timbre(3);
            endcase
          2:case(ui_cursor)
              1:select_effect(0);2:select_effect(1);3:select_effect(2);4:select_effect(4);5:select_effect(7);
            endcase
          3:case(ui_cursor)
              1:record_loop();
              2:loop_play_toggle();
              3:begin loop_command_valid<=1;loop_command<=2;end
              4:begin loop_command_valid<=1;loop_command<=4;end
              5:if(ui_confirm)begin loop_command_valid<=1;loop_command<=5;ui_confirm<=0;end else ui_confirm<=1;
            endcase
          4:case(ui_cursor)
              1:begin guide_ui_valid<=1;guide_ui_action<=4;end
              2:begin guide_ui_valid<=1;guide_ui_action<=3;end
              3:begin guide_ui_valid<=1;guide_ui_action<=8;end
              4:if(!score_valid)ui_notice<=3;
                else if(score_ui_ready && !score_ui_valid)begin score_ui_valid<=1;score_ui_action<=1;end
                else ui_pending<=1;
            endcase
          5:case(ui_cursor)
              1:scan_toggle();2:calibrate_keys();3:switch_input_mode();
              4:begin monitor_open<=1;monitor_demo<=0;end
              5:ui_pattern<=!ui_pattern;
            endcase
        endcase
      end
    endtask
    assign cfg_valid=(state==APPLY);
    assign pc_pad_valid=(state==PAD_APPLY);
    always @* gated_count=router_held+drum_voices;
    always @(posedge clk) begin
        if(rst) begin
            pmod_test<=0;pmod_single<=0;pmod_select<=0;fx_command_valid<=0;fx_monitor_mute<=0;fx_test_valid<=0;fx_test_value<=0;
            fx_mask<=0;fx_reverb_mix<=48;fx_delay_mix<=64;fx_chorus_mix<=80;fx_feedback<=96;
            fx_delay_time<=2;fx_room<=1;fx_rate<=1;fx_depth<=1;
            capture_command_valid<=0;capture_command_arm<=0;capture_trigger_nonzero<=0;
            capture_length<=0;capture_delay<=0;capture_read_address<=0;
            read_capture_id<=0;read_start<=0;read_count<=0;read_index<=0;capture_words<=0;
            led_command_valid<=0;led_command<=0;
            diag_command_valid<=0;diag_command<=0;
            state<=COLLECT;rx_index<=0;tx_index<=0;checksum<=0;crc_ok<=0;
            seq<=0;opcode<=0;result_code<=0;gate_mask<=0;command_count<=0;frame_count<=0;
            watchdog<=0;rx_timeout<=0;armed<=0;timed_out<=0;panic<=0;tx_data<=0;tx_valid<=0;gain_mode<=1;amp_hold<=0;
            monitor_open<=0;monitor_demo<=0;monitor_fade<=0;monitor_wait_clear<=0;missing_voice<=15;
            guide_ui_valid<=0;guide_ui_action<=0;score_ui_valid<=0;score_ui_action<=0;pt_bias<=DEFAULT_PT_BIAS;pt_mode<=2;express_adjust<=0;express_depth<=0;express_up<=0;
            key_mode<=0;key_test<=12;key_wave<=4;key_recalibrate<=0;
            key_level<=4588;key_press<=256;key_release<=128;key_attack<=672;
            key_decay<=2;key_sustain<=0;key_tail<=13;key_scale<=64;
            ui_focus<=0;ui_pattern<=0;ui_local<=0;ui_pending<=0;pending_score_exit<=0;pending_action<=0;ui_notice<=0;drum_mode<=DEFAULT_DRUM_MODE;drum_level<=1311;live_piano_flush<=0;loop_command_valid<=0;loop_command<=0;pc_pad<=0;
            ui_page<=0;ui_cursor<=0;ui_confirm<=0;pending_navigation<=0;legacy_selection<=0;ui_epoch<=0;
            pending_focus<=0;pending_from_host<=0;pending_value<=0;
            panel_tagged<=0;panel_key<=0;cfg_voice<=0;cfg_gate<=0;cfg_step<=0;cfg_wave<=0;cfg_level<=0;
            cfg_attack<=1;cfg_decay<=1;cfg_sustain<=0;cfg_release<=1;
            for(i=0;i<26;i=i+1) rx_buf[i]<=0;
            for(i=0;i<28;i=i+1) tx_buf[i]<=0;
        end else begin
            pmod_test<=0;fx_command_valid<=0;fx_test_valid<=0;
            capture_command_valid<=0;
            led_command_valid<=0;
            diag_command_valid<=0;
            guide_ui_valid<=0;if(score_ui_ready)score_ui_valid<=0;express_adjust<=0;panic<=0;monitor_fade<=0;tx_valid<=0;key_recalibrate<=0;live_piano_flush<=0;loop_command_valid<=0;
            if(monitor_wait_clear)begin
                if(!monitor_open || !amp_hold || panic || score_show_requested)monitor_wait_clear<=0;
                else if(engine_cleared)begin monitor_wait_clear<=0;monitor_demo<=1;end
            end
            if(sample_tick) frame_count<=frame_count+1'b1;
            if(armed && !ui_local && watchdog<WATCHDOG_CYCLES) watchdog<=watchdog+1'b1;
            if(armed && !ui_local && watchdog==WATCHDOG_CYCLES-1) begin
                panic<=1;gate_mask<=0;armed<=0;timed_out<=1;amp_hold<=0;
                ui_epoch<=ui_epoch+1'b1;
            end
            // A truncated packet cannot retain the parser indefinitely.
            if(rx_index!=0 && state==COLLECT) begin
                if(rx_timeout==CLK_HZ/20) begin rx_index<=0;rx_timeout<=0;end
                else rx_timeout<=rx_timeout+1'b1;
            end
            if(rx_error) begin rx_index<=0;rx_timeout<=0;end
            case(state)
                COLLECT: if(rx_valid) begin
                    rx_timeout<=0;
                    if(rx_index==0) begin
                        if(rx_data==8'ha5) rx_index<=1;
                    end else if(rx_index==1) begin
                        if(rx_data==8'h5a) begin rx_index<=2;checksum<=0;end
                        else if(rx_data!=8'ha5) rx_index<=0;
                    end else if(rx_index<26) begin
                        rx_buf[rx_index]<=rx_data;checksum<=checksum^rx_data;rx_index<=rx_index+1'b1;
                    end else if(rx_index==26) begin
                        crc_ok<=(rx_data==checksum);rx_index<=27;
                    end else begin
                        rx_index<=0;seq<=rx_buf[3];opcode<=rx_buf[4];
                        if(rx_data!=8'h0d || !crc_ok || rx_buf[2]!=1 || rx_buf[5]!=20) begin
                            result_code<=1;state<=BUILD;
                        end else begin
                            watchdog<=0;
                            case(rx_buf[4])
                                1,4: begin result_code<=0;state<=BUILD;end
                                2: if(key_mode!=0 || monitor_demo!=0) begin result_code<=4;state<=BUILD;end
                                else if(rx_buf[6]>=32 || rx_buf[7]>1 || rx_buf[8]>4 ||
                                       {rx_buf[14],rx_buf[13],rx_buf[12],rx_buf[11]}>(rx_buf[8]==4?32'h0ff00000:32'h0fffffff)) begin
                                    result_code<=3;state<=BUILD;
                                end else begin
                                    ui_local<=0;
                                    panel_tagged<=rx_buf[23][7:5]==3'b100;panel_key<=rx_buf[23][4:0];
                                    cfg_voice<=rx_buf[6][4:0];cfg_gate<=rx_buf[7][0];cfg_wave<=rx_buf[8][2:0];
                                    cfg_level<={rx_buf[10],rx_buf[9]};
                                    cfg_step<={rx_buf[14],rx_buf[13],rx_buf[12],rx_buf[11]};
                                    cfg_attack<={rx_buf[16],rx_buf[15]};cfg_decay<={rx_buf[18],rx_buf[17]};
                                    cfg_sustain<={rx_buf[20],rx_buf[19]};cfg_release<={rx_buf[22],rx_buf[21]};
                                    result_code<=0;state<=APPLY;
                                end
                                3: begin
                                    ui_local<=0;
                                    ui_epoch<=ui_epoch+1'b1;
                                    panic<=1;gate_mask<=0;command_count<=command_count+1'b1;
                                    amp_hold<=rx_buf[6][0] && amp_hold;
                                    armed<=rx_buf[6][0] && amp_hold;timed_out<=0;result_code<=0;state<=CLEAR;
                                end
                                5: begin
                                    if(rx_buf[6]>2) result_code<=3;
                                    else begin gain_mode<=rx_buf[6][1:0];result_code<=0;command_count<=command_count+1'b1;end
                                    state<=BUILD;
                                end
                                6: begin
                                    ui_local<=0;
                                    amp_hold<=1;armed<=1;watchdog<=0;timed_out<=0;
                                    command_count<=command_count+1'b1;result_code<=0;state<=BUILD;
                                end
                                7: begin
                                    if(rx_buf[6]>2 || rx_buf[7]>=32 || rx_buf[8]>4 ||
                                       {rx_buf[10],rx_buf[9]}>26214 ||
                                       {rx_buf[12],rx_buf[11]}>8191 ||
                                       {rx_buf[12],rx_buf[11]}<1 ||
                                       {rx_buf[14],rx_buf[13]}>={rx_buf[12],rx_buf[11]} ||
                                       {rx_buf[24],rx_buf[23]}<1 || {rx_buf[24],rx_buf[23]}>1024)
                                        begin result_code<=3;state<=BUILD;end
                                    else begin
                                        key_mode<=rx_buf[6][1:0];key_test<=rx_buf[7][4:0];key_wave<=rx_buf[8][2:0];
                                        key_level<={rx_buf[10],rx_buf[9]};key_press<={rx_buf[12],rx_buf[11]};
                                        key_release<={rx_buf[14],rx_buf[13]};key_attack<={rx_buf[16],rx_buf[15]};
                                        key_decay<={rx_buf[18],rx_buf[17]};key_sustain<={rx_buf[20],rx_buf[19]};
                                        key_tail<={rx_buf[22],rx_buf[21]};key_scale<={rx_buf[24],rx_buf[23]};
                                        key_recalibrate<=1;live_piano_flush<=1;gate_mask<=0;
                                        result_code<=0;command_count<=command_count+1'b1;state<=CLEAR;
                                    end
                                end
                                8: begin
                                    key_recalibrate<=1;live_piano_flush<=1;gate_mask<=0;
                                    result_code<=0;command_count<=command_count+1'b1;state<=CLEAR;
                                end
                                9: begin result_code<=0;state<=BUILD;end
                                10: begin
                                    if(rx_buf[6]>15 ||
                                       ((rx_buf[6]==13 || rx_buf[6]==15) && {rx_buf[8],rx_buf[7]}>1) || ((rx_buf[6]==5 || rx_buf[6]==6) && rx_buf[7]>12) ||
                                       (rx_buf[6]==7 && {rx_buf[8],rx_buf[7]}>view_level_limit) ||
                                       (rx_buf[6]==8 && rx_buf[7]>4)) result_code<=3;
                                    else if(ui_pending) result_code<=4;
                                    else begin
                                        ui_pending<=rx_buf[6]!=0;pending_action<=rx_buf[6][3:0];
                                        if(rx_buf[6]!=0)ui_epoch<=ui_epoch+1'b1;
                                        pending_navigation<=0;
                                        pending_score_exit<=rx_buf[6]==2 && score_visible;
                                        pending_focus<=rx_buf[7][3:0];pending_from_host<=1;result_code<=0;
                                        pending_value<={rx_buf[8],rx_buf[7]};
                                    end
                                    state<=BUILD;
                                end
                                11,12,13,14,16,17,19,27,29: begin result_code<=0;state<=BUILD;end
                                // Read trim (0), or write (1, uint16 little endian) with the PA safely off.
                                34:begin result_code<=0;state<=BUILD;end
                                35:begin result_code<=rx_buf[6]<=3?0:3;state<=BUILD;end
                                // Hierarchical UI. Selection and execution are separate so
                                // hosts can mirror exactly the controls on the HDMI screen.
                                36:begin
                                    state<=BUILD;
                                    if(rx_buf[6]>3 || (rx_buf[6]==1 &&
                                       (rx_buf[7]>5 || rx_buf[8]>(rx_buf[7]==4?4:5) || rx_buf[9]>1)) ||
                                       (rx_buf[6]==2 && rx_buf[7]>1))result_code<=3;
                                    else if(rx_buf[6]==0)result_code<=0;
                                    else if(ui_pending)result_code<=4;
                                    else if((rx_buf[6]==1 && rx_buf[9]==1 && rx_buf[10]!=ui_epoch) ||
                                            (rx_buf[6]==2 && rx_buf[7]==1 && rx_buf[8]!=ui_epoch))result_code<=4;
                                    else begin
                                        result_code<=0;
                                        ui_epoch<=ui_epoch+1'b1;
                                        if(rx_buf[6]==1)begin
                                            ui_page<=rx_buf[7][2:0];ui_cursor<=rx_buf[8][3:0];
                                            if(ui_page!=rx_buf[7][2:0] || ui_cursor!=rx_buf[8][3:0])ui_confirm<=0;
                                            legacy_selection<=0;
                                        end else begin
                                            ui_pending<=1;pending_navigation<=1;pending_from_host<=1;
                                            pending_action<=rx_buf[6]==2?2:0;
                                            pending_score_exit<=score_visible || score_show_requested;
                                            state<=UI_APPLY;
                                        end
                                    end
                                end
                                30:begin
                                    if(rx_buf[6]==0) result_code<=0;
                                    else if(rx_buf[6]>2 || (rx_buf[6]==1 && rx_buf[8][7:4]!=0) ||
                                            (rx_buf[6]==2 && {rx_buf[8],rx_buf[7]}>2)) result_code<=3;
                                    else if(!amp_muted || amp_hold || active_voices!=0 || gated_count!=0) result_code<=4;
                                    else begin
                                        if(rx_buf[6]==1)pt_bias<={rx_buf[8][3:0],rx_buf[7]};
                                        else pt_mode<=rx_buf[7][1:0];
                                        result_code<=0;
                                    end
                                    state<=BUILD;
                                end
                                31:begin
                                    if(rx_buf[6]>9)result_code<=3;
                                    else begin
                                        if(rx_buf[6]!=0)begin guide_ui_valid<=1;guide_ui_action<=rx_buf[6]-1'b1;end
                                        result_code<=0;
                                    end
                                    state<=CLEAR;
                                end
                                32:begin
                                    if(rx_buf[6]>3)result_code<=3;
                                    else if(rx_buf[6]!=0 && (!score_ui_ready || score_ui_valid))result_code<=4;
                                    else if(rx_buf[6]==2 && !score_valid)result_code<=4;
                                    else begin
                                        if(rx_buf[6]!=0)begin score_ui_valid<=1;score_ui_action<=rx_buf[6]-1'b1;end
                                        result_code<=0;
                                    end
                                    state<=CLEAR;
                                end
                                28:begin
                                    if(rx_buf[6]!=1 && (rx_buf[6]!=2 || rx_buf[7]>7))result_code<=3;
                                    else begin pmod_test<=1;pmod_single<=rx_buf[6]==2;pmod_select<=rx_buf[7][2:0];result_code<=0;end
                                    state<=BUILD;
                                end
                                18:begin
                                    if(rx_buf[6]>3)result_code<=3;
                                    else begin led_command<=rx_buf[6][1:0];led_command_valid<=1;result_code<=0;end
                                    state<=BUILD;
                                end
                                20:begin
                                    if(rx_buf[6]>2)result_code<=3;
                                    else begin diag_command<=rx_buf[6][1:0];diag_command_valid<=1;result_code<=0;end
                                    state<=BUILD;
                                end
                                15:begin
                                    if(rx_buf[6]>=12)begin result_code<=3;state<=BUILD;end
                                    else if(!amp_ready || monitor_demo!=0)begin result_code<=4;state<=BUILD;end
                                    else begin pc_pad<=rx_buf[6][3:0];result_code<=0;state<=PAD_APPLY;end
                                end
                                21:begin
                                    if(rx_buf[6]>1 || rx_buf[7]>1)result_code<=3;
                                    else if(rx_buf[6]==0)begin capture_command_valid<=1;capture_command_arm<=0;result_code<=0;end
                                    else if(capture_busy || score_reserved)result_code<=4;
                                    else if({rx_buf[9],rx_buf[8]}==0 || {rx_buf[9],rx_buf[8]}>capture_capacity ||
                                            {rx_buf[13],rx_buf[12],rx_buf[11],rx_buf[10]}>32'd488281)result_code<=3;
                                    else begin
                                        capture_command_valid<=1;capture_command_arm<=1;
                                        capture_trigger_nonzero<=rx_buf[7][0];capture_length<={rx_buf[9],rx_buf[8]};
                                        capture_delay<={rx_buf[13],rx_buf[12],rx_buf[11],rx_buf[10]};result_code<=0;
                                    end
                                    state<=BUILD;
                                end
                                22:begin result_code<=0;state<=BUILD;end
                                23,33:begin
                                    read_capture_id<={rx_buf[7],rx_buf[6]};read_start<={rx_buf[9],rx_buf[8]};
                                    read_count<=rx_buf[10][2:0];read_index<=0;capture_words<=0;
                                    if(rx_buf[4]==33 && (!score_valid || score_loading || {rx_buf[7],rx_buf[6]}!=score_page_index))begin result_code<=4;state<=BUILD;end
                                    else if(rx_buf[4]==23 && (!capture_ready || {rx_buf[7],rx_buf[6]}!=capture_id))begin result_code<=4;state<=BUILD;end
                                    else if(rx_buf[10]==0 || rx_buf[10]>6 ||
                                        ({1'b0,rx_buf[9],rx_buf[8]}+{9'd0,rx_buf[10]})>(rx_buf[4]==33?17'd32768:{1'b0,capture_count}))begin result_code<=3;state<=BUILD;end
                                    else begin result_code<=0;state<=CAP_ADDR;end
                                end
                                24:begin
                                    if(rx_buf[6]>7 || rx_buf[7]>128 || rx_buf[8]>128 || rx_buf[9]>128 ||
                                       ((rx_buf[6][0]?{1'b0,rx_buf[7]}:9'd0)+(rx_buf[6][1]?{1'b0,rx_buf[8]}:9'd0)>128) ||
                                       rx_buf[10]>3 || rx_buf[11]>128 || rx_buf[12]>2 || rx_buf[13]>3 || rx_buf[14]>3 || rx_buf[15]>1)result_code<=3;
                                    else begin
                                      fx_mask<=rx_buf[6][2:0];fx_reverb_mix<=rx_buf[7];fx_delay_mix<=rx_buf[8];fx_chorus_mix<=rx_buf[9];
                                      fx_delay_time<=rx_buf[10][1:0];fx_feedback<=rx_buf[11];fx_room<=rx_buf[12][1:0];fx_rate<=rx_buf[13][1:0];fx_depth<=rx_buf[14][1:0];
                                      fx_monitor_mute<=rx_buf[15][0];fx_command_valid<=1;result_code<=0;
                                    end
                                    state<=BUILD;
                                end
                                25:begin result_code<=0;state<=BUILD;end
                                26:begin
                                    if(!fx_monitor_mute || !amp_ready)result_code<=4;
                                    else if({rx_buf[7],rx_buf[6]}==0 || {rx_buf[7],rx_buf[6]}>16384)result_code<=3;
                                    else begin fx_test_value<={rx_buf[7],rx_buf[6]};fx_test_valid<=1;result_code<=0;end
                                    state<=BUILD;
                                end
                                default:begin result_code<=2;state<=BUILD;end
                            endcase
                        end
                    end
                end
                APPLY: if(cfg_ready) begin
                    if(panel_tagged)gate_mask[panel_key]<=cfg_gate;command_count<=command_count+1'b1;
                    armed<=1;watchdog<=0;timed_out<=0;state<=BUILD;
                end
                PAD_APPLY:if(!amp_ready)begin result_code<=4;state<=BUILD;end
                    else if(pc_pad_ready)begin command_count<=command_count+1'b1;state<=BUILD;end
                CAP_ADDR:begin capture_read_address<=read_start[14:0]+read_index;state<=CAP_WAIT;end
                CAP_WAIT:state<=CAP_LATCH;
                CAP_LATCH:begin
                    if(opcode==33 && (!score_valid || score_loading || read_capture_id!=score_page_index))begin result_code<=4;state<=BUILD;end
                    else begin
                        capture_words[read_index*16 +:16]<=capture_read_data;
                        if(read_index+1'b1==read_count)state<=BUILD;
                        else begin read_index<=read_index+1'b1;state<=CAP_ADDR;end
                    end
                end
                CLEAR: state<=BUILD;
                UI_APPLY:if(!ui_pending)state<=BUILD;
                BUILD: begin
                    // Snapshot actual FPGA state; status is not inferred from host clicks.
                    tx_buf[0]=8'h5a;tx_buf[1]=8'ha5;tx_buf[2]=1;
                    tx_buf[3]=seq;tx_buf[4]=8'h80;tx_buf[5]=20;
                    // A same-edge sheet BEGIN can acquire the RAM before the
                    // registered capture-arm pulse reaches pcm_capture.
                    tx_buf[6]=result_code;tx_buf[7]=gated_count;tx_buf[8]=active_voices;
                    tx_buf[9]={amp_hold,gain_mode,amp_ready,amp_muted,timed_out,clipped,overrun};
                    tx_buf[10]=command_count[7:0];tx_buf[11]=command_count[15:8];
                    tx_buf[12]=command_count[23:16];tx_buf[13]=command_count[31:24];
                    tx_buf[14]=frame_count[7:0];tx_buf[15]=frame_count[15:8];
                    tx_buf[16]=frame_count[23:16];tx_buf[17]=frame_count[31:24];
                    tx_buf[18]=pcm[7:0];tx_buf[19]=pcm[15:8];
                    tx_buf[20]=8'hdd;tx_buf[21]=8'h0e;tx_buf[22]=8'he9;tx_buf[23]=8'h02;
                    // 0x02e90edd = 48828125 milli-Hz.
                    if(opcode==9) begin
                        tx_buf[7]={6'b0,key_mode};tx_buf[8]={6'b0,key_fault,key_calibrated};
                        tx_buf[9]={3'b0,key_last};
                        tx_buf[10]=key_raw[7:0];tx_buf[11]=key_raw[15:8];
                        tx_buf[12]=key_base[7:0];tx_buf[13]=key_base[15:8];
                        tx_buf[14]=key_delta[7:0];tx_buf[15]=key_delta[15:8];
                        tx_buf[16]=key_velocity[7:0];tx_buf[17]=key_velocity[15:8];
                        tx_buf[18]=key_pressed[7:0];tx_buf[19]=key_pressed[15:8];
                        tx_buf[20]=key_pressed[23:16];tx_buf[21]=key_pressed[31:24];
                        tx_buf[22]=key_scans[7:0];tx_buf[23]=key_scans[15:8];
                    end
                    if(opcode==11) begin
                        tx_buf[7]={4'b0,ui_focus};tx_buf[8]={5'b0,key_wave};tx_buf[9]={1'b0,ui_volume};
                        tx_buf[10]={1'b0,video_locked,ui_local,ui_pattern,amp_hold,amp_muted,key_fault,key_calibrated};
                        tx_buf[11]={6'b0,key_mode};tx_buf[12]={4'b0,ui_notice};tx_buf[13]={2'b0,active_voices};
                        tx_buf[14]=view_level[7:0];tx_buf[15]=view_level[15:8];
                        tx_buf[16]=key_press[7:0];tx_buf[17]=key_press[15:8];
                        tx_buf[18]=key_release[7:0];tx_buf[19]=key_release[15:8];
                        tx_buf[20]=key_scale[7:0];tx_buf[21]=key_scale[15:8];
                        tx_buf[22]={6'd0,drum_mode,native_connected};tx_buf[23]={3'd0,native_last_event};
                    end
                    if(opcode==30) begin tx_buf[7]=pt_bias[7:0];tx_buf[8]={4'b0,pt_bias[11:8]};tx_buf[9]={6'b0,pt_mode};end
                    tx_buf[24]=32;tx_buf[25]=opcode;

                    if(opcode==12)begin
                        tx_buf[7]={7'd0,native_connected};tx_buf[8]={3'd0,native_last_event};tx_buf[9]={1'b1,vibrato_depth,bend_position};
                        for(i=0;i<8;i=i+1)tx_buf[10+i]=native_diagnostic[i*8 +: 8];
                        for(i=0;i<4;i=i+1)tx_buf[18+i]=native_events[i*8 +: 8];
                        tx_buf[22]=0;tx_buf[23]=0;
                    end
                    if(opcode==13)begin
                        tx_buf[7]={1'b0,drum_limited,drum_overrun,amp_ready,amp_muted,amp_hold,native_connected,1'b1};
                        tx_buf[8]={4'd0,drum_last_pad};tx_buf[9]={2'd0,drum_voices};
                        for(i=0;i<4;i=i+1)begin tx_buf[10+i]=drum_hits[i*8 +: 8];tx_buf[14+i]=drum_limit_frames[i*8 +: 8];end
                        tx_buf[18]=drum_mask[7:0];tx_buf[19]={4'd0,drum_mask[11:8]};
                        tx_buf[20]=drum_level[7:0];tx_buf[21]=drum_level[15:8];tx_buf[22]=0;tx_buf[23]=0;
                    end
                    if(opcode==14)begin
                        tx_buf[7]={2'd0,amp_hold,loop_full,loop_pending,loop_recording,loop_playing,(loop_layers!=0)};
                        tx_buf[8]={5'd0,loop_layers};tx_buf[9]={6'd0,loop_duration};
                        tx_buf[10]=loop_position[7:0];tx_buf[11]=loop_position[15:8];tx_buf[12]={5'd0,loop_position[18:16]};
                        tx_buf[13]={5'd0,loop_notice};
                        for(i=0;i<4;i=i+1)begin tx_buf[14+2*i]=loop_counts[i*9 +: 8];tx_buf[15+2*i]={7'd0,loop_counts[i*9+8]};end
                        tx_buf[22]=loop_replayed[7:0];tx_buf[23]=loop_replayed[15:8];
                    end
                    if(opcode==16)begin
                        tx_buf[7]={7'd0,drum_mode};tx_buf[8]={7'd0,(loop_layers!=0)};tx_buf[9]={5'd0,key_wave};
                        tx_buf[10]=loop_actual_length[7:0];tx_buf[11]=loop_actual_length[15:8];tx_buf[12]={5'd0,loop_actual_length[18:16]};
                        tx_buf[13]=loop_actual_cs[7:0];tx_buf[14]={6'd0,loop_actual_cs[9:8]};
                        tx_buf[15]=loop_position_cs[7:0];tx_buf[16]={6'd0,loop_position_cs[9:8]};
                        tx_buf[17]=drum_level[7:0];tx_buf[18]=drum_level[15:8];tx_buf[19]=key_level[7:0];tx_buf[20]=key_level[15:8];
                        tx_buf[21]={6'd0,key_mode};tx_buf[22]={6'd0,key_fault,key_calibrated};tx_buf[23]=0;
                    end
                    if(opcode==17)begin
                        tx_buf[7]={2'd0,router_held};tx_buf[8]={2'd0,router_live_held};tx_buf[9]=router_held-router_live_held;
                        for(i=0;i<4;i=i+1)begin tx_buf[10+i]=router_notes[i*8 +: 8];tx_buf[14+i]=router_steals[i*8 +: 8];tx_buf[18+i]=router_held_mask[i*8 +: 8];end
                        tx_buf[22]=router_ignored[7:0];tx_buf[23]=router_ignored[15:8];
                    end
                    if(opcode==19)begin
                        tx_buf[7]={6'd0,led_mode};tx_buf[8]={3'd0,led_index};tx_buf[9]={6'd0,led_color};
                        tx_buf[10]={4'd0,key_fault,key_calibrated,led_busy,led_preparing};tx_buf[11]=8;
                        for(i=0;i<4;i=i+1)begin tx_buf[12+i]=led_latched_mask[i*8 +: 8];tx_buf[16+i]=led_frames[i*8 +: 8];end
                        tx_buf[20]={6'd0,key_mode};tx_buf[21]={6'd0,diag_mode};tx_buf[22]={6'd0,diag_phase};tx_buf[23]={2'd0,diag_seconds};
                    end
                    if(opcode==22)begin
                        tx_buf[7]=capture_flags;tx_buf[8]=capture_id[7:0];tx_buf[9]=capture_id[15:8];
                        tx_buf[10]=capture_count[7:0];tx_buf[11]=capture_count[15:8];
                        tx_buf[12]=capture_target[7:0];tx_buf[13]=capture_target[15:8];
                        for(i=0;i<4;i=i+1)begin tx_buf[14+i]=capture_first_frame[i*8+:8];tx_buf[18+i]=capture_checksum[i*8+:8];end
                        tx_buf[22]=capture_capacity[7:0];tx_buf[23]=capture_capacity[15:8];
                    end
                    if(opcode==23 || opcode==33)begin
                        tx_buf[7]=read_capture_id[7:0];tx_buf[8]=read_capture_id[15:8];
                        tx_buf[9]=read_start[7:0];tx_buf[10]=read_start[15:8];
                        tx_buf[11]=result_code==0?{5'd0,read_count}:8'd0;
                        for(i=0;i<12;i=i+1)tx_buf[12+i]=capture_words[i*8+:8];
                    end
                    if(opcode==25)begin
                        tx_buf[7]={5'd0,fx_status_mask};tx_buf[8]=fx_status_reverb;tx_buf[9]=fx_status_delay;tx_buf[10]=fx_status_chorus;
                        tx_buf[11]={6'd0,fx_status_time};tx_buf[12]=fx_status_feedback;tx_buf[13]={6'd0,fx_status_room};
                        tx_buf[14]={6'd0,fx_status_rate};tx_buf[15]={6'd0,fx_status_depth};
                        tx_buf[16]={2'b01,fx_monitor_mute,fx_tail,fx_overrun,fx_clipped,fx_busy,fx_pending};
                        for(i=0;i<4;i=i+1)tx_buf[17+i]=fx_frames[i*8+:8];
                        for(i=0;i<3;i=i+1)tx_buf[21+i]=fx_clip_frames[i*8+:8];
                    end
                    if(opcode==29)begin
                        tx_buf[7]={6'd0,pmod_testing,bt_locked};tx_buf[8]=pmod_lamps;
                        tx_buf[9]=bt_period[7:0];tx_buf[10]=bt_period[15:8];
                        tx_buf[11]=bt_count[7:0];tx_buf[12]=bt_count[15:8];
                        tx_buf[13]=bt_dropped[7:0];tx_buf[14]=bt_dropped[15:8];
                        tx_buf[15]=1;for(i=16;i<=23;i=i+1)tx_buf[i]=0;
                    end
                    if(opcode==27)begin
                        tx_buf[7]=4;tx_buf[8]={6'd0,limiter_overrun,output_limited};tx_buf[9]={6'd0,gain_mode};
                        tx_buf[10]=limiter_gain[7:0];tx_buf[11]=limiter_gain[15:8];tx_buf[12]={7'd0,limiter_gain[16]};
                        for(i=0;i<4;i=i+1)tx_buf[13+i]=limited_frames[i*8 +: 8];
                        tx_buf[17]=8'h60;tx_buf[18]=8'h6d;
                        tx_buf[19]=key_level[7:0];tx_buf[20]=key_level[15:8];tx_buf[21]=drum_level[7:0];tx_buf[22]=drum_level[15:8];tx_buf[23]=40;
                    end
                    if(opcode==31)begin
                        tx_buf[7]={4'b0,guide_demo,guide_loading,guide_playing,guide_valid};tx_buf[8]={6'b0,guide_speed};
                        tx_buf[9]=guide_count[7:0];tx_buf[10]={6'b0,guide_count[9:8]};
                        tx_buf[11]=guide_index[7:0];tx_buf[12]={6'b0,guide_index[9:8]};
                        tx_buf[13]=guide_time_cs[7:0];tx_buf[14]=guide_time_cs[15:8];
                        tx_buf[15]=guide_duration_cs[7:0];tx_buf[16]=guide_duration_cs[15:8];
                        for(i=0;i<4;i=i+1)tx_buf[17+i]=guide_current[i*8 +:8];
                        tx_buf[21]=0;tx_buf[22]=0;tx_buf[23]=0;
                    end
                    if(opcode==32)begin
                        tx_buf[7]={3'd0,score_visible,score_reserved,score_loading,score_show_requested,score_valid};
                        tx_buf[8]=score_page_index[7:0];tx_buf[9]=score_page_index[15:8];
                        tx_buf[10]=score_page_count[7:0];tx_buf[11]=score_page_count[15:8];
                        for(i=0;i<4;i=i+1)begin tx_buf[12+i]=score_received_compressed[i*8+:8];tx_buf[16+i]=score_decoded_bytes[i*8+:8];end
                        for(i=20;i<24;i=i+1)tx_buf[i]=0;
                    end
                    if(opcode==34)begin
                        tx_buf[7]={3'd0,onset_valid,monitor_overrun,monitor_demo,monitor_open};
                        tx_buf[8]={3'd0,missing_voice};tx_buf[9]={2'd0,measured_peaks};
                        tx_buf[10]=onset_us[7:0];tx_buf[11]=onset_us[15:8];tx_buf[12]={2'd0,active_voices};
                        tx_buf[13]=orphan_flush_count[7:0];tx_buf[14]=orphan_flush_count[15:8];
                        tx_buf[15]={3'd0,measured_key};tx_buf[16]=measurement_count[7:0];tx_buf[17]=measurement_count[15:8];
                        for(i=0;i<3;i=i+1)begin tx_buf[18+i]=physical_ons[i*8+:8];tx_buf[21+i]=physical_offs[i*8+:8];end
                    end
                    if(opcode==35)begin
                        tx_buf[7]=rx_buf[6];
                        for(i=0;i<16;i=i+1)tx_buf[8+i]={3'd0,spectrum_levels[(rx_buf[6][1:0]*16+i)*5+:5]};
                    end
                    if(opcode==36)begin
                        tx_buf[7]={5'd0,ui_page};tx_buf[8]={4'd0,ui_cursor};
                        tx_buf[9]={4'd0,ui_pending,score_visible,monitor_open,ui_confirm};
                        tx_buf[10]=ui_page==4?5:6;tx_buf[11]={4'd0,ui_focus};tx_buf[12]=1;
                        tx_buf[13]=ui_epoch;for(i=14;i<24;i=i+1)tx_buf[i]=0;
                    end
                    tx_buf[27]=8'h0d;tx_index<=0;state<=CHECKSUM;
                    if(opcode==21 && rx_buf[6]==1 && score_reserved)tx_buf[6]=4;
                    if(opcode==33 && (!score_valid || score_loading || read_capture_id!=score_page_index))begin tx_buf[6]=4;tx_buf[11]=0;end
                end
                CHECKSUM:begin
                    response_xor=0;
                    for(i=2;i<26;i=i+1)response_xor=response_xor^tx_buf[i];
                    tx_buf[26]<=response_xor;state<=SEND;
                end
                SEND: if(tx_ready && !tx_valid) begin
                    tx_data<=tx_buf[tx_index];tx_valid<=1;
                    if(tx_index==27) state<=DRAIN;else tx_index<=tx_index+1'b1;
                end
                DRAIN: if(tx_ready && !tx_valid) state<=COLLECT;
                default:state<=COLLECT;
            endcase
            // Local actions wait for a packet boundary; status commands do not take ownership.
            if(ui_valid && (!ui_pending || ui_action==3)) begin
                ui_pending<=1;pending_action<=ui_action;
                ui_epoch<=ui_epoch+1'b1;
                pending_navigation<=0;
                pending_score_exit<=ui_action==2 && score_visible;
                pending_from_host<=0;pending_focus<=ui_value[3:0];pending_value<=ui_value;
            end
            if(ui_pending && !(ui_valid && ui_action==3) && (state==COLLECT || state==UI_APPLY) && rx_index==0 && !rx_valid) begin
                ui_pending<=0;ui_notice<=0;
                // A short B / KEY.0 returns from the sheet without activating
                // whichever synth menu happened to be selected underneath it.
                if(pending_score_exit || (score_visible && pending_action==2))begin
                    pending_score_exit<=0;
                    if(score_visible || score_show_requested)begin
                        if(score_ui_ready)begin score_ui_valid<=1;score_ui_action<=0;end
                        else begin ui_pending<=1;pending_score_exit<=1;end
                    end
                end else if(monitor_open)begin
                    case(pending_action)
                     0:if(pending_navigation)begin
                         monitor_open<=0;monitor_demo<=0;monitor_wait_clear<=0;
                         if(monitor_demo!=0 || monitor_wait_clear)begin panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
                       end
                     1,9:if(monitor_demo==0)begin monitor_open<=0;
                            if(monitor_wait_clear)begin monitor_wait_clear<=0;panic<=1;amp_hold<=0;armed<=0;ui_local<=0;end
                         end
                         else begin monitor_demo<=2;missing_voice<=pending_action==1?missing_voice+1'b1:missing_voice-1'b1;end
                     2:case(monitor_demo)
                        0:if(!monitor_wait_clear && !loop_playing && !loop_recording && !loop_pending)begin
                             missing_voice<=15;amp_hold<=1;armed<=1;ui_local<=1;watchdog<=0;timed_out<=0;
                             if(amp_ready && (router_held!=0 || active_voices!=0 || fx_tail || fx_pending))begin
                                 monitor_fade<=1;monitor_wait_clear<=1;
                             end else monitor_demo<=1;
                          end
                        1:monitor_demo<=2;
                        default:begin monitor_demo<=0;panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
                       endcase
                     3:begin monitor_open<=0;monitor_demo<=0;monitor_wait_clear<=0;mute_home();end
                     7:if(drum_mode)drum_level<=pending_value;else key_level<=pending_value;
                     13,15:if(monitor_demo==0)begin express_adjust<=1;express_depth<=pending_action==15;express_up<=pending_value[0];end
                    endcase
                end else case(pending_action)
                0:if(pending_navigation)navigation_back();
                1:begin ui_cursor<=ui_cursor==(ui_page==4?4:5)?0:ui_cursor+1'b1;ui_confirm<=0;legacy_selection<=0;end
                9:begin ui_cursor<=ui_cursor==0?(ui_page==4?4:5):ui_cursor-1'b1;ui_confirm<=0;legacy_selection<=0;end
                10:change_timbre(key_wave==0?3'd4:key_wave-1'b1);
                11:scan_toggle();
                12:calibrate_keys();
                13,15:begin express_adjust<=1;express_depth<=pending_action==15;express_up<=pending_value[0];end
                14:switch_input_mode();
                4:ui_pattern<=!ui_pattern;
                6:begin ui_focus<=pending_focus;legacy_selection<=1;ui_confirm<=0;end
                7:if(drum_mode)drum_level<=pending_value;else key_level<=pending_value;
                8:if(key_wave!=pending_value[2:0]) change_timbre(pending_value[2:0]);
                3:mute_home();
                2,5:begin
                  if(pending_action==2 && (pending_navigation || !pending_from_host || !legacy_selection))navigation_enter();
                  else begin
                   if(pending_action==5)begin ui_focus<=pending_focus;legacy_selection<=0;ui_confirm<=0;end
                   case(action_focus)
                    0:toggle_performance();
                    1:record_loop();
                    2:if(drum_mode)begin loop_command_valid<=1;loop_command<=2;end
                      else change_timbre(key_wave==4?3'd0:key_wave+1'b1);
                    3:if(drum_mode)loop_play_toggle();else scan_toggle();
                    4:if(drum_mode)begin loop_command_valid<=1;loop_command<=4;end else calibrate_keys();
                    5:if(drum_mode)begin loop_command_valid<=1;loop_command<=5;end else loop_play_toggle();
                    6:begin panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
                    7:switch_input_mode();
                    8:next_effect();
                    9:begin guide_ui_valid<=1;guide_ui_action<=4;end
                    10:begin guide_ui_valid<=1;guide_ui_action<=5;end
                    11:begin guide_ui_valid<=1;guide_ui_action<=3;end
                    12:begin monitor_open<=1;monitor_demo<=0;end
                   endcase
                  end
                end
                endcase
            end
            if(bt_accept)begin
                ui_epoch<=ui_epoch+1'b1;
                case(bt_command)
                    "+":if(drum_mode)drum_level<=higher_level;else key_level<=higher_level;
                    "-":if(drum_mode)drum_level<=lower_level;else key_level<=lower_level;
                    "T":change_timbre(key_wave==4?3'd0:key_wave+1'b1);
                    "F":next_effect();
                    "L":begin pmod_test<=1;pmod_single<=0;end
                    "M":begin panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
                endcase
            end
            if(panic)monitor_demo<=0;
            if(score_show_requested && monitor_open)begin
                monitor_open<=0;
                if(monitor_demo!=0)begin monitor_demo<=0;panic<=1;amp_hold<=0;armed<=0;gate_mask<=0;ui_local<=0;end
            end
            if(native_panic)begin monitor_open<=0;monitor_demo<=0;mute_home();ui_epoch<=ui_epoch+1'b1;ui_pending<=0;pending_score_exit<=0;end
            if(key_fault && !drum_mode)ui_notice<=2;
        end
    end
endmodule
