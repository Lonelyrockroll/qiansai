"""Muted v30 guide controls and real-time playback check on COM6 (no sound generation)."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board


def check(folder):
    folder.mkdir(parents=True, exist_ok=True)
    board = Board()
    observations = []
    def query():
        value = board.call(31, b'\0')
        observations.append(value)
        return value
    def action(code):
        # The ordinary control ACK means accepted; use a separate status poll.
        board.call(31, bytes([code+1]))
        time.sleep(.025)
        return query()
    try:
        before = board.state()
        (folder/'before_checks.json').write_text(json.dumps(before, indent=2)+'\n')
        assert before['4']['firmware'] == 30
        assert not before['4']['active'] and not before['16']['length_set']
        assert not any(before['22'][flag] for flag in ('recording','armed','ready'))
        initial = query()
        assert initial['guide_demo'], 'Leave a user-uploaded score intact'
        board.call(3)
        s = action(3)
        assert s['guide_valid'] and s['guide_count'] == 56 and s['guide_duration_cs'] == 1600
        assert s['guide_time_cs'] == 0 and not s['guide_playing']
        s = action(5)
        assert s['guide_time_cs'] == 0 and s['guide_mask'] == 1 << 14 and not s['guide_playing'], s
        s = action(5)
        assert s['guide_time_cs'] == 50 and s['guide_mask'] == 1 << 14, s
        s = action(6)
        assert s['guide_time_cs'] == 0 and s['guide_mask'] == 1 << 14, s
        speed = s['guide_speed']
        for step in range(4):
            s = action(8)
            assert s['guide_speed'] == (speed+step+1)%4, s
        assert s['guide_speed'] == 2
        action(3)
        action(1)
        start = time.monotonic()
        time.sleep(.35)
        s = action(2)
        assert 25 <= s['guide_time_cs'] <= 60 and not s['guide_playing'], s
        frozen = s['guide_time_cs']
        time.sleep(.15)
        assert query()['guide_time_cs'] == frozen
        action(4)
        time.sleep(.15)
        s = query()
        assert s['guide_playing'] and s['guide_time_cs'] > frozen
        action(3)
        action(1)
        start = time.monotonic()
        sampled_masks = set()
        while time.monotonic()-start < 18:
            s = query()
            sampled_masks.add(s['guide_mask'])
            if not s['guide_playing']:
                break
            time.sleep(.12)
        elapsed = time.monotonic()-start
        assert 15.7 < elapsed < 16.5, elapsed
        assert s['guide_time_cs'] == 0 and s['guide_mask'] == 0 and not s['guide_playing'], s
        assert len(sampled_masks) >= 6, sampled_masks
        board.call(10, bytes([6, 9]))
        after = board.state()
        assert after['11']['locked'] and after['11']['focus'] == 9
        assert after['9']['calibrated'] and not after['9']['fault'] and after['9']['pressed_mask'] == 0
        assert after['4']['amp_muted'] and not after['4']['active'] and not after['4']['overrun']
        result = dict(result='passed', scope='Real FPGA via PC UART. Android Bluetooth upload and screen appearance require separate observation.',
                      builtin_play_seconds=elapsed, unique_target_masks=sorted(sampled_masks),
                      controls='start/pause/resume/restart/next/previous/four speeds/end clears',
                      after=after, guide=observations)
        (folder/'guide_board.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ('after','guide')}, indent=2))
    finally:
        try:
            board.call(3)
            board.call(31, bytes([4]))
        finally:
            board.device.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    check(parser.parse_args().folder)
