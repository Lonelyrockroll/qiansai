"""Create and render the two-page public-domain Twinkle score demonstration.

Dependencies: reportlab, Pillow, Poppler pdftoppm. No temporary absolute input
paths are required. A Microsoft YaHei TrueType font is used on Windows; another
Chinese TrueType font can be supplied via --font or SCORE_CJK_FONT.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zlib

from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, STORED_HEIGHT = 1024, 600, 512
THRESHOLD = 180
# Each row is one 4/4 bar. '-' sustains the preceding note for one more beat.
BARS = [
    ('1', '1', '5', '5'), ('6', '6', '5', '-'),
    ('4', '4', '3', '3'), ('2', '2', '1', '-'),
    ('5', '5', '4', '4'), ('3', '3', '2', '-'),
    ('5', '5', '4', '4'), ('3', '3', '2', '-'),
    ('1', '1', '5', '5'), ('6', '6', '5', '-'),
    ('4', '4', '3', '3'), ('2', '2', '1', '-'),
]
NAMES = {'1': 'C4', '2': 'D4', '3': 'E4', '4': 'F4', '5': 'G4', '6': 'A4'}
MIDI = {'1': 60, '2': 62, '3': 64, '4': 65, '5': 67, '6': 69}


def font_path(requested):
    candidates = [requested, os.environ.get('SCORE_CJK_FONT')]
    candidates.append(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise SystemExit('Chinese TrueType font unavailable; pass --font /path/to/font.ttf (or .ttc).')


def top_text(pdf, x, top, text, size, font='CJK', align='left'):
    pdf.setFont(font, size)
    draw = {'left': pdf.drawString, 'center': pdf.drawCentredString, 'right': pdf.drawRightString}[align]
    draw(x, HEIGHT - top, text)


def create_pdf(path, font):
    pdfmetrics.registerFont(TTFont('CJK', str(font), subfontIndex=0))
    pdf = canvas.Canvas(str(path), pagesize=(WIDTH, HEIGHT), pageCompression=1, invariant=1)
    pdf.setTitle('小星星 - 32白键曲谱示范')
    pdf.setAuthor('Tang Synth project')
    pdf.setSubject('传统旋律，项目自行排版；两页大字简谱，每页6小节，C调4/4拍。')
    for page in range(2):
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setStrokeColorRGB(0, 0, 0)
        top_text(pdf, 48, 55, '小星星', 34)
        top_text(pdf, 210, 53, '32白键 / 大字简谱', 17)
        top_text(pdf, 976, 52, f'{page + 1} / 2', 28, 'Helvetica-Bold', 'right')
        top_text(pdf, 48, 91, '1 = C    4/4拍    数字一拍，横线延长一拍', 16)
        top_text(pdf, 976, 91, f'第 {page * 6 + 1}-{page * 6 + 6} 小节', 16, align='right')
        pdf.setLineWidth(1.2)
        pdf.line(48, HEIGHT - 108, 976, HEIGHT - 108)

        # Three systems, two bars per system, with four equal beat positions.
        for row in range(3):
            top = 190 + row * 126
            for column in range(2):
                bar_index = page * 6 + row * 2 + column
                origin = 48 + column * 464
                top_text(pdf, origin + 8, top - 48, f'{bar_index + 1:02}', 11, 'Helvetica')
                for beat, symbol in enumerate(BARS[bar_index]):
                    x = origin + 56 + beat * 100
                    if symbol == '-':
                        pdf.setLineWidth(3.7)
                        pdf.line(x - 18, HEIGHT - top + 18, x + 18, HEIGHT - top + 18)
                        top_text(pdf, x, top + 26, '延长', 12, align='center')
                    else:
                        top_text(pdf, x, top, symbol, 58, 'Helvetica-Bold', 'center')
                        top_text(pdf, x, top + 26, NAMES[symbol], 13, 'Helvetica', 'center')
                pdf.setLineWidth(1.7)
                separator = origin + 448
                pdf.line(separator, HEIGHT - top - 3, separator, HEIGHT - top + 43)
                if bar_index == len(BARS) - 1:
                    pdf.setLineWidth(3.4)
                    pdf.line(separator + 6, HEIGHT - top - 3, separator + 6, HEIGHT - top + 43)

        pdf.setLineWidth(0.8)
        pdf.line(48, HEIGHT - 513, 976, HEIGHT - 513)
        top_text(pdf, 48, 540, '音名对应：1=C4  2=D4  3=E4  4=F4  5=G4  6=A4', 14)
        top_text(pdf, 976, 540, '手机翻页 · 点按 B 返回', 14, align='right')
        top_text(pdf, 48, 572, '传统旋律《小星星》 / 本项目重新排版，无需黑键。', 12)
        top_text(pdf, 976, 572, '接下一页' if page == 0 else '全曲结束', 12, align='right')
        pdf.showPage()
    pdf.save()


def render_pdf(pdf, output, tool):
    for page in range(1, 3):
        for height, suffix in ((HEIGHT, 'original'), (STORED_HEIGHT, 'storage')):
            prefix = output / f'page-{page:02}-{suffix}'
            subprocess.run([tool, '-f', str(page), '-l', str(page), '-singlefile', '-png',
                            '-scale-to-x', str(WIDTH), '-scale-to-y', str(height),
                            str(pdf), str(prefix)], check=True)
            with Image.open(prefix.with_suffix('.png')) as image:
                assert image.size == (WIDTH, height), (image.size, height)


def encode_raw(image):
    rgb = image.convert('RGB')
    pixels = rgb.tobytes()
    packed = bytearray(WIDTH * STORED_HEIGHT // 8)
    for index in range(WIDTH * STORED_HEIGHT):
        red, green, blue = pixels[index * 3:index * 3 + 3]
        luminance = (77 * red + 150 * green + 29 * blue) >> 8
        if luminance < THRESHOLD:
            packed[index >> 3] |= 1 << (7 - (index & 7))
    return bytes(packed)


def encode_rle(raw):
    encoded = bytearray()
    start = 0
    while start < len(raw):
        end = start + 1
        while end < len(raw) and end - start < 255 and raw[end] == raw[start]:
            end += 1
        encoded.extend((end - start, raw[start]))
        start = end
    return bytes(encoded)


def decode_rle(encoded):
    assert len(encoded) % 2 == 0
    result = bytearray()
    for count, value in zip(encoded[::2], encoded[1::2]):
        assert count != 0
        result.extend([value] * count)
    return bytes(result)


def decode_raw(raw):
    assert len(raw) == 65536
    # PIL mode 1 uses 1=white, so invert our 1=black representation.
    return Image.frombytes('1', (WIDTH, STORED_HEIGHT), bytes(value ^ 255 for value in raw)).convert('L')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preprocess(output, pdf, font):
    metadata = {
        'title': '小星星', 'provenance': 'Traditional public-domain melody; project typesetting, not a reproduced score.',
        'page_count': 2, 'page_size': [WIDTH, HEIGHT], 'storage_size': [WIDTH, STORED_HEIGHT],
        'format': '1bpp, row-major, MSB-left, 1=black, no row padding',
        'threshold': THRESHOLD, 'luminance': '(77*R + 150*G + 29*B) >> 8',
        'transform': 'fit PDF to 1024x600 without crop, then scale Y by 512/600',
        'rle': 'alternating uint8 count (1..255), uint8 value; no header',
        'crc32': 'IEEE CRC32 of the decoded 65536-byte raw bitmap; hexadecimal',
        'font_sha256': sha(font), 'pdf_sha256': sha(pdf), 'pages': [],
        'bars': [list(bar) for bar in BARS],
        'midi_notes': MIDI, 'beats_per_bar': 4, 'total_beats': 48,
    }
    for page in range(1, 3):
        stem = f'page-{page:02}'
        with Image.open(output / f'{stem}-storage.png') as image:
            raw = encode_raw(image)
        encoded = encode_rle(raw)
        assert decode_rle(encoded) == raw
        (output / f'{stem}.bin').write_bytes(raw)
        (output / f'{stem}.rle').write_bytes(encoded)
        decoded = decode_raw(raw)
        decoded.save(output / f'{stem}-mono-512.png')
        # Matches the display lookup row=floor(y*512/600), not a filtered scale.
        restored = Image.new('L', (WIDTH, HEIGHT), 255)
        for y in range(HEIGHT):
            source_y = y * STORED_HEIGHT // HEIGHT
            restored.paste(decoded.crop((0, source_y, WIDTH, source_y + 1)), (0, y))
        restored.save(output / f'{stem}-restored-600.png')
        metadata['pages'].append({
            'page': page, 'bars': [page * 6 - 5, page * 6],
            'raw_file': f'{stem}.bin', 'rle_file': f'{stem}.rle',
            'raw_bytes': len(raw), 'rle_bytes': len(encoded),
            'crc32': f'{zlib.crc32(raw) & 0xffffffff:08X}',
            'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'rle_sha256': hashlib.sha256(encoded).hexdigest(),
            'black_pixels': sum(byte.bit_count() for byte in raw),
        })
    (output / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', help='Chinese TrueType font; default Microsoft YaHei on Windows')
    parser.add_argument('--pdftoppm', help='Poppler executable; default PATH lookup')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/pdf/score-demo.pdf')
    parser.add_argument('--no-copy-asset', action='store_true', help='Do not update the Android demonstration asset')
    args = parser.parse_args()
    font = font_path(args.font)
    tool = args.pdftoppm or shutil.which('pdftoppm')
    if not tool:
        raise SystemExit('Poppler pdftoppm is required to render and verify the PDF.')
    pdf = args.output.resolve()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    output = pdf.with_suffix('')
    output.mkdir(parents=True, exist_ok=True)
    create_pdf(pdf, font)
    render_pdf(pdf, output, tool)
    result = preprocess(output, pdf, font)
    if not args.no_copy_asset:
        asset = ROOT / 'realtime_synth/android_recorder/src/main/assets/score-demo.pdf'
        asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, asset)
        assert sha(asset) == result['pdf_sha256']
    print(json.dumps({'pdf': str(pdf), 'pages': result['pages']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
