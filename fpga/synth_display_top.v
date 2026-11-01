`timescale 1ns/1ps
module synth_display_top(
    input wire sys_clk,input wire bt_rx,output wire bt_tx,output wire [7:0] led_n,input wire uart_rx,output wire uart_tx,inout wire usb_dp,usb_dm,
    output wire HP_BCK,HP_WS,HP_DIN,PA_EN,
    output wire [4:0] key_addr,output wire key_cs_n,key_wr_n,keyboard_led,
    output wire i2s_bclk,i2s_lrclk,i2s_data,debug_sample,
    input wire key0_n,key1_n,output wire hpd_en,
    output wire tmds_clk_p,tmds_clk_n,output wire [2:0] tmds_data_p,tmds_data_n
);
    reg [15:0] startup=0;
    reg rst=1;
    always @(posedge sys_clk) begin
        if(!(&startup)) startup<=startup+1'b1;
        else rst<=0;
    end
    wire uart_panic,panic,tick,cfg_valid,cfg_ready,cfg_gate;
    wire drum_mode,drum_hit_valid,drum_hit_ready,drum_engine_ready,drum_busy,drum_overrun,drum_limited;
    wire [3:0] drum_hit_pad,drum_last_pad;wire [11:0] drum_mask;wire [5:0] drum_voices,music_voices;
    wire [31:0] drum_hits,drum_limit_frames;wire signed [23:0] drum_mix,music_mix;
    wire loop_playing,loop_recording,loop_pending,loop_full,loop_command_valid;
    wire [2:0] loop_command,loop_layers,loop_notice;wire [1:0] loop_duration;
    wire [18:0] loop_position;wire [6:0] loop_progress;wire [35:0] loop_counts;wire [31:0] loop_replayed;
    wire loop_live_ready,event_valid,event_ready,pc_pad_valid,pc_pad_ready;wire [3:0] pc_pad;
    wire [122:0] event_data;wire [2:0] event_source;
    reg queued_valid=0;reg [122:0] queued_data=0;reg [2:0] queued_source=0;
    wire router_ready;wire event_queue_ready=!queued_valid && !panic && !amp_muting;
    wire routed_drum_valid;wire [3:0] routed_drum_pad;
    wire routed_cfg_valid,routed_gate,routed_restart;wire [4:0] routed_voice;wire [31:0] routed_step,music_active_mask;
    wire [2:0] routed_wave;wire [15:0] routed_level,routed_attack,routed_decay,routed_sustain,routed_release;
    wire [31:0] held_mask,router_events,router_notes,router_steals,router_ignored;
    wire [5:0] held_count,live_held_count;wire control_live_flush;
    reg live_flush_pending=0;
    wire [18:0] loop_actual_length;wire [9:0] loop_actual_cs,loop_position_cs;
    wire [15:0] drum_level;
    always @(posedge sys_clk)begin
        if(rst || panic || clear_engine)queued_valid<=0;
        else begin
            if(queued_valid && router_ready)queued_valid<=0;
            // Data can be sampled whenever the slot is empty; only valid marks an accepted event.
            if(!queued_valid)begin queued_data<=event_data;queued_source<=event_source;end
            if(event_valid && event_queue_ready)queued_valid<=1;
        end
    end
    wire [1:0] key_mode;wire [4:0] key_test,key_last;
    wire [2:0] key_wave;
    wire key_recalibrate,key_calibrated,key_fault,key_cv,key_cr,key_gate;
    wire [4:0] key_voice;wire [31:0] key_step,key_pressed;
    wire [15:0] key_level,key_press,key_release,key_attack,key_decay,key_sustain,key_tail,key_scale;
    wire [15:0] key_cv_level,key_raw,key_base,key_delta,key_velocity,key_scans;
    wire adc_soc,adc_eoc;wire [12:0] adc_data;
    reg fault_old=0;
    always @(posedge sys_clk) if(rst) fault_old<=0;else fault_old<=key_fault;
    assign panic=uart_panic;
    wire engine_ready,amp_ready,amp_muting,clear_engine,output_clipped;
    wire led_command_valid,led_preparing,led_busy;wire [1:0] led_command,led_mode,led_color;
    wire [4:0] led_index;wire [31:0] led_latched_mask,led_frames;
    wire led_data,diag_command_valid,diag_blank,diag_reset;wire [1:0] diag_command,diag_mode,diag_phase;wire [5:0] diag_seconds;
    led_pin_diagnostic pin_diag(.clk(sys_clk),.rst(rst),.cancel(panic),
      .command_valid(diag_command_valid),.command(diag_command),.normal_data(led_data),.pin_data(keyboard_led),
      .blank_chain(diag_blank),.reset_chain(diag_reset),.mode(diag_mode),.phase(diag_phase),.seconds_left(diag_seconds));
    keyboard_lights lights(.clk(sys_clk),.rst(rst || diag_reset),.stop(diag_blank),
      .command_valid(led_command_valid),.command(led_command),.pressed(key_pressed),
      .keys_valid(key_mode!=0 && key_calibrated && !key_fault),.dout(led_data),
      .mode(led_mode),.index(led_index),.color_phase(led_color),.preparing(led_preparing),
      .tx_busy(led_busy),.latched_mask(led_latched_mask),.frames(led_frames));
    wire uart_amp_hold;
    wire amp_hold=uart_amp_hold;
    wire [1:0] gain_mode;
    reg signed [25:0] mix_total=0;
    wire signed [25:0] boosted_music=$signed({{2{music_mix[23]}},music_mix})<<<2;
    always @(posedge sys_clk)if(rst || clear_engine)mix_total<=0;else mix_total<=boosted_music+$signed({{2{drum_mix[23]}},drum_mix});
    // Four times the 32-voice sum plus bounded drums still fits signed 24 bits.
    wire signed [23:0] mix_sum=mix_total[23:0];
    wire output_limited,limiter_overrun;wire [16:0] limiter_gain;wire [31:0] limited_frames;
    wire performance_live_valid;wire [122:0] performance_live_data;
    performance_looper looper(.clk(sys_clk),.rst(rst),.sample_tick(tick),.session(uart_amp_hold),
      .audio_ready(amp_ready && !amp_muting),.stop(panic),
      .command_valid(loop_command_valid),.command(loop_command),
      .live_valid(performance_live_valid),.live_data(performance_live_data),.live_ready(loop_live_ready),
      .out_valid(event_valid),.out_data(event_data),.out_source(event_source),.out_ready(event_queue_ready),
      .playing(loop_playing),.recording(loop_recording),.pending_record(loop_pending),.layers(loop_layers),.duration_index(loop_duration),
      .position(loop_position),.progress(loop_progress),.notice(loop_notice),.event_full(loop_full),.layer_counts(loop_counts),.replayed_events(loop_replayed),
      .actual_length(loop_actual_length),.actual_cs(loop_actual_cs),.position_cs(loop_position_cs));
    performance_router router(.clk(sys_clk),.rst(rst),.clear(clear_engine),.cancel(panic),
      .event_valid(queued_valid && !panic && !amp_muting),.event_ready(router_ready),.event_data(queued_data),.event_source(queued_source),
      .drum_valid(routed_drum_valid),.drum_ready(drum_engine_ready),.drum_pad(routed_drum_pad),
      .cfg_valid(routed_cfg_valid),.cfg_ready(engine_ready),.cfg_voice(routed_voice),.cfg_gate(routed_gate),.cfg_restart(routed_restart),
      .cfg_step(routed_step),.cfg_wave(routed_wave),.cfg_level(routed_level),.cfg_attack(routed_attack),.cfg_decay(routed_decay),.cfg_sustain(routed_sustain),.cfg_release(routed_release),
      .voice_active_mask(music_active_mask),.held_mask(held_mask),.held_count(held_count),.live_held_count(live_held_count),
      .events_applied(router_events),.notes_applied(router_notes),.steals(router_steals),.ignored_offs(router_ignored));
    drum_engine drums(.clk(sys_clk),.rst(rst),.clear(clear_engine),.sample_tick(tick),
      .hit_valid(routed_drum_valid && !panic && !amp_muting),.hit_ready(drum_engine_ready),.hit_pad(routed_drum_pad),.level(drum_level),.gain_mode(gain_mode),
      .mix_sum(drum_mix),.active_mask(drum_mask),.active_voices(drum_voices),.busy(drum_busy),.overrun(drum_overrun),
      .limited(drum_limited),.hit_count(drum_hits),.limited_frames(drum_limit_frames),.last_pad(drum_last_pad));
    wire [4:0] cfg_voice;
    wire [31:0] cfg_step;
    wire [2:0] cfg_wave;
    wire [15:0] cfg_level,cfg_attack,cfg_decay,cfg_sustain,cfg_release;
    wire signed [15:0] pcm,engine_pcm,dry_pcm;
    wire fx_cv,fx_monitor_mute,fx_test_valid,fx_busy,fx_pending,fx_tail,fx_overrun,fx_clipped,fx_valid;
    wire [2:0] fx_mask,fx_status_mask;
    wire [7:0] fx_r,fx_d,fx_c,fx_fb,fx_sr,fx_sd,fx_sc,fx_sfb;
    wire [1:0] fx_time,fx_room,fx_rate,fx_depth,fx_stime,fx_sroom,fx_srate,fx_sdepth;
    wire [15:0] fx_test_value;wire [31:0] fx_frames;wire [23:0] fx_clip_frames;
    wire amp_disable_logic;
    reg fx_test_pending=0;reg signed [15:0] fx_test_sample=0;
    always @(posedge sys_clk)begin
      if(rst || clear_engine)begin fx_test_pending<=0;fx_test_sample<=0;end
      else if(fx_test_valid)begin fx_test_pending<=1;fx_test_sample<=fx_test_value;end
      else if(tick)fx_test_pending<=0;
    end
    assign PA_EN=amp_disable_logic || fx_monitor_mute;
    audio_effects effects(.clk(sys_clk),.rst(rst),.clear(clear_engine),.sample_tick(tick),
      .audio_enable(amp_ready && !amp_muting),.dry_pcm(fx_test_pending?fx_test_sample:dry_pcm),
      .cfg_valid(fx_cv),.cfg_mask(fx_mask),.cfg_reverb_mix(fx_r),.cfg_delay_mix(fx_d),.cfg_chorus_mix(fx_c),
      .cfg_feedback(fx_fb),.cfg_delay_time(fx_time),.cfg_room(fx_room),.cfg_rate(fx_rate),.cfg_depth(fx_depth),
      .pcm(pcm),.valid(fx_valid),.busy(fx_busy),.pending(fx_pending),.tail_active(fx_tail),.overrun(fx_overrun),
      .clipped(fx_clipped),.clipped_frames(fx_clip_frames),.frames(fx_frames),.mask(fx_status_mask),
      .reverb_mix(fx_sr),.delay_mix(fx_sd),.chorus_mix(fx_sc),.feedback(fx_sfb),.delay_time(fx_stime),
      .room(fx_sroom),.rate(fx_srate),.depth(fx_sdepth));
    wire cap_cv,cap_arm,cap_trigger,cap_busy,cap_ready;
    wire [15:0] cap_length,cap_data,cap_id,cap_count,cap_target,cap_capacity;
    wire [31:0] cap_delay,cap_first,cap_crc;wire [14:0] cap_address;wire [7:0] cap_flags;
    pcm_capture capture(.clk(sys_clk),.rst(rst),.sample_tick(tick),.pcm(pcm),
      .command_valid(cap_cv),.command_arm(cap_arm),.trigger_nonzero(cap_trigger),
      .requested_length(cap_length),.requested_delay(cap_delay),.read_address(cap_address),.read_data(cap_data),
      .busy(cap_busy),.ready(cap_ready),.flags(cap_flags),.capture_id(cap_id),.count(cap_count),.target_length(cap_target),
      .first_frame(cap_first),.checksum(cap_crc),.capacity(cap_capacity));
    wire ui_valid,ui_pattern,ui_local;wire [3:0] ui_action,ui_notice;
    wire button_valid,native_valid,native_ready,ui_ready,native_panic,native_connected;wire [3:0] button_action,native_action;wire [15:0] native_value;wire [4:0] native_last_event;wire [31:0] native_events;
    wire [63:0] native_diagnostic;
    assign ui_valid=button_valid || (native_valid && native_ready);assign ui_action=button_valid?button_action:native_action;
    assign native_ready=ui_ready && !button_valid;
    native_usb_bridge native_usb(.sys_clk(sys_clk),.rst(rst),.usb_dp(usb_dp),.usb_dm(usb_dm),
      .current_level(drum_mode?drum_level:key_level),.current_timbre(key_wave),.drum_mode(drum_mode),
      .drum_hit_ready(drum_hit_ready),.drum_hit_valid(drum_hit_valid),.drum_hit_pad(drum_hit_pad),
      .command_ready(native_ready),.command_valid(native_valid),.command_action(native_action),.command_value(native_value),
      .disconnect_pulse(native_panic),.connected(native_connected),.event_count(native_events),.last_event(native_last_event),.diagnostic(native_diagnostic));
    wire express_adjust,express_depth,express_up;
    wire [3:0] bend_position;wire [2:0] vibrato_depth;wire signed [13:0] pitch_offset;
    pitch_expression expression_ctrl(.clk(sys_clk),.rst(rst),.tick(tick),.clear(panic || native_panic),
        .adjust(express_adjust),.select_depth(express_depth),.increase(express_up),
        .bend_position(bend_position),.vibrato_depth(vibrato_depth),.pitch_offset(pitch_offset));
    wire [3:0] ui_focus;wire [6:0] ui_volume;
    wire pixel_clk,serial_clk,video_locked;
    reg [1:0] lock_sync=0;
    always @(posedge sys_clk) lock_sync<={lock_sync[0],video_locked};
    panel_buttons buttons(.clk(sys_clk),.rst(rst),.next_n(key1_n),.apply_n(key0_n),.valid(button_valid),.action(button_action));
    wire pcm_valid,busy,overrun,clipped;
    wire [5:0] active_voices=music_voices+drum_voices;
    wire use_keys=(key_mode!=0);
    wire source_valid=use_keys?key_cv:cfg_valid;
    wire source_gate=use_keys?key_gate:cfg_gate;
    wire [15:0] source_level=use_keys?key_cv_level:cfg_level;
    wire audible_command=source_gate && source_level!=0;
    wire music_allowed=source_valid && (!audible_command || amp_ready) && !amp_muting && !panic;
    wire pads_allowed=amp_ready && !amp_muting && !panic;
    wire choose_reset=live_flush_pending && !amp_muting && !panic;
    wire choose_off=!choose_reset && music_allowed && !source_gate;
    wire choose_native=!choose_reset && !choose_off && pads_allowed && drum_hit_valid;
    wire choose_pc=!choose_reset && !choose_off && !choose_native && pads_allowed && pc_pad_valid;
    wire choose_music=!choose_reset && !choose_native && !choose_pc && music_allowed;
    wire [122:0] music_event={2'b01,source_gate,(use_keys?key_voice:cfg_voice),(use_keys?key_wave:cfg_wave),
      (use_keys?key_step:cfg_step),source_level,(use_keys?key_attack:cfg_attack),(use_keys?key_decay:cfg_decay),
      (use_keys?key_sustain:cfg_sustain),(use_keys?key_tail:cfg_release)};
    assign performance_live_valid=choose_reset || choose_native || choose_pc || choose_music;
    assign performance_live_data=choose_reset?{2'b10,121'd0}:(choose_native || choose_pc)?
      {2'b00,1'b1,1'b0,(choose_native?drum_hit_pad:pc_pad),115'd0}:music_event;
    assign cfg_ready=!use_keys && choose_music && loop_live_ready;
    assign key_cr=use_keys && choose_music && loop_live_ready;
    assign pc_pad_ready=choose_pc && loop_live_ready;
    assign drum_hit_ready=(!uart_amp_hold && !amp_ready) || amp_muting || panic ? 1'b1:(choose_native && loop_live_ready);
    always @(posedge sys_clk)begin
      if(rst || clear_engine || panic)live_flush_pending<=0;
      else if(control_live_flush || (key_fault && !fault_old))live_flush_pending<=1;
      else if(choose_reset && loop_live_ready)live_flush_pending<=0;
    end
    keyboard_adc adc(.clk(sys_clk),.rst(rst),.soc(adc_soc),.eoc(adc_eoc),.data(adc_data));
    keyboard_input keys(.clk(sys_clk),.rst(rst),.recalibrate(key_recalibrate),
        .play(amp_hold && amp_ready && !amp_muting && !panic && !clear_engine),
        .mode(key_mode),.test_key(key_test),.press_threshold(key_press),.release_threshold(key_release),
        .max_level(key_level),.velocity_scale(key_scale),.mux_addr(key_addr),.mux_cs_n(key_cs_n),.mux_wr_n(key_wr_n),
        .adc_soc(adc_soc),.adc_eoc(adc_eoc),.adc_data(adc_data),.calibrated(key_calibrated),.fault(key_fault),
        .pressed_mask(key_pressed),.scan_count(key_scans),.last_raw(key_raw),.last_base(key_base),
        .last_delta(key_delta),.last_velocity(key_velocity),.last_key(key_last),
        .cfg_valid(key_cv),.cfg_ready(key_cr),.cfg_voice(key_voice),.cfg_gate(key_gate),
        .cfg_level(key_cv_level),.cfg_step(key_step));
    assign debug_sample=tick;
    wire bt_request,bt_accept,bt_locked,pmod_test,pmod_testing,pmod_single;wire [2:0] pmod_select;
    wire [7:0] bt_command,pmod_lamps;wire [15:0] bt_period,bt_count,bt_dropped;
    wire guide_ui_valid,guide_valid,guide_playing,guide_loading,guide_demo;wire [3:0] guide_ui_action;
    wire [15:0] guide_time_cs,guide_duration_cs;wire [9:0] guide_count,guide_index;wire [1:0] guide_speed;
    wire [31:0] guide_current,guide_onset,guide_next;wire [63:0] guide_colors;
    bt_console bluetooth(.guide_ui_valid(guide_ui_valid),.guide_ui_action(guide_ui_action),
        .guide_valid(guide_valid),.guide_playing(guide_playing),.guide_loading(guide_loading),.guide_demo(guide_demo),
        .guide_time_cs(guide_time_cs),.guide_duration_cs(guide_duration_cs),.guide_count(guide_count),.guide_index(guide_index),
        .guide_speed(guide_speed),.guide_current(guide_current),.guide_onset(guide_onset),.guide_next(guide_next),.guide_colors(guide_colors),.clk(sys_clk),.rst(rst),.bt_rx(bt_rx),.bt_tx(bt_tx),.audio_tick(tick),.pcm(pcm),.locked(bt_locked),
        .period(bt_period),.commands(bt_count),.dropped(bt_dropped),.request(bt_request),.command(bt_command),
        .accept(bt_accept),.settled(!fx_cv && !fx_pending),.volume(ui_volume),.timbre(key_wave),.fx(fx_status_mask),.lamps(pmod_lamps));
    wire [15:0] magnitude=pcm[15]?-pcm:pcm;
    pmod_indicators indicators(.clk(sys_clk),.rst(rst),.test(pmod_test),.single(pmod_single),.select_lamp(pmod_select),.sample_tick(tick),
        .magnitude(magnitude),.muted(PA_EN),
        .lamps(pmod_lamps),.testing(pmod_testing),.led_n(led_n));
    wire [31:0] pc_key_pressed;
    wire [31:0] panel_keys=key_mode==0?pc_key_pressed:key_pressed;
    wire [11:0] pt_bias;wire [1:0] pt_mode;
    uart_control_display controller(.guide_ui_valid(guide_ui_valid),.guide_ui_action(guide_ui_action),
        .guide_valid(guide_valid),.guide_playing(guide_playing),.guide_loading(guide_loading),.guide_demo(guide_demo),
        .guide_time_cs(guide_time_cs),.guide_duration_cs(guide_duration_cs),.guide_count(guide_count),.guide_index(guide_index),
        .guide_speed(guide_speed),.guide_current(guide_current),.pt_mode(pt_mode),.pt_bias(pt_bias),
        .pc_key_pressed(pc_key_pressed),
        .bt_request(bt_request),.bt_command(bt_command),.bt_accept(bt_accept),.bt_period(bt_period),.bt_locked(bt_locked),
        .bt_count(bt_count),.bt_dropped(bt_dropped),.pmod_test(pmod_test),.pmod_single(pmod_single),.pmod_select(pmod_select),.pmod_testing(pmod_testing),.pmod_lamps(pmod_lamps),
        .output_limited(output_limited),.limiter_overrun(limiter_overrun),.limiter_gain(limiter_gain),.limited_frames(limited_frames),
        .fx_command_valid(fx_cv),.fx_mask(fx_mask),.fx_reverb_mix(fx_r),.fx_delay_mix(fx_d),.fx_chorus_mix(fx_c),
        .fx_feedback(fx_fb),.fx_delay_time(fx_time),.fx_room(fx_room),.fx_rate(fx_rate),.fx_depth(fx_depth),
        .fx_monitor_mute(fx_monitor_mute),.fx_test_valid(fx_test_valid),.fx_test_value(fx_test_value),
        .fx_status_mask(fx_status_mask),.fx_status_reverb(fx_sr),.fx_status_delay(fx_sd),.fx_status_chorus(fx_sc),
        .fx_status_feedback(fx_sfb),.fx_status_time(fx_stime),.fx_status_room(fx_sroom),.fx_status_rate(fx_srate),.fx_status_depth(fx_sdepth),
        .fx_pending(fx_pending),.fx_busy(fx_busy),.fx_tail(fx_tail),.fx_overrun(fx_overrun),.fx_clipped(fx_clipped),
        .fx_frames(fx_frames),.fx_clip_frames(fx_clip_frames),
        .capture_command_valid(cap_cv),.capture_command_arm(cap_arm),.capture_trigger_nonzero(cap_trigger),
        .capture_length(cap_length),.capture_delay(cap_delay),.capture_read_address(cap_address),.capture_read_data(cap_data),
        .capture_busy(cap_busy),.capture_ready(cap_ready),.capture_flags(cap_flags),.capture_id(cap_id),
        .capture_count(cap_count),.capture_target(cap_target),.capture_capacity(cap_capacity),.capture_first_frame(cap_first),.capture_checksum(cap_crc),.clk(sys_clk),.rst(rst),.uart_in(uart_rx),.uart_out(uart_tx),
        .led_command_valid(led_command_valid),.led_command(led_command),.led_mode(led_mode),
        .led_index(led_index),.led_color(led_color),.led_preparing(led_preparing),.led_busy(led_busy),
        .led_latched_mask(led_latched_mask),.led_frames(led_frames),
        .diag_command_valid(diag_command_valid),.diag_command(diag_command),.diag_mode(diag_mode),.diag_phase(diag_phase),.diag_seconds(diag_seconds),
        .ui_valid(ui_valid),.ui_action(ui_action),.ui_value(button_valid?16'd0:native_value),.ui_ready(ui_ready),
        .express_adjust(express_adjust),.express_depth(express_depth),.express_up(express_up),
        .bend_position(bend_position),.vibrato_depth(vibrato_depth),.native_panic(native_panic),.native_connected(native_connected),.native_last_event(native_last_event),.native_diagnostic(native_diagnostic),.native_events(native_events),.video_locked(lock_sync[1]),
        .loop_command_valid(loop_command_valid),.loop_command(loop_command),.loop_playing(loop_playing),.loop_recording(loop_recording),
        .loop_pending(loop_pending),.loop_full(loop_full),.loop_layers(loop_layers),.loop_notice(loop_notice),.loop_duration(loop_duration),
        .loop_position(loop_position),.loop_actual_length(loop_actual_length),.loop_actual_cs(loop_actual_cs),.loop_position_cs(loop_position_cs),.loop_counts(loop_counts),.loop_replayed(loop_replayed),.pc_pad_valid(pc_pad_valid),.pc_pad(pc_pad),.pc_pad_ready(pc_pad_ready),
        .live_piano_flush(control_live_flush),.drum_level(drum_level),.router_held(held_count),.router_live_held(live_held_count),
        .router_held_mask(held_mask),.router_notes(router_notes),.router_steals(router_steals),.router_ignored(router_ignored),
        .drum_mode(drum_mode),.drum_hits(drum_hits),.drum_limit_frames(drum_limit_frames),.drum_mask(drum_mask),
        .drum_last_pad(drum_last_pad),.drum_overrun(drum_overrun),.drum_limited(drum_limited),.drum_voices(drum_voices),
        .ui_focus(ui_focus),.ui_pattern(ui_pattern),.ui_local(ui_local),.ui_volume(ui_volume),.ui_notice(ui_notice),
        .sample_tick(tick),.active_voices(active_voices),.pcm(pcm),.overrun(overrun|drum_overrun|fx_overrun|limiter_overrun),.clipped(clipped|output_clipped|fx_clipped),
        .amp_muted(PA_EN),.amp_ready(amp_ready),.gain_mode(gain_mode),.amp_hold(uart_amp_hold),
        .key_calibrated(key_calibrated),.key_fault(key_fault),.key_pressed(panel_keys),
        .key_last(key_last),.key_raw(key_raw),.key_base(key_base),.key_delta(key_delta),.key_velocity(key_velocity),.key_scans(key_scans),
        .key_mode(key_mode),.key_test(key_test),.key_wave(key_wave),.key_recalibrate(key_recalibrate),
        .key_level(key_level),.key_press(key_press),.key_release(key_release),.key_attack(key_attack),
        .key_decay(key_decay),.key_sustain(key_sustain),.key_tail(key_tail),.key_scale(key_scale),
        .panic(uart_panic),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_voice(cfg_voice),
        .cfg_gate(cfg_gate),.cfg_step(cfg_step),.cfg_wave(cfg_wave),.cfg_level(cfg_level),
        .cfg_attack(cfg_attack),.cfg_decay(cfg_decay),.cfg_sustain(cfg_sustain),.cfg_release(cfg_release));
    synth_engine_shared engine(.pitch_offset(pitch_offset),.clk(sys_clk),.rst(rst|clear_engine),.sample_tick(tick),
        .cfg_valid(routed_cfg_valid && !panic && !amp_muting),.cfg_ready(engine_ready),.cfg_voice(routed_voice),
        .cfg_gate(routed_gate),.cfg_restart(routed_restart),.cfg_step(routed_step),.cfg_wave(routed_wave),.cfg_level(routed_level),
        .cfg_attack(routed_attack),.cfg_decay(routed_decay),.cfg_sustain(routed_sustain),.cfg_release(routed_release),
        .pcm(engine_pcm),.pcm_valid(pcm_valid),.busy(busy),.overrun(overrun),.clipped(clipped),.voice_active_mask(music_active_mask),.active_voices(music_voices),.mix_sum(music_mix));
    audio_output output_stage(.clk(sys_clk),.rst(rst),.sample_tick(tick),.panic(panic),
        .limited(output_limited),.limiter_overrun(limiter_overrun),.limiter_gain(limiter_gain),.limited_frames(limited_frames),
        .hold_open(amp_hold),
        .wake_request(source_valid && audible_command && (!use_keys || !key_fault)),
        .active_voices(active_voices!=0?active_voices:(fx_tail?6'd1:6'd0)),.mix_sum(mix_sum),.gain_mode(gain_mode),
        .pcm(dry_pcm),.pa_disable(amp_disable_logic),.ready(amp_ready),.muting(amp_muting),
        .clear_engine(clear_engine),.clipped(output_clipped));
    // NEO 31004 is AC-coupled at C111/C113 and C135/C136. The measured
    // trim is held constant during playback; PCM and I2S retain their original samples.
    audio_tx #(.USE_PT_TRIM(1)) tx(.pt_mode(pt_mode),.pt_trim(pt_bias),.clk(sys_clk),.rst(rst),.pcm_left(pcm),.pcm_right(pcm),.sample_tick(tick),
        .i2s_bclk(i2s_bclk),.i2s_lrclk(i2s_lrclk),.i2s_data(i2s_data),.hp_bck(HP_BCK),.hp_ws(HP_WS),.hp_din(HP_DIN));
    assign hpd_en=1;
    display_pll pll(.clkin(sys_clk),.lock(video_locked),.clkout0(serial_clk),.clkout1(pixel_clk));
    reg [3:0] reset_sync=0;
    always @(posedge pixel_clk or negedge video_locked)
        if(!video_locked) reset_sync<=0;else reset_sync<={reset_sync[2:0],1'b1};
    wire pixel_rst=!reset_sync[3];
    wire [10:0] x,y;wire hs,vs,de,frame_start;
    video_timing timing(.clk(pixel_clk),.rst(pixel_rst),.x(x),.y(y),.hs(hs),.vs(vs),.de(de),.frame_start(frame_start));
    reg [7:0] peak=0;reg [5:0] peak_div=0;
    always @(posedge sys_clk) begin
        if(rst) begin peak<=0;peak_div<=0;end
        else if(tick) begin
            peak_div<=peak_div+1'b1;
            if(magnitude[15]) peak<=255;
            else if(magnitude[14:7]>peak) peak<=magnitude[14:7];
            else if(peak_div==0 && peak!=0) peak<=peak-1'b1;
        end
    end
    wire [370:0] panel_state;
    display_snapshot #(.WIDTH(371)) snapshot(.sys_clk(sys_clk),.sys_rst(rst),.pixel_clk(pixel_clk),.pixel_rst(pixel_rst),
        .frame_start(frame_start),.source({panel_keys,guide_colors,guide_next,guide_onset,guide_current,guide_speed,guide_index,guide_count,guide_duration_cs,guide_time_cs,guide_demo,guide_loading,guide_playing,guide_valid,bend_position,vibrato_depth,fx_status_mask,ui_focus[3],loop_actual_cs,loop_position_cs,loop_layers,loop_duration,loop_playing,loop_recording,loop_pending,loop_notice,loop_progress,drum_mode,ui_focus[2:0],key_wave,ui_volume,active_voices,key_mode,
            key_calibrated,key_fault,PA_EN,amp_ready,uart_amp_hold,ui_pattern,ui_notice,(drum_mode?{20'd0,drum_mask}:panel_keys),peak}),.snapshot(panel_state));
    wire [23:0] rgb;wire hs_out,vs_out,de_out;
    panel_renderer renderer(.actual_keys(panel_state[370:339]),.guide_colors(panel_state[338:275]),
        .guide_next(panel_state[274:243]),.guide_onset(panel_state[242:211]),.guide_target(panel_state[210:179]),
        .guide_speed(panel_state[178:177]),.guide_index(panel_state[176:167]),.guide_count(panel_state[166:157]),
        .guide_duration_cs(panel_state[156:141]),.guide_time_cs(panel_state[140:125]),.guide_demo(panel_state[124]),
        .guide_loading(panel_state[123]),.guide_playing(panel_state[122]),.guide_valid(panel_state[121]),.clk(pixel_clk),.rst(pixel_rst),.x(x),.y(y),.hs(hs),.vs(vs),.de(de),
        .loop_actual_cs(panel_state[109:100]),.loop_position_cs(panel_state[99:90]),.loop_layers(panel_state[89:87]),.loop_duration(panel_state[86:85]),.loop_playing(panel_state[84]),
        .loop_recording(panel_state[83]),.loop_pending(panel_state[82]),.loop_notice(panel_state[81:79]),.loop_progress(panel_state[78:72]),
        .bend_position(panel_state[120:117]),.vibrato_depth(panel_state[116:114]),.drum_mode(panel_state[71]),.focus({panel_state[110],panel_state[70:68]}),.fx(panel_state[113:111]),.timbre(panel_state[67:65]),.volume(panel_state[64:58]),
        .voices(panel_state[57:52]),.mode(panel_state[51:50]),.calibrated(panel_state[49]),.fault(panel_state[48]),
        .muted(panel_state[47]),.ready(panel_state[46]),.playing(panel_state[45]),.pattern(panel_state[44]),
        .notice(panel_state[43:40]),.pressed(panel_state[39:8]),.peak(panel_state[7:0]),
        .rgb(rgb),.hs_out(hs_out),.vs_out(vs_out),.de_out(de_out));
    DVI_TX_Top video_tx(.I_rst_n(reset_sync[3]),.I_serial_clk(serial_clk),.I_rgb_clk(pixel_clk),
        .I_rgb_vs(vs_out),.I_rgb_hs(hs_out),.I_rgb_de(de_out),.I_rgb_r(rgb[23:16]),.I_rgb_g(rgb[15:8]),.I_rgb_b(rgb[7:0]),
        .O_tmds_clk_p(tmds_clk_p),.O_tmds_clk_n(tmds_clk_n),.O_tmds_data_p(tmds_data_p),.O_tmds_data_n(tmds_data_n));
endmodule
