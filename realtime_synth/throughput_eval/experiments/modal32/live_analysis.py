"""Measure the 32 predicted C4 peaks in board PCM. This program never opens a device."""
import argparse
import csv
import hashlib
import json
import re
import wave
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from verify_modal32 import FS, ROOT, TABLE, increments


N = 4096
DBIN = FS / N
MIN_AMPLITUDE = 3.0  # 16-bit PCM peak-amplitude units
MIN_CONTRAST_DB = 12.0
REFERENCE_FLOOR = 0.5  # never claim infinite contrast against digital zeros


def expected_frequencies(coefficients=ROOT/'modal32_coeffs.v'):
    project = ROOT.parents[2]
    key_map = (project/'control_white_keys/white_key_map.v').read_text()
    note_rom = (project/'rtl/note_rom.v').read_text()
    midi = int(re.search(r"5'd14:\s*note=7'd(\d+);", key_map)[1])
    step = int(re.search(rf"7'd{midi}:\s*step=32'd(\d+);", note_rom)[1])
    if midi != 60 or step != round(440 * 2**((60-69)/12) * 2**32 / FS):
        raise ValueError('H15, MIDI C4 and host DDS formula disagree')
    table = {int(a): int(v, 16) for _, a, v in TABLE.findall(coefficients.read_text())}
    if len(table) != 192:
        raise ValueError('32-partial coefficient table incomplete')
    return step, np.asarray(increments(step, table)) * FS / 2**32


def amplitude_spectrum(x):
    hann = np.hanning(N)
    x = np.asarray(x, dtype=float)
    if x.shape != (N,):
        raise ValueError(f'Expected {N} samples, got {x.shape}')
    return 2 * np.abs(np.fft.rfft((x-x.mean())*hann)) / hann.sum()


def ratio_db(peak, reference):
    return float(20*np.log10(max(peak, 1e-12)/max(reference, REFERENCE_FLOOR)))


def measure(signal, silence, expected):
    bins, baseline = amplitude_spectrum(signal), amplitude_spectrum(silence)
    peaks = []
    non_target = np.ones(len(bins), dtype=bool)
    non_target[0] = False
    for number, target in enumerate(expected, 1):
        center = int(round(target/DBIN))
        k = center-1 + int(np.argmax(bins[center-1:center+2]))
        non_target[center-4:center+5] = False
        maximum = bool(bins[k] > bins[k-1] and bins[k] > bins[k+1])
        # A local peak can straddle bins. Log-quadratic interpolation on a Hann
        # window estimates its position and amplitude without snapping it to the grid.
        offset = 0.0
        amp = float(bins[k])
        if maximum:
            left, mid, right = np.log(np.maximum(bins[k-1:k+2], 1e-12))
            offset = 0.5*(left-right)/(left-2*mid+right)
            amp = float(np.exp(mid-0.25*(left-right)*offset))
        fitted = (k+offset)*DBIN
        local = max(bins[k-8:k-3].max(), bins[k+4:k+9].max())
        quiet = max(baseline[k-1:k+2])
        contrast = ratio_db(amp, max(local, quiet))
        accepted = maximum and abs(fitted-target) <= DBIN/2 and amp >= MIN_AMPLITUDE and contrast >= MIN_CONTRAST_DB
        peaks.append(dict(partial=number, expected_hz=float(target),
                          stretch_vs_integer_harmonic_hz=float(target-number*expected[0]),
                          fft_bin=int(k), fitted_hz=float(fitted),
                          error_hz=float(fitted-target), amplitude_pcm=amp, silent_peak_pcm=float(quiet),
                          local_sideband_max_pcm=float(local), contrast_db=contrast, passed=bool(accepted)))
    k = np.flatnonzero(non_target)[int(np.argmax(bins[non_target]))]
    return peaks, bins, dict(hz=float(k*DBIN), amplitude_pcm=float(bins[k]))


def record(path):
    data = path.read_bytes()
    if len(data) != 2*N:
        raise ValueError(f'{path.name} has {len(data)} bytes, expected {2*N}')
    pcm = np.frombuffer(data, dtype='<i2').astype(float)
    return pcm, dict(file=path.name, sha256=hashlib.sha256(data).hexdigest(), crc32=zlib.crc32(data), samples=N,
                     absolute_peak_pcm=int(np.max(np.abs(pcm))), rms_pcm=float(np.sqrt(np.mean(pcm**2))))


