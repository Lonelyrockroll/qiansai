"""Analytic piano modal parameters. No sampled instrument recordings."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FS=50e6/1024
BASE=[1,.88,.72,.45,.30,.20,.10,.095,.065,.045,.032,.024]
TAU=[1.10,.85,.62,.43,.29,.18]
TAIL=[2.5,2.1,1.75,1.2,.8,.5]
B=[.00025,.00013,.00010,.00018,.0004,.0010]
PHASE=[0,.12,.29,.07,.38,.21,.44,.16,.34,.03,.27,.41,.015,.135,.305,.085]

def make_parameters():
    bands=[]
    for band in range(6):
        weights=BASE+[BASE[n-1]*.22 for n in range(1,5)]
        norm=28000/sum(weights)
        rows=[]
        for index,w in enumerate(weights):
            n=index+1 if index<12 else index-11
            ratio=n*math.sqrt((1+B[band]*n*n)/(1+B[band]))
            if index>=12:
                cents=[1.5,-1.2,1.7,-1.4][index-12]
                ratio*=2**(cents/1200)
            tau=(TAU[band]/(1+.13*(n-1)+.027*(n-1)**2) if index<12
                 else TAIL[band]/(1+.18*(n-1)))
            target=1-math.exp(-1/(FS*tau))
            s1,s2=min(((a,b) for a in range(10,23) for b in range(a,32)),
                      key=lambda v:abs(2**-v[0]+2**-v[1]-target))
            hard=round(w*norm)
            soft=round(hard*(.88*math.exp(-.13*(n-1))))
            rows.append(dict(ratio=round(ratio*65536),soft=soft,hard=hard,
                             shift1=s1,shift2=s2,phase=round(PHASE[index]*4096),
                             harmonic=n,companion=index>=12,tau_s=1/(FS*(2**-s1+2**-s2))))
        bands.append(rows)
    return bands

def generate():
    bands=make_parameters()
    lines=['// Generated analytic modal coefficients; not recorded PCM.',
           'module piano_modal_tables(input wire [2:0] band,input wire [1:0] group,',
           'output wire [73:0] c0,c1,c2,c3);',
           'function [73:0] coeff; input [6:0] address; begin case(address)']
    for band,rows in enumerate(bands):
        for i,r in enumerate(rows):
            v=r['ratio']
            for field,bits in [('soft',16),('hard',16),('shift1',5),('shift2',5),('phase',12)]:
                v=(v<<bits)|r[field]
            lines.append(f"7'd{band*16+i}: coeff=74'h{v:019x};")
    lines += ["default:coeff=74'd0;endcase end endfunction",
              "assign c0=coeff({band,group,2'd0});assign c1=coeff({band,group,2'd1});",
              "assign c2=coeff({band,group,2'd2});assign c3=coeff({band,group,2'd3});endmodule",
              'module piano_sine4(input wire clk,input wire [11:0] a0,a1,a2,a3,',
              'output reg signed [15:0] y0,y1,y2,y3);',
              'reg signed [15:0] lut[0:4095];initial begin']
    for i in range(4096):
        sample=round(32767*math.sin(2*math.pi*i/4096))
        lines.append(f"lut[{i}]=16'h{sample&65535:04x};")
    lines += ['end','always @(posedge clk) begin y0<=lut[a0];y1<=lut[a1];y2<=lut[a2];y3<=lut[a3];end','endmodule']
    (ROOT/'rtl/piano_modal_tables.v').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'sim/piano_modal_parameters.json').write_text(json.dumps(bands,indent=2),encoding='utf-8')
    print('Generated 6 registers x 16 analytic modes and a 4096-point sine lookup.')

if __name__=='__main__':generate()
