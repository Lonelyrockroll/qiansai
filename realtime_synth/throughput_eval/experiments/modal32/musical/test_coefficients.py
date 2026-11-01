"""Check the musical ROM and estimate held C4 energy from the coefficients."""
import json
import math
import re

import numpy as np

from generate_musical import FIELD_WIDTHS, FS, HARD_BUDGET, HERE, decay_time, generate_bands, legacy_bands, source


def read_new_width_rom(path):
    text = path.read_text(encoding='ascii')
    values = {}
    for index, word in re.findall(r"8'd(\d+): coeff=76'h([a-f0-9]+)", text):
        value, fields = int(word, 16), []
        for width in reversed(FIELD_WIDTHS):
            fields.append(value & ((1 << width)-1))
            value >>= width
        assert value == 0
        values[int(index)] = tuple(reversed(fields))
    assert set(values) == set(range(192))
    return [[values[b*32 + i] for i in range(32)] for b in range(6)]


def c4_partials(rows, seconds, velocity=.25):
    step = round(440 * 2**(-9/12) * 2**32 / FS)
    frequencies = np.array([((step * r[0]) >> 16)*FS/2**32 for r in rows])
    amplitude = np.array([(r[1]+int((r[2]-r[1])*velocity))*np.exp(-seconds/decay_time(*r[3:5]))
                          for r in rows])
    return frequencies, amplitude


def white_key_counts(bands):
    counts = {}
    for k in range(32):
        midi = 36 + 12*(k//7) + (0,2,4,5,7,9,11)[k%7]
        step = round(440 * 2**((midi-69)/12) * 2**32 / FS)
        band = sum(step >= v for v in (11506199,23012398,46024797,92049593,184099186))
        counts[midi] = sum(((step*r[0]) >> 16) < 0x70000000 for r in bands[band])
    return counts


def high_band_db(rows, seconds):
    hz, amp = c4_partials(rows, seconds)
    return round(10*math.log10(np.sum(amp[hz>=2500]**2)/np.sum(amp**2)), 2)


def estimated_fft_peaks(rows):
    # Coefficient-only approximation in stuck-key steady gain. Omits hammer noise,
    # sine-table quantization and hardware rounding. Actual RTL and board captures
    # are separate checks. Final scaling mirrors gain 1 and 25% note velocity.
    t = np.arange(256, 4352, dtype=float) / FS
    signal = np.zeros(t.shape)
    hz, _ = c4_partials(rows, 0)
    for i, row in enumerate(rows):
        start = row[1] + ((row[2]-row[1])*16384 >> 16)
        signal += start*.25*.5*np.exp(-t/decay_time(*row[3:5]))*np.sin(math.tau*(hz[i]*t+row[5]/4096))
    signal = np.round(signal)
    hann = np.hanning(len(t))
    amps = 2*abs(np.fft.rfft((signal-signal.mean())*hann))/hann.sum()
    peaks = []
    for target in hz:
        guess = round(target*len(t)/FS)
        k = guess-1+int(np.argmax(amps[guess-1:guess+2]))
        assert amps[k] > amps[k-1] and amps[k] > amps[k+1]
        ref = max(.5, *amps[k-8:k-3], *amps[k+4:k+9])
        margin = 20*math.log10(amps[k]/ref)
        assert amps[k] >= 3 and margin >= 12, (k, amps[k], margin)
        peaks.append((k, amps[k], margin))
    assert len(set(p[0] for p in peaks)) == 32
    return dict(peak_count=len(peaks), min_peak_pcm=round(min(p[1] for p in peaks),3),
                min_contrast_db=round(min(p[2] for p in peaks),2))


def main():
    path = HERE/'modal32_coeffs.v'
    musical = read_new_width_rom(path)
    old, demo = legacy_bands(), read_new_width_rom(HERE.parent/'modal32_coeffs.v')
    assert path.read_text(encoding='ascii') == source() and musical == generate_bands()
    for b, regs in enumerate(musical):
        assert sum(r[2] for r in regs) == HARD_BUDGET
        assert all(0 < s <= h for _, s, h, *_ in regs)
        assert all(regs[i][0] < regs[i+1][0] for i in range(31))
        assert [r[0] for r in regs[:12]] == [r[0] for r in old[b][:12]]
    key_terms = {name: {f'tau_n{n}_s': round(decay_time(*regs[n-1][3:5]),3)
                        for n in ([1,12] if name=='v26' else [1,12,32])}
                 for name, regs in [('v26',old[2]), ('demo',demo[2]), ('musical',musical[2])]}
    band_energy = {name:{str(sec):high_band_db(regs,sec) for sec in (0., .05, .15, .3, .5)}
                   for name,regs in [('v26',old[2]), ('demo',demo[2]), ('musical',musical[2])]}
    assert band_energy['musical']['0.3'] < band_energy['demo']['0.3'] - 15
    note_stats = estimated_fft_peaks(musical[2])
    report = dict(scope='Coefficient ROM and analytic model; not RTL, hardware or acoustic measurements.',
                  x='C4; 25% velocity. Relative model energy for individual partials >= 2500 Hz versus total.',
                  sample_rate_hz=FS, first12_ratios='identical to v26 in all six registers',
                  C4_time_constants=key_terms, C4_high_band_db=band_energy, predicted_C4_4096_gain1=note_stats,
                  allowed_partials_by_white_key_midi=white_key_counts(musical))
    (HERE/'coefficient_report.json').write_text(json.dumps(report, indent=2)+'\n',encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