def draw_plot(path, frequencies, takes, quiet, passed, scope):
    image = Image.new('RGB', (1200, 500), '#f8faf8')
    draw = ImageDraw.Draw(image)
    fonts = {n: ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', n) for n in (14, 17, 20, 29)}
    ink, gray, teal, orange = '#15353a', '#5f6d74', '#087771', '#ae5724'

    def label(x, y, s, size=17, fill=ink, anchor='la'):
        draw.text((x, y), s, font=fonts[size], fill=fill, anchor=anchor)

    label(30, 14, f'C4 单音实板频谱  ·  {passed} / 32 个预期分量通过', 29)
    label(31, 62, scope, 17, gray)
    x0, x1, y0, y1 = 81, 1163, 119, 349
    def x(hz):
        return x0 + hz*(x1-x0)/9000
    def y(db):
        return y1 - (min(-20, max(-110, db))+110)*(y1-y0)/90
    def db(amps):
        return 20*np.log10(np.maximum(amps, 1e-9)/32768)

    for v in range(-100, -19, 20):
        draw.line((x0,y(v),x1,y(v)), fill='#d5dedd')
        label(x0-9, y(v), str(v), 14, gray, 'rm')
    label(24, 91, 'dBFS', 14, gray)
    for v in range(0, 9001, 1000):
        label(x(v), y1+9, str(v//1000), 14, gray, 'mt')
    label(x1, y1+31, 'kHz', 14, gray, 'rt')
    masked = frequencies <= 9000
    for spec, color in ((quiet, '#ced2d1'), (takes[0][1], '#80a7a2')):
        draw.line([(x(h), y(a)) for h,a in zip(frequencies[masked],db(spec[masked]))], fill=color, width=1)
    for i, peak in enumerate(takes[0][0]):
        xp, yp = x(peak['fitted_hz']), y(db(peak['amplitude_pcm']))
        color = teal if all(rows[i]['passed'] for rows, _ in takes) else '#c3323d'
        if i >= 16 and color == teal:
            color = orange
        draw.ellipse((xp-3,yp-3,xp+3,yp+3), fill=color)
        if i in (0,7,15,23,31):
            label(xp,yp-7,str(i+1),14,color,'mb')
    label(33, 405, '绿色  1–16 分量', 20, teal)
    label(239, 405, '橙色  17–32 分量', 20, orange)
    label(515, 406, '灰线为静音参考；低于 −110 dBFS 的部分显示在底线。', 17, gray)
    label(34, 450, '图示第一遍弹奏的整窗频谱。每个通过点均符合频率、局部峰、最小幅度及信噪对照的判据。', 17, gray)
    image.save(path)


def analyze(folder,coefficients=ROOT/'modal32_coeffs.v'):
    step, expected = expected_frequencies(coefficients)
    quiet_pcm, quiet_meta = record(folder/'silence.pcm')
    files = [folder/'c4.pcm']
    if (folder/'c4_repeat.pcm').exists():
        files.append(folder/'c4_repeat.pcm')
    takes, meta, csv_rows = [], [], []
    for file in files:
        pcm, audio = record(file)
        peaks, bins, spill = measure(pcm, quiet_pcm, expected)
        takes.append((peaks, bins))
        audio.update(passed_count=sum(p['passed'] for p in peaks),
                     weakest=min(peaks, key=lambda p: p['amplitude_pcm']),
                     max_abs_frequency_error_hz=max(abs(p['error_hz']) for p in peaks),
                     min_contrast_db=min(p['contrast_db'] for p in peaks),
                     strongest_bin_outside_target_plus_minus_4_bins=spill)
        for p in peaks:
            csv_rows.append(dict(take=file.name, **p))
        meta.append(audio)
    passed = [i+1 for i in range(32) if all(rows[i]['passed'] for rows, _ in takes)]
    if any(len({p['fft_bin'] for p in rows}) != 32 for rows, _ in takes):
        raise ValueError('Different predicted partials landed on duplicate bins')
    capture_info = folder/'capture.json'
    if capture_info.exists():
        board = json.loads(capture_info.read_text(encoding='utf8'))['takes']
        for take in [quiet_meta, *meta]:
            name = Path(take['file']).stem
            hardware = board[name]['capture']
            if (take['crc32'] != hardware['crc32'] or take['sha256'] != board[name]['sha256']
                    or hardware['count'] != N or hardware['sample_rate'] != FS):
                raise ValueError(f'{name} capture metadata differs from the PCM')
            take.update(capture_id=hardware['capture_id'], first_frame=hardware['first_frame'])
        if len({take['capture_id'] for take in [quiet_meta, *meta]}) != 1+len(meta):
            raise ValueError('Capture IDs must differ for a repeat measurement')
    summary = dict(scope='Board-captured digital PCM, evaluated in the sample clock domain.',
                   coefficient_sha256=hashlib.sha256(coefficients.read_bytes()).hexdigest(),
                   note='MIDI 60, physical white key 15', dds_step=step, root_hz=float(expected[0]),
                   fs_hz=FS, n_fft=N, bin_spacing_hz=DBIN, window='Hann; one fixed entire capture, no peak-selected time window',
                   criteria=dict(min_peak_pcm=MIN_AMPLITUDE, max_frequency_error_hz=DBIN/2,
                                 min_contrast_db=MIN_CONTRAST_DB, min_reference_pcm=REFERENCE_FLOOR,
                                 reference='max of same-take sidebands at 4..8 bins on both sides and quiet capture in peak bin +/-1',
                                 require_strict_local_maximum=True),
                   silence=quiet_meta, takes=meta, repeated=len(takes)==2,
                   repeat_pcm_bit_identical=(meta[0]['sha256']==meta[1]['sha256']) if len(meta)==2 else None,
                   counted_in_every_available_take=len(passed), passed_partials=passed)
    with (folder/'c4_peaks.csv').open('w', newline='', encoding='utf8') as stream:
        writer=csv.DictWriter(stream, fieldnames=csv_rows[0].keys())
        writer.writeheader(); writer.writerows(csv_rows)
    frequencies = np.fft.rfftfreq(N, 1/FS)
    quiet_bins = amplitude_spectrum(quiet_pcm)
    np.savetxt(folder/'c4_spectra.csv', np.column_stack([frequencies,quiet_bins]+[bins for _,bins in takes]),
               delimiter=',', header=','.join(['hz','silence']+[f.stem for f in files]), comments='')
    (folder/'c4_peaks.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf8')
    subtitle = f'板载数字 PCM  |  串口触发 {len(takes)} 次 C4  |  {FS:,.3f} Hz  |  {N} 点 Hann 窗  |  频点间隔 {DBIN:.2f} Hz'
    draw_plot(folder/'c4_peaks.png', frequencies, takes, quiet_bins, len(passed), subtitle)
    print(f'{len(passed)}/32 in all {len(takes)} available take(s)')
    return len(passed)


def selftest():
    _, expected = expected_frequencies()
    silence = np.zeros(N)
    for name, count in [('C4_16_components.wav', 16), ('C4_32_components.wav', 32)]:
        with wave.open(str(ROOT/'audition'/name)) as wav:
            assert wav.getsampwidth()==2 and wav.getnchannels()==1
            wav.setpos(2048)
            pcm = np.frombuffer(wav.readframes(N), dtype='<i2').astype(float)/4
        rows, _, _ = measure(pcm,silence,expected)
        assert [r['partial'] for r in rows if r['passed']] == list(range(1,count+1)), name
    assert not any(p['passed'] for p in measure(silence,silence,expected)[0])
    print('PASS zero, 16-only and 32-component RTL controls')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path, nargs='?')
    parser.add_argument('--coefficients', type=Path, default=ROOT/'modal32_coeffs.v')
    parser.add_argument('--self-test', action='store_true')
    args=parser.parse_args()
    if args.self_test:
        selftest()
    if args.folder:
        raise SystemExit(0 if analyze(args.folder,args.coefficients.resolve()) == 32 else 1)
    if not args.self_test:
        parser.error('provide a capture folder or --self-test')
