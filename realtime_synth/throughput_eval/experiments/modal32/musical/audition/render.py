"""Compile all three real tone cores, render the same strikes, and compare their output."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np


HERE = Path(__file__).resolve().parent
MODAL = HERE.parents[1]
BASE = MODAL.parents[2] / 'control_key_gain'
FS = 50_000_000 / 1024
FRAME_COUNT = 38000
TONE_LENGTH = 24000
LISTEN_GAIN = 2
NOTES = {'C4':60, 'E4':64, 'G4':67, 'C6':84}
VARIANTS = ('original_v26', 'bright_demo32', 'musical32')


def sources(name):
    original = name == 'original_v26'
    core = BASE/'piano_modal_mixed.v' if original else MODAL/'modal32.v'
    files = [HERE/'tb_tone.v', core, BASE/'piano_modal_tables_compact.v']
    if not original:
        coeff = MODAL/('modal32_coeffs.v' if name == 'bright_demo32' else 'musical/modal32_coeffs.v')
        files.append(coeff)
    return files


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_one(name):
    files = sources(name)
    signature = {str(p.relative_to(MODAL.parents[2])):digest(p) for p in files}
    cache = HERE/'captures'/name
    cache.mkdir(parents=True,exist_ok=True)
    index = cache/'manifest.json'
    if index.is_file():
        old = json.loads(index.read_text())
        if old['inputs'] == signature and all((cache/(n+'.pcm')).is_file() and
                  digest(cache/(n+'.pcm')) == old['notes'][n]['sha256'] for n in NOTES):
            return old
    with tempfile.TemporaryDirectory(dir=HERE) as directory:
        work=Path(directory)
        binary=work/'tone.vvp'
        opts = ['-DORIGINAL16'] if name=='original_v26' else []
        subprocess.run([shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe',
                        '-g2012',*opts,'-s','tb_tone','-o',binary,*files],check=True,cwd=work)
        def strike(pair):
            voice,(note,midi) = pair
            step = round(440 * 2**((midi-69)/12) * 2**32/FS)
            pcm = cache/(note+'.pcm')
            result = subprocess.run([shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe',binary,
                f'+step={step}', f'+voice={voice}',f'+output={pcm.as_posix()}'],
                check=True,capture_output=True,text=True,timeout=300,cwd=work)
            match = re.search(r'PASS early_nonzero=([0-9a-f]{8}) alive_at_2048=([0-9a-f]{8})',result.stdout)
            if not match or pcm.stat().st_size != FRAME_COUNT*2:
                raise ValueError(result.stdout+result.stderr)
            data = np.fromfile(pcm,dtype='<i2')
            if not np.any(data) or np.any(data[-128:]):
                raise ValueError('Missing tone or release failed')
            entry=dict(voice=voice, midi=midi, step=step, sha256=digest(pcm),
                early_nonzero_mask=match[1], early_nonzero_count=int(match[1],16).bit_count(),
                active_mask_at_frame2048=match[2], active_count_at_frame2048=int(match[2],16).bit_count())
            print(f'{name} {note}: {entry["early_nonzero_count"]} contributing components',flush=True)
            return note,entry
        with ThreadPoolExecutor(max_workers=2) as pool:
            notes=dict(pool.map(strike,enumerate(NOTES.items())))
    report = dict(inputs=signature, notes=notes)
    index.write_text(json.dumps(report,indent=2)+'\n')
    return report


def measures(x, start, length):
    # Integrated Hann-window spectral power, not a count of audible oscillators.
    y = x[start:start+length].astype(float)
    bins = np.fft.rfftfreq(length, 1/FS)
    power = np.abs(np.fft.rfft((y-y.mean())*np.hanning(length)))**2
    floor = 1e-16
    return {'high_to_total_db':float(10*np.log10(max(floor,power[bins>=4000].sum()/power.sum()))),
            'centroid_hz':float((power*bins).sum()/power.sum()),'rms_pcm':float(np.sqrt(np.mean(y*y)))}


def save_wav(path,a):
    peak=int(np.max(np.abs(a)))
    if peak >= 32767: raise ValueError(f'Shared gain clipped {path.name} ({peak})')
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,round(FS),0,'NONE','not compressed'))
        f.writeframes(a.astype('<i2').tobytes())
    with wave.open(str(path),'rb') as f:
        assert np.array_equal(np.frombuffer(f.readframes(f.getnframes()),dtype='<i2'),a)
    return {'peak_pcm':peak, 'clipped_samples':0, 'sha256':digest(path)}


def phrase(tones):
    # C4, E4, G4, then all three together and finally C6. Keep the same
    # note waveforms and note lengths in each take. Add overlapping samples.
    hits=[(0,'C4'),(.27,'E4'),(.54,'G4'),(1.25,'C4'),(1.25,'E4'),(1.25,'G4'),(2.15,'C6')]
    y=np.zeros(round(3.0*FS),dtype=np.int32)
    for time,note in hits:
        start=round(time*FS)
        y[start:start+FRAME_COUNT] += tones[note]
    return y


def analyze():
    result={'scope':'Tone-core RTL sample output. Chord is linear superposition, before limiter, FX and analog playback.',
        'sample_rate':FS,'wav_rate':round(FS),'dds_level':16384,'attack':672,'release':8,'key_down_frames':TONE_LENGTH,
        'shared_linear_listening_gain':LISTEN_GAIN,'comparison_order':list(VARIANTS),
        'spectral_windows':{'early':'frames 256..2303 (5.24..47.17 ms)','late':'frames 10800..14895 (221.18..305.05 ms)'},
        'high_band':'4 kHz to Nyquist','models':{}}
    takes=[]; chords=[]
    for name in VARIANTS:
        cache=HERE/'captures'/name
        info=json.loads((cache/'manifest.json').read_text())
        tones={n: np.fromfile(cache/(n+'.pcm'),dtype='<i2').astype(np.int32) for n in NOTES}
        renders={}
        for note,x in tones.items():
            pcm_peak=int(np.max(np.abs(x)))
            if pcm_peak>=32767: raise ValueError(f'{name}/{note} clipped in core')
            renders[note] = dict(early=measures(x,256,2048),late=measures(x,10800,4096),peak_pcm=pcm_peak,
                                  contributing=info['notes'][note]['early_nonzero_count'],
                                  alive_at_2048=info['notes'][note]['active_count_at_frame2048'])
        takes.append(tones['C4']*LISTEN_GAIN)
        chords.append(phrase(tones)*LISTEN_GAIN)
        result['models'][name]={'tones':renders,'phrase_wav':save_wav(HERE/(name+'_phrase.wav'),chords[-1])}
    for name,clips in [('C4_compare.wav',takes),('phrase_compare.wav',chords)]:
        parts=[]
        for clip in clips:
            if parts: parts.append(np.zeros(round(.25*FS),dtype=np.int32))
            parts.append(clip)
        result[name]=save_wav(HERE/name,np.concatenate(parts))
    for name in VARIANTS[1:]:
        for n in ('C4','C6'):
            x=result['models'][name]['tones'][n];ref=result['models']['original_v26']['tones'][n]
            for window in ('early','late'):
                x[window]['high_to_total_delta_vs_original_db']=x[window]['high_to_total_db']-ref[window]['high_to_total_db']
    (HERE/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    for name in VARIANTS:
        x=result['models'][name]['tones']['C4']
        print(name,'C4 early/late >=4kHz relative dB:',x['early']['high_to_total_db'],x['late']['high_to_total_db'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--render',choices=VARIANTS,nargs='+')
    p.add_argument('--analyze',action='store_true')
    args=p.parse_args()
    if args.render:
        with ThreadPoolExecutor(max_workers=len(args.render)) as pool:list(pool.map(render_one,args.render))
    if args.analyze:analyze()
