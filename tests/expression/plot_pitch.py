"""Plot the frequency of the rendered RTL sine from its rising zero crossings."""
from pathlib import Path
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from verify import FS, crossing_hz

out=Path(__file__).resolve().parent/'results'
with wave.open(str(out/'sine_C4.wav')) as f:
    pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)
t,hz=crossing_hz(pcm,500,len(pcm)-256)
cents=1200*np.log2(hz/261.6255653)
canvas=Image.new('RGB',(1060,365),'#f5f8f6')
draw=ImageDraw.Draw(canvas)
fonts={s:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',s) for s in (15,18,25)}
def label(x,y,text,size=15,color='#1e383a',anchor='la'):
    draw.text((x,y),text,font=fonts[size],fill=color,anchor=anchor)
left,right,top,bottom=80,1010,82,275
def x(v):return left+v/1.9*(right-left)
def y(v):return bottom-(v+65)/285*(bottom-top)
label(28,13,'按住同一个 C4 · 旋钮如何改变音高',25)
label(30,53,'纵轴为音分，100 音分等于一个半音。曲线从实际 RTL 输出的正弦音频计算。')
for v in (-50,0,50,100,150,200):
    draw.line((left,y(v),right,y(v)),fill='#92a5a6' if not v else '#d3dede')
    label(left-9,y(v),str(v),15,anchor='rm')
for v in (0,.25,.5,.75,1,1.25,1.5,1.75):
    label(x(v),285,f'{v:g}',anchor='mt')
label(1008,285,'秒',anchor='rt')
points=[(x(a),y(b)) for a,b in zip(t,cents)]
draw.line(points,fill='#0c7568',width=3)
label(80,324,'A 快转四格，上滑 200 音分',18)
label(457,324,'回到 C4 后，按转 A 加入颤音，约 ±50 音分',18)
canvas.save(out/'pitch_trace.png')
