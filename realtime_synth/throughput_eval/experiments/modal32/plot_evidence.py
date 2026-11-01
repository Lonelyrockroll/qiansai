"""Draw the measured single-note FFT from the candidate's final PCM simulation."""
import csv
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
data = json.loads((root / 'modal32_validation.json').read_text(encoding='utf8'))
with (root / 'evidence/single_spectrum.csv').open() as f:
    spectrum = list(csv.DictReader(f))

image = Image.new('RGB', (1160, 418), '#f8f9f6')
draw = ImageDraw.Draw(image)
ink, secondary, line = '#172f37', '#49636a', '#cedad8'
fonts = {size: ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', size) for size in (14, 16, 19, 28)}


def caption(x, y, value, size=16, color=ink, anchor=None):
    draw.text((x, y), value, font=fonts[size], fill=color, anchor=anchor)


def x_for(hz):
    return 76 + hz * 1040 / 9000


def y_for(amp):
    dbfs = max(-100, 20 * math.log10(max(1e-10, amp) / 32768))
    return 302 - (dbfs + 100) * 194 / 65


caption(32, 17, '一个琴键的 32 个加法分量', 28)
caption(34, 63, 'RTL 仿真 · 最终数字输出 · 测试基频 262.26 Hz · 48,828.125 次采样/秒 · 2048 点 Hann 窗', 16, secondary)
for db in (-100, -80, -60, -40):
    y = y_for(32768 * 10 ** (db / 20))
    draw.line((76, y, 1116, y), fill=line)
    caption(67, y, str(db), 14, secondary, 'rm')
caption(27, 91, 'dBFS', 14, secondary)
for hz in range(0, 9001, 1000):
    caption(x_for(hz), 310, str(hz // 1000), 14, secondary, 'mt')
caption(1115, 330, 'kHz', 14, secondary, 'rt')
points = [(x_for(float(r['Hz'])), y_for(float(r['full32']))) for r in spectrum if float(r['Hz']) <= 9000]
draw.line(points, fill='#8ea7a9', width=1)
for n, peak in enumerate(data['single_spectrum'], 1):
    x, y = x_for(peak['fitted_hz']), y_for(peak['amplitude_pcm'])
    color = '#116d61' if n <= 16 else '#ad561e'
    draw.ellipse((x-3, y-3, x+3, y+3), fill=color)
    if n in (1, 8, 16, 24, 32):
        caption(x, y-6, str(n), 14, color, 'mb')
caption(34, 368, '绿色  1–16 路', 19, '#116d61')
caption(230, 368, '橙色  17–32 路', 19, '#ad561e')
caption(452, 370, '单独关第 12 路，原频点下降 80.68 dB。', 16, secondary)
image.save(root / 'evidence/single_note_32.png')
