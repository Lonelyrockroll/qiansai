"""Wire protocol shared by the host and RTL tests. Python standard library only."""
import math
import struct

BAUD = 115200
FS = 50_000_000 / 1024
REQUEST_SYNC = b'\xa5\x5a'
RESPONSE_SYNC = b'\x5a\xa5'
PING, CONFIG, PANIC, STATUS, GAIN, ARM, KEY_CONFIG, KEY_CALIBRATE, KEY_STATUS = 1, 2, 3, 4, 5, 6, 7, 8, 9
DISPLAY_ACTION, DISPLAY_STATUS = 10, 11
LED_CONTROL, LED_STATUS = 18, 19
LED_PIN_CONTROL = 20
PCM_CONTROL, PCM_STATUS, PCM_READ = 21, 22, 23
FX_CONTROL, FX_STATUS, FX_IMPULSE = 24, 25, 26
OUTPUT_GAIN_STATUS = 27
PMOD_TEST, PMOD_STATUS = 28, 29
# H1..H32 on the white-key instrument. Index is independent of the allocated voice.
WHITE_KEYS = tuple(36 + 12*(i//7) + (0,2,4,5,7,9,11)[i%7] for i in range(32))



def packet(seq, opcode, payload=b''):
    if len(payload) > 20:
        raise ValueError('payload too long')
    body = bytes((1, seq & 255, opcode, 20)) + payload.ljust(20, b'\0')
    checksum = 0
    for byte in body:
        checksum ^= byte
    return REQUEST_SYNC + body + bytes((checksum, 13))


def voice_payload(voice, gate, frequency, timbre=0, level=0.6,
                  attack_ms=5, decay_ms=80, sustain=0.65, release_ms=100):
    numbers = (frequency, level, attack_ms, decay_ms, sustain, release_ms)
    if not all(math.isfinite(float(v)) for v in numbers):
        raise ValueError('参数必须为有限数值')
    if not 0 <= voice < 32 or gate not in (0, 1) or not 0 <= timbre < 5:
        raise ValueError('声部、门控或音色超出范围')
    if not 0 < frequency < FS / 16:
        raise ValueError(f'频率范围为 0～{FS/16:.2f} Hz，不含端点')
    if timbre==4 and round(frequency*2**32/FS)>0x0ff00000:
        raise ValueError('钢琴模式基频需低于约 3039.84 Hz，为微失谐高次谐波留出余量')
    if not 0 <= level <= 1 or not 0 <= sustain <= 1:
        raise ValueError('力度和 Sustain 必须在 0～1 范围')
    if not all(0 <= t <= 5000 for t in (attack_ms, decay_ms, release_ms)):
        raise ValueError('包络时间范围为 0～5000 ms')
    def rate(distance, milliseconds):
        return max(1, min(65535, math.ceil(distance / max(1, milliseconds*FS/1000))))
    sustain_u16 = round(sustain*65535)
    return struct.pack('<BBBH I HHHH', voice, gate, timbre, round(level*65535),
                       round(frequency*2**32/FS), rate(65535, attack_ms),
                       rate(65535-sustain_u16, decay_ms), sustain_u16,
                       rate(65535 if timbre==4 else sustain_u16, release_ms))


class Decoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while True:
            pos = self.buffer.find(RESPONSE_SYNC)
            if pos < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer[-1:] == b'\x5a' else b''
                break
            del self.buffer[:pos]
            if len(self.buffer) < 28:
                break
            frame = bytes(self.buffer[:28])
            checksum = 0
            for byte in frame[2:26]:
                checksum ^= byte
            if frame[2] != 1 or frame[4:6] != b'\x80\x14' or frame[26] != checksum or frame[27] != 13:
                del self.buffer[0]
                continue
            del self.buffer[:28]
            p = frame[6:26]
            if p[19]==PMOD_STATUS and p[18]>=22:
                period=int.from_bytes(p[3:5],'little')
                result.append(dict(seq=frame[3],status=p[0],locked=bool(p[1]&1),testing=bool(p[1]&2),lamps=p[2],
                    period=period,single_supported=bool(p[9]&1),baud=round(50_000_000/period) if p[1]&1 and period else None,
                    commands=int.from_bytes(p[5:7],'little'),dropped=int.from_bytes(p[7:9],'little'),
                    sample_rate=FS,firmware=p[18],opcode=p[19]))
                continue
            if p[19]==OUTPUT_GAIN_STATUS and p[18]>=21:
                result.append(dict(seq=frame[3],status=p[0],melodic_factor=p[1],limited=bool(p[2]&1),
                    limiter_overrun=bool(p[2]&2),gain_mode=p[3],limiter_gain_q16=int.from_bytes(p[4:7],'little'),
                    limited_frames=int.from_bytes(p[7:11],'little'),ceiling=int.from_bytes(p[11:13],'little'),
                    keyboard_level=int.from_bytes(p[13:15],'little'),drum_level=int.from_bytes(p[15:17],'little'),
                    sample_rate=FS,firmware=p[18],opcode=p[19]))
                continue
            if p[19]==FX_STATUS and p[18]>=20:
                flags=p[10]
                result.append(dict(seq=frame[3],status=p[0],mask=p[1],reverb_mix=p[2],delay_mix=p[3],chorus_mix=p[4],
                    delay_time=p[5],feedback=p[6],room=p[7],rate=p[8],depth=p[9],pending=bool(flags&1),busy=bool(flags&2),
                    clipped=bool(flags&4),overrun=bool(flags&8),tail=bool(flags&16),monitor_mute=bool(flags&32),
                    frames=int.from_bytes(p[11:15],'little'),clipped_frames=int.from_bytes(p[15:18],'little'),
                    sample_rate=FS,firmware=p[18],opcode=p[19]))
                continue
            if p[19]==PCM_STATUS and p[18]>=19:
                result.append(dict(seq=frame[3],status=p[0],flags=p[1],armed=bool(p[1]&1),
                    recording=bool(p[1]&2),ready=bool(p[1]&4),aborted=bool(p[1]&8),error=bool(p[1]&16),
                    capture_id=int.from_bytes(p[2:4],'little'),count=int.from_bytes(p[4:6],'little'),
                    target=int.from_bytes(p[6:8],'little'),first_frame=int.from_bytes(p[8:12],'little'),
                    crc32=int.from_bytes(p[12:16],'little'),capacity=int.from_bytes(p[16:18],'little'),
                    sample_rate=FS,firmware=p[18],opcode=p[19]))
                continue
            if p[19]==PCM_READ and p[18]>=19:
                count=p[5]
                if count>6:continue
                result.append(dict(seq=frame[3],status=p[0],capture_id=int.from_bytes(p[1:3],'little'),
                    offset=int.from_bytes(p[3:5],'little'),count=count,data=p[6:6+2*count].hex(),
                    sample_rate=FS,firmware=p[18],opcode=p[19]))
                continue
            if p[19]==LED_STATUS and p[18]>=17:
                result.append(dict(seq=frame[3],status=p[0],mode=p[1],index=p[2],color=p[3],
                    preparing=bool(p[4]&1),busy=bool(p[4]&2),calibrated=bool(p[4]&4),fault=bool(p[4]&8),
                    brightness=p[5],latched_mask=int.from_bytes(p[6:10],'little'),frames=int.from_bytes(p[10:14],'little'),
                    key_mode=p[14],firmware=p[18],opcode=p[19],
                    diagnostic_mode=p[15] if p[18]>=18 else 0,diagnostic_phase=p[16] if p[18]>=18 else 0,
                    diagnostic_seconds=p[17] if p[18]>=18 else 0))
                continue
            if p[19]==16 and p[18]>=16:
                result.append(dict(seq=frame[3],status=p[0],view_is_drums=bool(p[1]),length_set=bool(p[2]),timbre=p[3],
                    actual_frames=int.from_bytes(p[4:7],'little'),actual_centiseconds=int.from_bytes(p[7:9],'little'),
                    position_centiseconds=int.from_bytes(p[9:11],'little'),drum_level=int.from_bytes(p[11:13],'little'),
                    keyboard_level=int.from_bytes(p[13:15],'little'),key_mode=p[15],calibrated=bool(p[16]&1),fault=bool(p[16]&2),
                    firmware=p[18],opcode=p[19]))
                continue
            if p[19]==17 and p[18]>=16:
                result.append(dict(seq=frame[3],status=p[0],held=p[1],live_held=p[2],loop_held=p[3],
                    notes_applied=int.from_bytes(p[4:8],'little'),steals=int.from_bytes(p[8:12],'little'),
                    held_mask=int.from_bytes(p[12:16],'little'),ignored_offs_mod65536=int.from_bytes(p[16:18],'little'),
                    firmware=p[18],opcode=p[19]))
                continue
            if p[19]==14 and p[18]>=15:
                result.append(dict(seq=frame[3],status=p[0],present=bool(p[1]&1),playing=bool(p[1]&2),recording=bool(p[1]&4),
                    pending_record=bool(p[1]&8),event_full=bool(p[1]&16),session=bool(p[1]&32),layers=p[2],
                    duration_index=p[3],duration_seconds=(2,4,8)[min(p[3],2)],position_frames=int.from_bytes(p[4:7],'little'),
                    notice=p[7],layer_counts=[int.from_bytes(p[8+2*i:10+2*i],'little') for i in range(4)],
                    replayed_events_mod65536=int.from_bytes(p[16:18],'little'),firmware=p[18],opcode=p[19]))
                continue
            if p[19]==13 and p[18]>=14:
                result.append(dict(seq=frame[3],status=p[0],drum_mode=bool(p[1]&1),native_usb_connected=bool(p[1]&2),
                    amp_hold=bool(p[1]&4),amp_muted=bool(p[1]&8),amp_ready=bool(p[1]&16),overrun=bool(p[1]&32),
                    limited=bool(p[1]&64),last_pad=p[2]+1,active_voices=p[3],hits=int.from_bytes(p[4:8],'little'),
                    limited_frames=int.from_bytes(p[8:12],'little'),active_mask=int.from_bytes(p[12:14],'little'),
                    level=int.from_bytes(p[14:16],'little'),firmware=p[18],opcode=p[19]))
                continue
            if p[19]==12 and p[18]>=13:
                expr={'bend_cents':(int(p[3]&15)-4)*50,'vibrato_cents':((p[3]>>4)&7)*10} if p[18]>=27 and p[3]&128 else {}
                result.append(dict(seq=frame[3],status=p[0],native_usb_connected=bool(p[1]),**expr,
                    last_event=p[2],diagnostic_hex=p[4:12].hex(),event_count=int.from_bytes(p[12:16],'little'),firmware=p[18],opcode=p[19]))
                continue
            if p[19]==DISPLAY_STATUS:
                result.append(dict(seq=frame[3],status=p[0],focus=p[1],timbre=p[2],volume=p[3],
                    calibrated=bool(p[4]&1),fault=bool(p[4]&2),amp_muted=bool(p[4]&4),
                    amp_hold=bool(p[4]&8),pattern=bool(p[4]&16),local=bool(p[4]&32),locked=bool(p[4]&64),
                    mode=p[5],notice=p[6],active=p[7],level=int.from_bytes(p[8:10],'little'),
                    press=int.from_bytes(p[10:12],'little'),release=int.from_bytes(p[12:14],'little'),
                    sensitivity=int.from_bytes(p[14:16],'little'),firmware=p[18],opcode=p[19],
                    native_usb_connected=bool(p[16]&1) if p[18]>=13 else None,
                    native_last_event=p[17] if p[18]>=13 else None,drum_mode=bool(p[16]&2) if p[18]>=14 else False,
                    simultaneous_sources=p[18]>=16))
                continue
            if p[19]==KEY_STATUS:
                result.append(dict(seq=frame[3],status=p[0],mode=p[1],calibrated=bool(p[2]&1),
                    fault=bool(p[2]&2),key=p[3],raw=int.from_bytes(p[4:6],'little'),
                    baseline=int.from_bytes(p[6:8],'little'),delta=int.from_bytes(p[8:10],'little'),
                    velocity=int.from_bytes(p[10:12],'little'),pressed_mask=int.from_bytes(p[12:16],'little'),
                    scans=int.from_bytes(p[16:18],'little'),firmware=p[18],opcode=p[19]))
                continue
            result.append(dict(seq=frame[3], status=p[0], gated=p[1], active=p[2],
                               overrun=bool(p[3]&1), clipped=bool(p[3]&2),
                               watchdog=bool(p[3]&4), amp_muted=bool(p[3]&8), amp_ready=bool(p[3]&16),
                               gain_mode=(p[3]>>5)&3, amp_hold=bool(p[3]&128),commands=int.from_bytes(p[4:8],'little'),
                               frames=int.from_bytes(p[8:12],'little'),
                               pcm=int.from_bytes(p[12:14],'little',signed=True),
                               sample_rate=int.from_bytes(p[14:18],'little')/1000,
                               firmware=p[18], opcode=p[19]))
        return result


def response_for_test(seq, opcode, *, status=0, gated=0, active=0, commands=0, frames=0, pcm=0, flags=0):
    p = struct.pack('<BBBBIIhIBB', status,gated,active,flags,commands,frames,pcm,round(FS*1000),9,opcode)
    raw = packet(seq,128,p)
    return RESPONSE_SYNC + raw[2:]


def keyboard_payload(mode=0,key=12,press=256,release=128,sensitivity=64,params=None):
    if any(isinstance(v,bool) or int(v)!=v for v in (mode,key,press,release,sensitivity)):
        raise ValueError('琴键模式、编号及阈值必须是整数')
    if not 0<=mode<=2 or not 0<=key<32 or not 0<=release<press<=8191 or not 1<=sensitivity<=1024:
        raise ValueError('琴键参数越界：松开阈值必须小于按下阈值')
    params=dict(params or dict(timbre=4,level=.24,attack_ms=1,decay_ms=1000,sustain=0,release_ms=110))
    params['level']=min(float(params.get('level',.24)),.25)
    _,_,wave,level,_,attack,decay,sustain,tail=struct.unpack('<BBBH I HHHH',voice_payload(0,0,440,**params))
    return struct.pack('<BBB8H',int(mode),int(key),wave,level,int(press),int(release),attack,decay,sustain,tail,int(sensitivity))
