"""Capture final PCM from the SRAM-loaded modal32 build and restore local controls."""
import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from verify32 import Board, FIELDS, PRESETS, FS, require, save_json, status, voice_payload, wait_for
from protocol import WHITE_KEYS

N = 4096
KEY = WHITE_KEYS.index(60)
FREQ = 440 * 2 ** ((60 - 69) / 12)
STEP = round(FREQ * 2**32 / FS)


def c4(board, gate):
    payload = voice_payload(0, gate, FREQ, timbre=4, level=.25, attack_ms=2,
                            decay_ms=10, sustain=1, release_ms=8)
    board.call(2, payload + bytes([0x80 | KEY]))


def capture(board, folder, tag, note_on, delay):
    old = board.call(22)['capture_id']
    board.call(21, bytes([1, int(note_on)]) + struct.pack('<HI', N, delay))
    result = {'trigger_delay_frames': delay}
    if note_on:
        require(board.call(22)['armed'], 'Capture trigger was not armed in silence')
        c4(board, 1)
    try:
        meta = wait_for(lambda: board.call(22), lambda s: s['ready'], 'capture ready', 2)
        require(meta['capture_id'] == (old + 1) % 65536 and meta['count'] == meta['target'] == N
                and meta['sample_rate'] == FS and not meta['error'], f'Wrong capture metadata: {meta}')
        result['capture'] = meta
        result['keyboard'] = board.call(9)
        require(result['keyboard']['pressed_mask'] == (1 << KEY if note_on else 0), 'Incorrect white-key mask')
        result['audio'] = board.call(4)
        result['gain'] = board.call(27)
        result['fx'] = board.call(25)
        result['voices'] = board.call(17)
        a, g, f, v = (result[k] for k in ('audio', 'gain', 'fx', 'voices'))
        require(a['gated'] == a['active'] == v['live_held'] == int(note_on)
                and not v['loop_held'] and a['amp_ready'] and a['amp_muted'], 'Unexpected voice or monitor state')
        require(not (a['overrun'] or a['clipped'] or a['watchdog'] or g['limited_frames'] or g['limiter_overrun']
                     or f['mask'] or f['overrun'] or f['clipped']), 'Output health or dry-path check failed')
    finally:
        if note_on:
            c4(board, 0)
    raw = bytearray()
    for offset in range(0, N, 6):
        n = min(6, N - offset)
        reply = board.call(23, struct.pack('<HHB', meta['capture_id'], offset, n))
        data = bytes.fromhex(reply['data'])
        require(reply['capture_id'] == meta['capture_id'] and reply['offset'] == offset
                and reply['count'] == n and len(data) == 2*n, f'Mismatched block at {offset}')
        raw.extend(data)
    require(zlib.crc32(raw) == meta['crc32'], 'Board / PC CRC mismatch')
    (folder / (tag + '.pcm')).write_bytes(raw)
    result['sha256'] = hashlib.sha256(raw).hexdigest()
    return result


def run(folder, build_report, gain_mode, select_piano, record_tail):
    build = json.loads(build_report.read_text())
    live_code = re.search(r'User Code is:\s*(0x[0-9a-f]+)\b',
                          (folder/'candidate_jtag.log').read_text(), re.I)
    require(build['validated'] and live_code and int(live_code.group(1),16) == int(build['user_code'],16),
            'Independent JTAG readback does not match validated candidate')
    require(not (folder/'silence.pcm').exists(), 'Use a fresh capture folder')
    original = json.loads((folder/'before_program.json').read_text())
    saved_timbre = original['11']['timbre']
    if select_piano:
        original['11']['timbre'] = 4
    board = Board()
    report = dict(sample_rate=FS, capture_length=N, c4_requested_hz=FREQ, white_key=KEY+1,
                  phase_step=STEP, c4_actual_hz=STEP*FS/2**32, timbre=4, level=.25,
                  gain_mode=gain_mode, user_code=build['user_code'], bitstream_sha256=build['sha256'],
                  original_timbre=saved_timbre, selected_timbre=original['11']['timbre'],
                  trigger_delay_frames=256, takes={})
    try:
        now = status(board)
        require(not (now['4']['active'] or now['4']['amp_hold'] or now['16']['length_set'] or
                    now['14']['layers'] or now['14']['recording'] or now['14']['pending_record'] or
                    now['22']['ready'] or now['22']['armed'] or now['22']['recording']) and now['16']['key_mode'] == 0,
                'Expected idle, freshly loaded candidate')
    except BaseException:
        board.device.close()
        raise
    try:
        board.fx(dict(PRESETS['off'], monitor_mute=1))
        board.call(5, bytes([gain_mode]))
        takes = [('silence',False,0), ('c4',True,256), ('c4_repeat',True,256)]
        if record_tail:
            takes.append(('c4_tail',True,10800))  # 221 ms into the held note
        for label, sound, delay in takes:
            # Clear old release tails before arming the next independent acquisition.
            board.call(3)
            wait_for(lambda: board.call(4), lambda a: not a['active'] and not a['amp_ready'] and a['amp_muted'], 'drain')
            board.call(6)
            wait_for(lambda: board.call(4), lambda a: a['amp_ready'] and a['amp_muted'], 'digital warmup')
            report['takes'][label] = capture(board, folder, label, sound, delay)
            save_json(folder/'capture.json', report)
            print(f'{label}: verified CRC {report["takes"][label]["capture"]["crc32"]:08X}', flush=True)
        report['result'] = 'passed'
    finally:
        try:
            board.call(3)
            board.call(21)
            board.restore(original)
            final = status(board)
            for op, fields in [('11',('timbre','level','focus','drum_mode','pattern','sensitivity','press','release')),
                               ('16',('key_mode','keyboard_level','drum_level')), ('27',('gain_mode',))]:
                require(all(final[op][f] == original[op][f] for f in fields), f'Unrestored panel settings ({op})')
            require(final['11']['locked'] and (not final['16']['key_mode'] or
                    (final['9']['calibrated'] and not final['9']['fault'])), 'Scan or HDMI not restored')
            require(all(final['25'][f] == original['25'][f] for f in FIELDS), 'Effects not restored')
            # Restore the original armed performance only once all notes have been released.
            if original['4']['amp_hold'] and not final['9']['pressed_mask'] and not final['4']['active']:
                board.call(6)
                wait_for(lambda: board.call(4), lambda a: a['amp_ready'] and a['amp_hold'], 'local warmup')
            report['restored'] = status(board)
        finally:
            board.device.close()
            save_json(folder/'capture.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--build-report', type=Path, default=HERE/'font_place2_report.json')
    parser.add_argument('--gain-mode', type=int, choices=(0,1,2), default=0)
    parser.add_argument('--select-piano', action='store_true', help='select the tested piano for local playing on completion')
    parser.add_argument('--record-tail', action='store_true', help='also capture C4 after the bright strike has decayed')
    args = parser.parse_args()
    run(args.folder.resolve(), args.build_report.resolve(), args.gain_mode, args.select_piano, args.record_tail)
