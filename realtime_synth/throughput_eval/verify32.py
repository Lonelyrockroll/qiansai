"""v26 digital-output throughput demonstration. See --help; default is status only."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import zlib
from datetime import datetime

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'control_meter_l8'))
from verify_board import Board
from fx_tools import FIELDS, PRESETS
from protocol import FS, voice_payload

N = 4096
BINS = tuple(17 + 7*i for i in range(32))
OFF = 15
NEW_BIN = BINS[OFF] + 2


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def status(board):
    state = board.state()
    for op in (13, 14, 17):
        state[str(op)] = board.call(op)
    return state


def check_idle(s, pause_held, android_idle):
    require(android_idle, 'v26 cannot report Android recording state. Stop phone recording, then pass --android-idle.')
    require(all(v['firmware'] == 26 for v in s.values()), 'This test is for v26 only.')
    require(s['16']['key_mode'] in (0, 2), 'Single-channel calibration mode cannot be restored losslessly. Switch modes first.')
    require(not (s['4']['active'] or s['4']['gated'] or s['17']['held'] or s['13']['active_voices']
                 or s['9']['pressed_mask'] or s['25']['tail'] or s['25']['pending']), 'Live notes, effects transition or tail present.')
    require(not (s['16']['length_set'] or s['14']['present'] or s['14']['playing'] or s['14']['recording']
                 or s['14']['pending_record'] or s['14']['layers'] or any(s['14']['layer_counts'])), 'Loop in use or recorded layers present.')
    require(not any(s['22'][k] for k in ('ready', 'recording', 'armed')), 'There is a PCM capture to preserve.')
    require(not s['4']['amp_hold'] or pause_held, 'Performance is armed. Pass --pause-held only if stopping it is intended.')


def wait_for(fn, predicate, label, timeout=1.2):
    end = time.monotonic() + timeout
    while True:
        current = fn()
        if predicate(current):
            return current
        if time.monotonic() > end:
            raise RuntimeError(label + ': ' + str(current))
        time.sleep(.005)


def note(board, voice, gate, k):
    # Exactly representable DDS step = k*2^20. Each peak has the same nonzero gain.
    board.call(2, voice_payload(voice, gate, k*FS/N, timbre=0, level=.10, attack_ms=3,
                                decay_ms=5, sustain=1, release_ms=5))


def assert_healthy(s, count, limiter_start):
    a, r, fx, gain, drums = (s[str(op)] for op in (4, 17, 25, 27, 13))
    require(a['sample_rate'] == FS and a['active'] == a['gated'] == r['live_held'] == count
            and not r['loop_held'] and not drums['active_voices'], 'Wrong simultaneous count/rate')
    require(a['amp_muted'] and a['amp_ready'] and fx['monitor_mute'] and not fx['mask'], 'Expected isolated dry digital output')
    require(not (a['overrun'] or a['clipped'] or a['watchdog'] or fx['overrun'] or fx['clipped']
                 or gain['limited'] or gain['limiter_overrun'] or drums['overrun']), 'Clip, limit, watchdog or missed deadline')
    require(gain['limited_frames'] == limiter_start and gain['limiter_gain_q16'] == 65536, 'Limiter affected the test')


def snapshot_audio(board):
    return {str(op): board.call(op) for op in (4, 13, 17, 25, 27)}


def grab(board, count, limiter_start):
    before = snapshot_audio(board)
    assert_healthy(before, count, limiter_start)
    old_id = board.call(22)['capture_id']
    board.call(21, b'\1\0' + struct.pack('<HI', N, 0))
    meta = wait_for(lambda: board.call(22), lambda v: v['ready'], 'PCM capture timeout')
    require(meta['capture_id'] == (old_id+1) % 65536 and meta['count'] == meta['target'] == N and not meta['error'], 'Unexpected PCM metadata')
    after = snapshot_audio(board)
    assert_healthy(after, count, limiter_start)
    raw = bytearray()
    for offset in range(0, N, 6):
        n = min(6, N-offset)
        item = board.call(23, struct.pack('<HHB', meta['capture_id'], offset, n))
        data = bytes.fromhex(item['data'])
        require(item['capture_id'] == meta['capture_id'] and item['offset'] == offset and item['count'] == n and len(data) == 2*n,
                f'Mismatched readback at {offset}')
        raw.extend(data)
    require(zlib.crc32(raw) == meta['crc32'], 'FPGA CRC32 mismatch')
    return bytes(raw), {'before':before, 'after':after, 'capture':meta, 'sha256':hashlib.sha256(raw).hexdigest()}


def spectrum(raw, bins):
    require(len(raw) == 2*N, 'Wrong recording length')
    pcm = np.frombuffer(raw, dtype='<i2').astype(np.float64)
    amps = 2*np.abs(np.fft.rfft(pcm-pcm.mean()))/N
    bg = amps.copy(); bg[list(bins)] = 0
    weak = float(min(amps[k] for k in bins))
    noise = float(bg.max())
    require(weak >= 50 and weak >= 10*noise, f'Missing or obscured component: weakest target {weak:.2f}, largest unexpected bin {noise:.2f}')
    require(max(amps[k] for k in bins) < 1.42*weak, 'Excessive spread in nominally equal tones')
    return amps, dict(peak_pcm=int(np.max(np.abs(pcm))), rms_pcm=float(np.sqrt(np.mean(pcm**2))),
                      min_tone_amplitude_pcm=weak, max_unexpected_amplitude_pcm=noise)


def compare(full, changed, retuned=False):
    k = BINS[OFF]
    require(changed[k] <= full[k]/32, 'Released fundamental did not drop by at least 30 dB')
    keep = [i for i in BINS if i != k]
    require(np.all(np.abs(changed[keep]-full[keep]) <= np.maximum(2.,.02*full[keep])), 'Unrelated fundamentals changed')
    if retuned:
        require(abs(changed[NEW_BIN]-full[k]) <= max(2.,.02*full[k]), 'Retuned fundamental has wrong amplitude')


def restore(board, before, owned_capture):
    errors = []
    def attempt(label, fn):
        try:
            return fn()
        except Exception as exc:
            errors.append(f'{label}: {exc}')
    # Silence the test before re-enabling the user's analog monitor.
    attempt('panic', lambda: board.call(3))
    if owned_capture:
        attempt('abort test capture', lambda: board.call(21))
    safe = attempt('wait muted', lambda: wait_for(lambda: board.call(4),
                   lambda s: s['active'] == s['gated'] == 0 and not s['amp_hold'] and not s['amp_ready'], 'PA not drained'))
    attempt('gain', lambda: board.call(5, bytes([before['27']['gain_mode']])))
    def restore_scan():
        expected = before['16']['key_mode']
        if board.call(11)['mode'] != expected:
            board.call(10, b'\x0b')
        wait_for(lambda: board.call(9), lambda k: k['mode'] == expected and
                 (not expected or (k['calibrated'] and not k['fault'])), 'Scan mode/calibration not restored', 3)
    attempt('keyboard', restore_scan)
    if safe:
        attempt('FX/monitor', lambda: board.fx(before['25']))
    if errors:
        raise RuntimeError('Restore incomplete: '+'; '.join(errors))
    final = status(board)
    require(final['4']['amp_muted'] and not final['4']['amp_hold'], 'Not safely stopped at exit')
    for op, fields in [('11',('focus','drum_mode','timbre','level','press','release','sensitivity','pattern')),
                       ('16',('drum_level','keyboard_level','key_mode')),('27',('gain_mode',)),('25',FIELDS)]:
        require(all(final[op][f] == before[op][f] for f in fields), f'Original state differs: opcode {op}')
    return final


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def run(board, args):
    before = status(board)
    if not args.run:
        print(json.dumps({k:before[k] for k in ('4','13','14','16','17','22','25','27')},ensure_ascii=False,indent=2))
        return
    check_idle(before,args.pause_held,args.android_idle)
    dest = args.out or ROOT/'runs'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    dest.mkdir(parents=True,exist_ok=False)
    report = {'result':'incomplete', 'scope':'FPGA final digital PCM with analog monitor muted; no acoustic claim',
              'sample_rate_hz_design_and_firmware':FS, 'capture_size':N, 'muted_voice':OFF, 'before':before, 'cases':{}}
    save_json(dest/'summary.json',report)
    owns_capture = False
    try:
        # Do not use KEY_CONFIG: its complete original ADSR cannot be read from v26.
        board.fx(dict(PRESETS['off'],monitor_mute=1))
        board.call(3)
        if before['16']['key_mode'] == 2:
            board.call(10,b'\x0b')
            wait_for(lambda: board.call(11),lambda s:s['mode']==0,'Select PC input')
        board.call(5,b'\0')
        board.call(6)
        wait_for(lambda: board.call(4),lambda s:s['amp_muted'] and s['amp_ready'],'Muted digital warmup')
        limiter_start = board.call(27)['limited_frames']
        for i,k in enumerate(BINS):
            note(board,i,1,k)
        owns_capture = True
        amps = {}
        cases = [('all32',list(BINS)),('off31',[k for k in BINS if k!=BINS[OFF]])]
        if args.retune:
            cases.append(('retuned32',cases[1][1]+[NEW_BIN]))
        for name,bins in cases:
            if name=='off31':note(board,OFF,0,BINS[OFF])
            if name=='retuned32':note(board,OFF,1,NEW_BIN)
            time.sleep(.04)
            raw, meta = grab(board,len(bins),limiter_start)
            (dest/(name+'.pcm')).write_bytes(raw)
            report['cases'][name]=meta
            arr,levels=spectrum(raw,bins)
            amps[name]=arr;meta.update(levels);meta['expected_bins']=bins
            if name!='all32':compare(amps['all32'],arr,retuned=(name=='retuned32'))
        with (dest/'spectrum.csv').open('w',newline='',encoding='utf8') as file:
            out=csv.writer(file);out.writerow(['bin','Hz',*amps])
            for i in range(1,N//2+1):
                out.writerow([i,i*FS/N,*(float(a[i]) for a in amps.values())])
        report['validated_digital_components']=32
        report['component_samples_per_second']=32*FS
        report['result']='passed'
    except BaseException as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
        raise
    finally:
        try:report['restored']=restore(board,before,owns_capture)
        except Exception as exc:
            report['result']='incomplete';report['restore_error']=str(exc)
            raise
        finally:save_json(dest/'summary.json',report)
    print(f'PASS 32 FFT-bin-centered tones and selective note-off. Evidence: {dest}')
    if before['4']['amp_hold']:print('The previously armed performance is stopped. Start it again from its original controls.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='temporarily test the current v26 FPGA; otherwise read status only')
    parser.add_argument('--android-idle',action='store_true',help='operator confirms no Android recording is underway')
    parser.add_argument('--pause-held',action='store_true',help='allow stopping an armed, idle performance; restart manually afterwards')
    parser.add_argument('--retune',action='store_true',help='add a third capture with the released oscillator retuned to a new bin')
    parser.add_argument('--out',type=Path,help='new results directory (must not already exist)')
    args=parser.parse_args()
    board=Board()
    try:run(board,args)
    finally:board.device.close()


if __name__=='__main__':main()
