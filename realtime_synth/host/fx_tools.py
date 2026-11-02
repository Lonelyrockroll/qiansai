from protocol import FX_CONTROL,FX_STATUS,FX_IMPULSE
FIELDS=('mask','reverb_mix','delay_mix','chorus_mix','delay_time','feedback','room','rate','depth','monitor_mute')
LEGACY_PRESETS={
 'off':dict(mask=0,reverb_mix=48,delay_mix=64,chorus_mix=80,delay_time=2,feedback=96,room=1,rate=1,depth=1,monitor_mute=0),
 'piano':dict(mask=1,reverb_mix=48,delay_mix=0,chorus_mix=0,delay_time=2,feedback=96,room=0,rate=1,depth=1,monitor_mute=0),
 'reverb':dict(mask=1,reverb_mix=80,delay_mix=0,chorus_mix=0,delay_time=2,feedback=96,room=1,rate=1,depth=1,monitor_mute=0),
 'delay':dict(mask=2,reverb_mix=0,delay_mix=80,chorus_mix=0,delay_time=2,feedback=96,room=1,rate=1,depth=1,monitor_mute=0),
 'chorus':dict(mask=4,reverb_mix=0,delay_mix=0,chorus_mix=96,delay_time=2,feedback=96,room=1,rate=1,depth=2,monitor_mute=0),
 'combined':dict(mask=7,reverb_mix=48,delay_mix=48,chorus_mix=64,delay_time=2,feedback=80,room=1,rate=1,depth=1,monitor_mute=0)
}
PRESETS={
 'off':LEGACY_PRESETS['off'].copy(),
 'piano':dict(mask=1,reverb_mix=64,delay_mix=0,chorus_mix=0,delay_time=3,feedback=112,room=1,rate=2,depth=2,monitor_mute=0),
 'reverb':dict(mask=1,reverb_mix=128,delay_mix=0,chorus_mix=0,delay_time=3,feedback=112,room=2,rate=2,depth=2,monitor_mute=0),
 'delay':dict(mask=2,reverb_mix=0,delay_mix=128,chorus_mix=0,delay_time=3,feedback=112,room=2,rate=2,depth=2,monitor_mute=0),
 'chorus':dict(mask=4,reverb_mix=0,delay_mix=0,chorus_mix=128,delay_time=3,feedback=112,room=2,rate=2,depth=2,monitor_mute=0),
 'combined':dict(mask=7,reverb_mix=64,delay_mix=64,chorus_mix=112,delay_time=3,feedback=112,room=2,rate=2,depth=2,monitor_mute=0),
}
def validate(settings,profile=1):
    values={k:settings[k] for k in FIELDS}
    wet_limit=128 if profile>=2 else 96
    limits=[7,wet_limit,wet_limit,128,3,128,2,3,3,1]
    for key,limit in zip(FIELDS,limits):
        v=values[key]
        if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=limit:raise ValueError(f'效果器参数 {key} 超出范围')
    total=(values['reverb_mix'] if values['mask']&1 else 0)+(values['delay_mix'] if values['mask']&2 else 0)
    if total>128:raise ValueError('混响与延迟的混合量合计不能超过50%')
    return values
def configure(controller,data):
    if not controller.transport or controller.feedback.get('firmware',0)<20:raise ValueError('请先连接 v20 效果器固件')
    profile=controller.fx_feedback.get('effect_profile',1)
    if 'preset' in data:
        if data['preset'] not in PRESETS:raise ValueError('未知效果预设')
        values=(PRESETS if profile>=2 else LEGACY_PRESETS)[data['preset']].copy()
        # Preserve a deliberately muted monitor during unattended test/preset changes.
        values['monitor_mute']=int(controller.fx_feedback.get('monitor_mute',False))
    else:values=validate(data['settings'],profile)
    controller.exchange(FX_CONTROL,bytes(values[k] for k in FIELDS));controller.exchange(FX_STATUS)
def impulse(controller,amplitude):
    if not isinstance(amplitude,int) or isinstance(amplitude,bool) or not 1<=amplitude<=16384:raise ValueError('测试幅度无效')
    status=controller.exchange(FX_STATUS)
    if not status['monitor_mute']:raise ValueError('脉冲测试仅允许在模拟输出关闭时执行')
    controller.exchange(FX_IMPULSE,amplitude.to_bytes(2,'little'))
    controller.pcm_context['stimulus']=dict(kind='FPGA-generated single-sample impulse before effects',amplitude=amplitude)
