"""Render all audition variants from one HDL phrase with a common output gain."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import wave

import numpy as np
from reference import Effects,FS

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT.parent/'tmp/effects_enhance'
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from fx_tools import PRESETS,LEGACY_PRESETS


def main():
    phrase=WORK/'sim/phrase.pcm'
    x=np.fromfile(phrase,dtype='<i2')
    assert len(x)==390625
    spec=importlib.util.spec_from_file_location('old_effects',Path(__file__).with_name('baseline_reference.py'))
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    output=ROOT/'output/effects-v32p2'
    output.mkdir(parents=True,exist_ok=True)
    rendered={}
    for prefix,model,presets in [('new',Effects,PRESETS),('previous',old.Effects,LEGACY_PRESETS)]:
        for name in ('off','reverb','delay','chorus'):
            p=presets[name]
            fx=model(mask=p['mask'],r=p['reverb_mix'],d=p['delay_mix'],c=p['chorus_mix'],time=p['delay_time'],
                     feedback=p['feedback'],room=p['room'],rate=p['rate'],depth=p['depth'])
            for _ in range(20000):fx.step(0)
            audio=np.array([fx.step(int(v)) for v in x],dtype=np.int32)
            if hasattr(fx,'clipped_count'):assert fx.clipped_count==0,(name,fx.clipped_count)
            rendered[prefix+'_'+name]=audio
            print(prefix,name,'peak',int(np.max(abs(audio))),flush=True)
    peak=max(int(np.max(abs(x))) for x in rendered.values())
    gain=min(4.,.8*32767/peak)
    result={'source':'One phrase synthesized by the production HDL voice engine, then processed by integer effect models verified against RTL.',
            'source_sha256':hashlib.sha256(phrase.read_bytes()).hexdigest(),'frames':len(x),'logical_sample_rate':FS,
            'wav_sample_rate':round(FS),'common_audition_gain':gain,'files':{}}
    for name,audio in rendered.items():
        path=output/(name+'.wav')
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(round(FS));f.writeframes(np.rint(audio*gain).astype('<i2').tobytes())
        result['files'][name]=dict(peak=int(np.max(abs(audio))),tail_rms=float(np.sqrt(np.mean(audio[round(4.7*FS):].astype(float)**2))),
                                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (output/'audition.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Common gain',gain)


if __name__=='__main__':main()
