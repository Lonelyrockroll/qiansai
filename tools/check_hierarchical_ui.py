"""Verify the UI after SRAM loading, with the known initial envelope supplied by the caller."""
import argparse
import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'realtime_synth/control_meter_l8'))
from verify_board import Board


def check(output, initial_envelope, test_key):
    board = Board()
    before = None
    results = {}

    def selected(page, row):
        current = board.call(36)
        value = board.call(36, bytes([1, page, row, 1, current['epoch']]))
        assert (value['page'], value['cursor']) == (page, row) and not value['pending'], value
        assert not value['monitor_open'] and not value['score_visible'], value
        return value

    def execute(value):
        assert not value['pending'], value
        return board.call(36, bytes([2, 1, value['epoch']]))

    def item(page, row):
        return execute(selected(page, row))

    def settled_fx(mask):
        end = time.monotonic() + 2
        while time.monotonic() < end:
            state = board.call(25)
            if not state['pending'] and state['mask'] == mask:
                return state
            time.sleep(.01)
        raise AssertionError(state)

    try:
        initial = board.state()
        loop = board.call(14)
        guide = board.call(31)
        assert not initial['4']['amp_hold'] and not initial['4']['active'], initial['4']
        assert not initial['9']['pressed_mask'] and not loop['recording'] and not loop['playing']
        assert not guide['guide_playing'] and not guide['guide_loading'], guide
        assert not board.call(32)['score_visible']
        navigation = board.call(36)
        assert navigation['supported'] and not any(navigation[k] for k in ('monitor_open', 'pending', 'score_visible'))
        assert not any(initial['22'][k] for k in ('armed', 'recording', 'ready'))
        before = initial
        results['before'] = initial
        pages = []
        for page in range(1, 6):
            opened = item(0, page)
            assert (opened['page'], opened['cursor']) == (page, 1), opened
            returned = item(page, 0)
            assert (returned['page'], returned['cursor']) == (0, page), returned
            pages.append(opened)
        results['pages'] = pages

        tones = []
        for row, timbre in enumerate((4, 0, 1, 2, 3), 1):
            item(1, row)
            state = board.call(11)
            assert state['timbre'] == timbre, state
            tones.append(state)
        results['tones'] = tones

        effects = []
        for row, mask in enumerate((0, 1, 2, 4, 7), 1):
            item(2, row)
            effects.append(settled_fx(mask))
        results['effects'] = effects

        confirmed = item(3, 5)
        assert confirmed['confirm'], confirmed
        cancelled = selected(3, 4)
        assert not cancelled['confirm'], cancelled
        assert board.call(14)['layers'] == loop['layers']
        results['clear_without_erasing'] = [confirmed, cancelled]

        speeds = []
        for _ in range(4):
            item(4, 3)
            speeds.append(board.call(31))
        assert [x['guide_speed'] for x in speeds] == [(guide['guide_speed'] + i) % 4 for i in range(1, 5)]
        results['guide_speed_cycle'] = speeds

        item(5, 5)
        assert board.call(11)['pattern']
        board.call(10, bytes([3]))
        nav = board.call(36)
        assert not board.call(11)['pattern'] and (nav['page'], nav['cursor']) == (0, 0)
        results['pattern_panic_home'] = nav

        item(5, 4)
        assert board.call(34)['monitor']
        board.call(36, bytes([3]))
        assert not board.call(34)['monitor']
        results['spectrum_entry_exit'] = board.call(36)
        results['result'] = 'passed'
    finally:
        try:
            if before is not None:
                board.call(10, bytes([3]))
                # Envelope and single-key selector are not included in v32 status;
                # do not guess them from the last sampled ADC channel.
                board.call(7, struct.pack('<BBB8H', before['16']['key_mode'], test_key,
                    before['11']['timbre'], before['16']['keyboard_level'],
                    before['11']['press'], before['11']['release'],
                    *initial_envelope, before['11']['sensitivity']))
                board.fx(before['25'])
                for _ in range(4):
                    if board.call(31)['guide_speed'] == guide['guide_speed']:
                        break
                    item(4, 3)
                assert board.call(31)['guide_speed'] == guide['guide_speed']
                if before['16']['key_mode']:
                    time.sleep(.8)
                selected(0, 0)
                after = board.state()
                assert after['4']['amp_muted'] and not after['4']['active'], after['4']
                assert after['11']['timbre'] == before['11']['timbre']
                assert after['16']['keyboard_level'] == before['16']['keyboard_level']
                assert after['16']['drum_level'] == before['16']['drum_level']
                assert after['25']['mask'] == before['25']['mask']
                results['after'] = after
                results['navigation_after'] = board.call(36)
                results['restored_known_envelope'] = list(initial_envelope)
                results['restored_test_key'] = test_key
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        finally:
            board.device.close()
    print('PASS six pages, five tones, five FX presets, clear cancellation, guide speed, pattern panic and monitor return; restored muted home')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--initial-envelope', type=int, nargs=4, required=True,
                        metavar=('ATTACK', 'DECAY', 'SUSTAIN', 'RELEASE'),
                        help='Known raw envelope values configured before this test; not discoverable from v32 status')
    parser.add_argument('--test-key', type=int, required=True, choices=range(32),
                        help='Known single-channel test selector, normally 12')
    args = parser.parse_args()
    check(args.output, args.initial_envelope, args.test_key)
