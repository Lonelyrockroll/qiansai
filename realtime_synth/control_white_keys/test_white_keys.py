"""Check all 32 ADC notes, note-off, polyphony, actual HDMI colours, labels, and host mapping."""
from pathlib import Path
import json,math,subprocess,sys
from PIL import Image
R=Path(__file__).resolve().parent;S=R/'sim';S.mkdir(exist_ok=True)
sys.path.insert(0,str(R.parent/'host'))
from protocol import WHITE_KEYS,FS
# Independent oracle: pick natural pitch classes over the requested inclusive instrument range.
midi=[n for n in range(36,90) if n%12 not in (1,3,6,8,10)]
assert len(midi)==32 and list(WHITE_KEYS)==midi
steps=[round(440*2**((n-69)/12)*2**32/FS) for n in midi]
(S/'reference_steps.hex').write_text('\n'.join(f'{v:08x}' for v in steps)+'\n')
def run(top,files):
    image=S/(top+'.vvp')
    subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-s',top,'-o',image,*files],cwd=R,check=True)
    result=subprocess.run(['E:/iverilog/bin/vvp.exe',image],cwd=R,text=True,capture_output=True,timeout=120)
    print(result.stdout+result.stderr,flush=True);result.check_returncode()
run('tb_white_keys',['tb_white_keys.v','keyboard_input.v','white_key_map.v','../rtl/note_rom.v','panel_renderer.v'])
run('tb_panel_preview',['tb_panel_preview.v','panel_renderer.v'])
preview=Image.open(S/'white_keys.ppm').convert('RGB')
assert preview.size==(1024,600)
for k in range(32):
    assert preview.getpixel((64+16*k+6,410))==((85,223,189) if k in (14,16,18) else (233,237,242))
# Check actual glyph pixels against ASCII font ROM, independently of string-slot addresses.
font=[int(n,16) for n in (R/'ui_font.hex').read_text().split()]
def check_label(x,y,char,fg,bg):
    for row in range(18):
        bits=font[ord(char)*32+row]
        for col in range(15):
            expect=fg if bits&(1<<(15-col)) else bg
            assert preview.getpixel((x+col,y+row))==expect,(x,y,char,row,col)
for k in range(32):
    bg=(85,223,189) if k in (14,16,18) else (233,237,242)
    check_label(64+16*k,470,'CDEFGAB'[k%7],(25,51,58),bg)
for k in (0,7,14,21,28,31):
    text=('CDEFGAB'[k%7]+str(midi[k]//12-1))
    for j,c in enumerate(text):check_label(64+16*k+16*j,504,c,(233,237,242),(23,39,55))
preview.save(R/'hdmi_white_keys.png')
rows=[dict(key=k+1,index=k,note='CDEFGAB'[k%7]+str(n//12-1),midi=n,hz=round(440*2**((n-69)/12),4),dds=steps[k]) for k,n in enumerate(midi)]
(R/'keyboard_validation.json').write_text(json.dumps(dict(result='passed',keys=rows,hdmi_chord=['C4','E4','G4']),indent=2)+'\n')
print('PASS all 32 pitches and rendered letter pixels; octave and endpoint labels match the physical indices')
