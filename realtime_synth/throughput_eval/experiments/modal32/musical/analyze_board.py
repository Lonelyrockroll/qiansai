"""Check C4 against the musical coefficient ROM, then compare strike and sustain spectra."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from live_analysis import FS, N, amplitude_spectrum, analyze, record


def verify(folder):
    count = analyze(folder,HERE/'modal32_coeffs.v')
    metadata = json.loads((folder/'capture.json').read_text())
    frequency = np.fft.rfftfreq(N,1/FS)
    windows = {}
    for name, delay in [('c4',256), ('c4_tail',10800)]:
        pcm, file = record(folder/(name+'.pcm'))
        take = metadata['takes'][name]
        assert take['trigger_delay_frames'] == delay
        assert take['capture']['crc32'] == file['crc32'] and take['sha256'] == file['sha256']
        power = amplitude_spectrum(pcm)**2
        high_power = power[frequency >= 4000].sum()
        windows[name] = dict(delay_ms=1000*delay/FS, capture_id=take['capture']['capture_id'],
                             rms=file['rms_pcm'], high_power=float(high_power),
                             high_to_total_db=float(10*np.log10(high_power/power.sum())),
                             centroid_hz=float(np.dot(power,frequency)/power.sum()))
    early, late = windows['c4'], windows['c4_tail']
    assert early['capture_id'] != late['capture_id']
    stats=dict(scope='FPGA final PCM, two matched C4 strikes sampled at different delays, each 4096 frames',
               gain_mode=metadata['gain_mode'], input_level=metadata['level'], windows=windows,
               high_band_power_change_db=float(10*np.log10(late['high_power']/early['high_power'])),
               high_to_total_change_db=late['high_to_total_db']-early['high_to_total_db'])
    (folder/'strike_decay.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps(stats,indent=2))
    return count


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    sys.exit(0 if verify(p.parse_args().folder.resolve()) == 32 else 1)
