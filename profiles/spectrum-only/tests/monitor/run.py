"""Exercise and render the real DFT/HDMI Lite observer without a board."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CASES=[[],[(16,2100)],[(5,3500),(23,2100)],[(k,105) for k in range(1,64,2)],
       [(k,105) for k in range(1,64,2) if k!=19],[]]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--status-only',action='store_true')
    args=parser.parse_args()
    results=HERE/'results';results.mkdir(exist_ok=True)
    (ROOT/'.work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='spectrum-',dir=ROOT/'.work') as folder:
        work=Path(folder)
        sources=[ROOT/'fpga/audio_monitor.v',ROOT.parents[1]/'fpga/display_snapshot.v',HERE/'tb_monitor.v']
        digest={}
        for path in sources:
            data=path.read_bytes();(work/path.name).write_bytes(data)
            digest[path.name]=hashlib.sha256(data).hexdigest()
        with (work/'stimulus.hex').open('w',newline='\n') as file:
            for tones in CASES:
                raw=[round(sum(amplitude*math.sin(2*math.pi*k*n/1024) for k,amplitude in tones)) for n in range(1024)]
                for sample in raw*2:file.write(f'{sample&65535:04x}\n')
        iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
        vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
        subprocess.run([iv,'-g2012','-s','tb_monitor','-o','test.vvp',*[f.name for f in sources]],cwd=work,check=True)
        cmd=[vvp,'test.vvp']
        for flag,on in [('+NATIVE',args.native),('+RENDER',args.render),('+STATUS_ONLY',args.status_only)]:
            if on:cmd.append(flag)
        proc=subprocess.run(cmd,cwd=work,capture_output=True,text=True,timeout=480,check=True)
        if 'PASS' not in proc.stdout:raise RuntimeError(proc.stdout+proc.stderr)
        outcome={'result':'passed','source_sha256':digest,'scope':'Actual Lite DFT/renderer RTL simulation; no board claim.',
                 'sample_period_sys_clocks':1024 if args.native else 160,'status_only':args.status_only,'frames':[]}
        if not args.status_only:
            for line in (work/'frames.txt').read_text().splitlines():
                tag,peaks,bits=line.split();k=int(tag);p=int(peaks)
                heights=[(int(bits,16)>>(5*i))&31 for i in range(64)]
                assert p==len(CASES[k]),(k,p)
                if CASES[k]:
                    ranked=sorted(range(1,65),key=lambda j:heights[j-1],reverse=True)
                    assert set(ranked[:p])=={j for j,_ in CASES[k]},(k,heights)
                else:assert max(heights)==0
                outcome['frames'].append({'case':k,'peaks':p,'levels':heights})
        if args.render:
            from PIL import Image
            hashes={}
            for name in (['loop-header'] if args.status_only else ['tone','test32','test31']):
                with Image.open(work/(name+'.ppm')) as source:
                    image=source.convert('RGB')
                assert image.size==((1024,112) if args.status_only else (1024,600))
                golden=results/(name+'.png')
                if golden.is_file():
                    with Image.open(golden) as expected:assert image.tobytes()==expected.convert('RGB').tobytes(),name
                else:image.save(golden)
                hashes[name]=hashlib.sha256(image.tobytes()).hexdigest()
            outcome['rgb_sha256']=hashes
        filename='status-validation.json' if args.status_only else 'validation.json'
        (results/filename).write_text(json.dumps(outcome,indent=2)+'\n')
        print(proc.stdout.strip())
        if outcome['frames']:print([f['peaks'] for f in outcome['frames']])

if __name__=='__main__':main()
