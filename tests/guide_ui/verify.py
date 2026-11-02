"""Check three-bank font contents and compare newly rendered PNGs to golden pixels."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FPGA = ROOT / 'fpga'
# Name, hierarchical page, focused row, confirmation, drum volume target.
CASES = [('home',0,1,0,0), ('tones',1,1,0,0), ('effects',2,2,0,0),
         ('loop_confirm',3,5,1,1), ('guide',4,1,0,0), ('settings',5,2,0,0),
         ('drums',3,1,0,1)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_font():
    # This retained legacy table is a reference only; panel_renderer.v does not
    # load it into FPGA RAM. The active ROMs are compact_ui_font0/1/2.hex.
    legacy = [int(s, 16) for s in (FPGA / 'compact_ui_font.hex').read_text().split()]
    banks = [[int(s, 16) for s in (FPGA / f'compact_ui_font{i}.hex').read_text().split()] for i in range(3)]
    assert len(legacy) == 4096
    assert [len(bank) for bank in banks] == [1024, 1024, 1024]
    packed = sum(banks, [])
    assert all(legacy[g * 16] == 0 for g in range(256)), 'Row 16 must remain blank'
    packing = json.loads((FPGA / 'font_packing.json').read_text(encoding='utf8'))
    glyph_slots = packing['font_used_words'] // 15
    for glyph in range(glyph_slots):
        for row in range(1, 16):
            assert packed[glyph * 15 + row - 1] == legacy[glyph * 16 + row], (glyph, row)
    assert all(word == 0 for word in packed[glyph_slots * 15:])
    return {'font_banks': 3, 'bank_words': 1024, 'bank_width_bits': 16,
            'font_words_used': glyph_slots * 15, 'all_glyph_rows_unchanged': True}


def verify_frames(frames, report_path=None):
    golden = HERE / 'results' / 'hierarchical'
    original = json.loads((golden / 'verification.json').read_text(encoding='utf8'))
    result = verify_font()
    result.update({
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'baseline_renderer_sha256': original['baseline_renderer_sha256'],
        'renderer_sha256': sha256(FPGA / 'panel_renderer.v'),
        'pixel_latency_cycles': 3,
        'pages': {},
    })
    for name, *_ in CASES:
        with Image.open(golden / f'{name}.png') as expected, Image.open(frames / f'{name}.png') as actual:
            assert expected.size == actual.size == (1024, 600)
            expected_bytes = expected.convert('RGB').tobytes()
            actual_bytes = actual.convert('RGB').tobytes()
        different = sum(expected_bytes[i:i+3] != actual_bytes[i:i+3] for i in range(0, len(actual_bytes), 3))
        assert different == 0, f'{name}: {different} pixels differ from the accepted image'
        result['pages'][name] = {
            'pixels_compared': 614400, 'pixels_different': different,
            'rgb_sha256': hashlib.sha256(actual_bytes).hexdigest(),
        }
    if report_path:
        report_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path, required=True, help='Directory containing the seven newly rendered hierarchical pages')
    parser.add_argument('--report', type=Path, help='Optional result JSON; keep the accepted results/verification.json unchanged')
    args = parser.parse_args()
    print(json.dumps(verify_frames(args.frames.resolve(), args.report), indent=2))
