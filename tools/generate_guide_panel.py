"""Generate the framebuffer-free 1024x600 guide UI and optional RTL previews."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FPGA = ROOT / 'fpga'
STRINGS = ['']
FIELDS = []

def string(value):
    if value not in STRINGS:
        STRINGS.append(value)
    return STRINGS.index(value)

def choices(values):
    first = len(STRINGS)
    STRINGS.extend(values)
    return first

def text(x, y, value, scale=0, color="24'hdce7eb", width=None, condition=None):
    expr = str(string(value)) if isinstance(value, str) else value[0]
    width = width or (len(value) if isinstance(value, str) else value[1])
    FIELDS.append((x,y,width,scale,expr,color,None,condition))

def digit(x, y, value, scale=0, color="24'hdce7eb", condition=None):
    FIELDS.append((x,y,1,scale,'0',color,value,condition))

def fixed_bcd(x,y,name,integer_digits=3,scale=0,color="24'hdce7eb",condition=None):
    for i in range(integer_digits):
        nibble=integer_digits+1-i
        digit(x+i*(16<<scale),y,f'{name}[{nibble*4} +: 4]',scale,color,condition)
    text(x+integer_digits*(16<<scale),y,'.',scale,color,condition=condition)
    digit(x+(integer_digits+1)*(16<<scale),y,f'{name}[7:4]',scale,color,condition)
    digit(x+(integer_digits+2)*(16<<scale),y,f'{name}[3:0]',scale,color,condition)

def menu_item(index, label, condition=None):
    col=index//6;row=index%6
    x=512+col*240;y=338+row*32
    digit(x+8,y,str((index+1)//10),color="24'h6e8f98",condition=condition)
    digit(x+24,y,str((index+1)%10),color="24'h6e8f98",condition=condition)
    text(x+48,y,label,color="24'hf1f5f3",condition=condition)

def scene():
    text(24,18,'TANG',1,color="24'hf0f6f2")
    text(176,28,'白键合奏 / 曲目指引',color="24'h8ca7b3")
    text(176,50,'琴键检测异常，请检查校准',color="24'heca27f",condition='fault || notice!=0')
    text(176,50,'循环操作受限，请检查录制状态',color="24'heca27f",condition='!fault && notice==0 && loop_notice!=0')
    play_labels=choices(['已静音','演奏就绪','功放预热'])
    text(856,23,(f'{play_labels}+(muted?0:(ready?1:2))',4),color="24'h79d7bd")
    source=choices(['手机曲目','内置练习'])
    text(856,50,(f'{source}+guide_demo',4),color="24'h8ca7b3")
    text(24,72,'跟着亮键演奏',color="24'hf0f6f2")
    states=choices(['等待曲目','曲目就绪','跟拍进行','接收曲目'])
    text(272,72,(f'{states}+(guide_loading?3:(guide_playing?2:(guide_valid?1:0)))',4),color="guide_loading?24'he9bc79:24'h79d7bd")
    fixed_bcd(632,72,'time_bcd',3,color="24'hf0f6f2")
    text(736,72,'/',color="24'h637f8c")
    fixed_bcd(760,72,'duration_bcd',3,color="24'h8ca7b3")
    text(864,72,'秒',color="24'h8ca7b3")
    speed=choices(['0.50倍','0.75倍','1.00倍','1.25倍'])
    text(912,72,(f'{speed}+guide_speed',5),color="24'h79d7bd")
    text(24,99,'下一组',color="24'h93adb6")
    text(824,99,'32白键 C2—F6',color="24'h93adb6")

    # One glyph address per letter/octave; no division by a non-power-of-two key width.
    notes=[36+12*(i//7)+(0,2,4,5,7,9,11)[i%7] for i in range(32)]
    labels=[f'{"CDEFGAB"[i%7]}{n//12-1}' for i,n in enumerate(notes)]
    key_base=choices([''.join(labels[:16]),''.join(labels[16:])])
    text(0,240,(str(key_base),2),color="24'h24414b",width=64)

    text(40,283,'新弹 / 延音',color="24'h96afb7")
    text(248,283,'下一组预告',color="24'h96afb7")
    text(460,283,'实按正确',color="24'h96afb7")
    text(640,283,'实按偏离',color="24'h96afb7")
    text(844,283,'按音轨配色',color="24'h96afb7")

    modes=choices(['电脑琴键','单键检测','32键扫描'])
    text(40,328,(f'{modes}+mode',6),color="24'h8ca7b3")
    text(40,354,'当前音色',color="24'h8ca7b3")
    tones=choices(['纯净正弦','风琴音色','柔和复合','弦乐锯齿','敲击钢琴'])
    text(40,378,(f'{tones}+timbre',4),1,color="24'hf0f6f2")
    level_labels=choices(['琴键音量','鼓组音量'])
    text(256,354,(f'{level_labels}+drum_mode',4),color="24'h8ca7b3")
    digit(256,380,'volume/10',1,color="24'hf0f6f2")
    digit(288,380,'volume%10',1,color="24'hf0f6f2")
    text(326,395,'%',color="24'h79d7bd")
    text(376,354,'声部',color="24'h8ca7b3")
    digit(376,387,'voices/10',color="24'hf0f6f2")
    digit(392,387,'voices%10',color="24'hf0f6f2")

    text(40,435,'LOOP',color="24'h8ca7b3",condition='!drum_mode')
    fixed_bcd(128,435,'loop_bcd',1,color="24'hdce7eb",condition='!drum_mode')
    text(192,435,'秒',color="24'h8ca7b3",condition='!drum_mode')
    digit(240,435,'loop_layers',color="24'h79d7bd",condition='!drum_mode')
    text(256,435,'/4轮',color="24'h8ca7b3",condition='!drum_mode')
    caps=choices(['上限2秒','上限4秒','上限8秒'])
    text(352,435,(f'{caps}+loop_duration',5),color="24'h8ca7b3",condition='!drum_mode')
    loop_state=choices(['等待录制','循环播放','正在录制','录制准备'])
    text(272,99,(f'{loop_state}+(loop_pending?3:(loop_recording?2:(loop_playing?1:0)))',4),color="loop_recording?24'heca27f:24'h8ca7b3")
    fixed_bcd(352,99,'loop_bcd',1,color="24'hdce7eb")
    text(420,99,'秒',color="24'h8ca7b3")
    digit(464,99,'loop_layers',color="24'h79d7bd")
    text(480,99,'/4轮',color="24'h8ca7b3")
    text(576,99,(f'{caps}+loop_duration',5),color="24'h8ca7b3")
    text(40,463,(f'{loop_state}+(loop_pending?3:(loop_recording?2:(loop_playing?1:0)))',4),color="loop_recording?24'heca27f:24'h8ca7b3",condition='!drum_mode')
    text(208,463,'指引事件',color="24'h8ca7b3",condition='!drum_mode')
    for i in range(3):digit(272+i*16,463,f'index_bcd[{(2-i)*4} +: 4]',color="24'h79d7bd",condition='!drum_mode')
    text(320,463,'/',color="24'h637f8c",condition='!drum_mode')
    for i in range(3):digit(336+i*16,463,f'count_bcd[{(2-i)*4} +: 4]',color="24'h8ca7b3",condition='!drum_mode')
    text(40,501,'输出',color="24'h8ca7b3",condition='!drum_mode')
    alerts=choices(['已校准','校准中','扫描未开','ADC故障'])
    text(336,501,(f'{alerts}+(fault?3:(mode==0?2:(calibrated?0:1)))',4),color="fault?24'heca27f:24'h79d7bd",condition='!drum_mode')
    # The drum page uses its compact 12-pad status strip; the guide keyboard stays visible.
    for i,name in enumerate(['底鼓','军鼓','拍手','闭镲','开镲','低通','中通','高通','吊镲','叮镲','边击','牛铃']):
        x=40+(i%4)*104;y=435+(i//4)*29
        text(x+8,y,f'{i+1:02} {name}',color=f"pressed[{i}]?24'h133c3a:24'h95acb5",condition='drum_mode')

    text(512,309,'B 选择 · 点按执行',color="24'h8ca7b3")
    p=choices(['开始演奏','停止演奏']);menu_item(0,(f'{p}+playing',4))
    p=choices(['录制一轮','结束录制','取消准备']);menu_item(1,(f'{p}+(loop_pending?2:(loop_recording?1:0))',4))
    p=choices(['切换音色','撤销末轮']);menu_item(2,(f'{p}+drum_mode',4))
    p=choices(['开启扫描','关闭扫描']);menu_item(3,(f'{p}+(mode!=0)',4),condition='!drum_mode')
    q=choices(['播放循环','停止循环']);menu_item(3,(f'{q}+loop_playing',4),condition='drum_mode')
    menu_item(4,'松键校准',condition='!drum_mode');menu_item(4,(f'{caps}+loop_duration',5),condition='drum_mode')
    menu_item(5,(f'{q}+loop_playing',4),condition='!drum_mode');menu_item(5,'清空循环',condition='drum_mode')
    menu_item(6,'全部静音')
    p=choices(['鼓组页面','琴键页面']);menu_item(7,(f'{p}+drum_mode',4))
    fx=choices(['效果 原声','效果 混响','效果 延迟','效果 混响延迟','效果 合唱','效果 混响合唱','效果 延迟合唱','效果 全开']);menu_item(8,(f'{fx}+fx',8))
    p=choices(['播放指引','暂停指引']);menu_item(9,(f'{p}+guide_playing',4))
    menu_item(10,'指引下一组');menu_item(11,'指引重来')
    text(24,550,'A 转滑音 · 按转颤音 · 点静音',color="24'h8ca7b3")
    text(512,550,'B 转选项 · 按转音量 · 点执行',color="24'h8ca7b3")
    bend=choices([f'滑音 {i*50:+d} 音分' if i else '滑音 0 音分' for i in range(-4,5)])
    depth=choices([f'颤音 {i*10} 音分' for i in range(6)])
    text(24,576,(f'{bend}+bend_position',11),color="timbre==4?24'h657e87:24'h79d7bd")
    text(248,576,(f'{depth}+vibrato_depth',10),color="timbre==4?24'h657e87:24'h79d7bd")
    p=choices(['现场表情','钢琴原音']);text(456,576,(f'{p}+(timbre==4)',4),color="24'h8ca7b3")
    text(720,576,'手机传曲 · 板卡跟拍',color="24'h8ca7b3")
    return key_base

HEADER='''`timescale 1ns/1ps
// Generated by tools/generate_guide_panel.py. Three-cycle pixel pipeline.
module panel_renderer(input wire clk,rst,input wire [10:0] x,y,input wire hs,vs,de,
 input wire [3:0] bend_position,focus,input wire [2:0] vibrato_depth,fx,timbre,input wire [6:0] volume,input wire [5:0] voices,
 input wire [1:0] mode,input wire calibrated,fault,muted,ready,playing,pattern,
 input wire [9:0] loop_actual_cs,loop_position_cs,input wire [2:0] loop_layers,loop_notice,input wire [1:0] loop_duration,
 input wire loop_playing,loop_recording,loop_pending,input wire [6:0] loop_progress,
 input wire drum_mode,input wire [3:0] notice,input wire [31:0] pressed,input wire [7:0] peak,
 input wire guide_valid,guide_playing,guide_loading,guide_demo,
 input wire [15:0] guide_time_cs,guide_duration_cs,input wire [9:0] guide_count,guide_index,input wire [1:0] guide_speed,
 input wire [31:0] guide_target,guide_onset,guide_next,actual_keys,input wire [63:0] guide_colors,
 output reg [23:0] rgb,output reg hs_out,vs_out,de_out);
 reg [7:0] strings[0:4095];
 // Exactly three 1024x16 synchronous font banks. Row 16 is blank for every
 // glyph, so storing only rows 1..15 saves one physical BSRAM block.
 reg [15:0] font0[0:1023],font1[0:1023],font2[0:1023];
 initial begin
  $readmemh("compact_ui_strings.hex",strings);
  $readmemh("compact_ui_font0.hex",font0);
  $readmemh("compact_ui_font1.hex",font1);
  $readmemh("compact_ui_font2.hex",font2);
 end

 // Round-robin binary-to-BCD conversion decouples decimal formatting from the
 // pixel path. All five values refresh within 85 pixel clocks.
 reg [2:0] bcd_slot;
 reg [4:0] bcd_step;
 reg [15:0] bcd_binary;
 reg [19:0] bcd_work,bcd_adjust;
 reg [19:0] time_bcd,duration_bcd,count_bcd,index_bcd,loop_bcd;
 integer digit_index;
 always @* begin
  bcd_adjust=bcd_work;
  for(digit_index=0;digit_index<5;digit_index=digit_index+1)
   if(bcd_work[digit_index*4 +: 4]>=5)bcd_adjust[digit_index*4 +: 4]=bcd_work[digit_index*4 +: 4]+4'd3;
 end
 always @(posedge clk) begin
  if(rst) begin bcd_slot<=0;bcd_step<=0;bcd_binary<=0;bcd_work<=0;time_bcd<=0;duration_bcd<=0;count_bcd<=0;index_bcd<=0;loop_bcd<=0;end
  else if(bcd_step==0) begin
   bcd_work<=0;bcd_step<=1;
   case(bcd_slot)
    0:bcd_binary<=guide_time_cs;1:bcd_binary<=guide_duration_cs;
    2:bcd_binary<={6'd0,guide_count};3:bcd_binary<={6'd0,guide_index};
    default:bcd_binary<={6'd0,(loop_recording?loop_position_cs:loop_actual_cs)};
   endcase
  end else begin
   bcd_work<={bcd_adjust[18:0],bcd_binary[15]};bcd_binary<={bcd_binary[14:0],1'b0};
   if(bcd_step==16) begin
    case(bcd_slot)
     0:time_bcd<={bcd_adjust[18:0],bcd_binary[15]};1:duration_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     2:count_bcd<={bcd_adjust[18:0],bcd_binary[15]};3:index_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     default:loop_bcd<={bcd_adjust[18:0],bcd_binary[15]};
    endcase
    bcd_slot<=bcd_slot==4?0:bcd_slot+1'b1;bcd_step<=0;
   end else bcd_step<=bcd_step+1'b1;
  end
 end
 wire [4:0] key_index=x[9:5];
 reg [23:0] target_color,held_color;
 always @* begin
  case(guide_colors[{key_index,1'b0} +: 2])
   0:begin target_color=24'h67d8b8;held_color=24'hb8ddd1;end
   1:begin target_color=24'hebb376;held_color=24'he5d4bb;end
   2:begin target_color=24'hb7abe6;held_color=24'hd6d1e8;end
   default:begin target_color=24'h78b9dc;held_color=24'hcbdfe8;end
  endcase
 end
 reg [23:0] bg,fg;reg [11:0] addr;reg [4:0] row;reg [3:0] col;
 reg enable,direct_on;reg [7:0] direct;
 wire guide_key=guide_valid && guide_target[key_index];
 wire wrong_key=guide_valid && guide_target!=0 && !guide_target[key_index];
 wire [8:0] peak_width={peak,1'b0}-(peak>>1);
 always @* begin
  bg=24'h0c1925;fg=24'hdce7eb;addr=0;row=0;col=0;enable=0;direct_on=0;direct=0;
  if(y<62)bg=24'h101f2e;
  if(y>=114 && y<274)bg=24'h354957;
  if(y>=118 && y<124 && x[4:0]!=31)bg=guide_valid && guide_next[key_index]?24'he9c38a:24'h263c48;
  if(x>=680 && x<780 && y>=105 && y<111)begin bg=24'h263c48;if(x<680+loop_progress)bg=loop_recording?24'heca27f:24'h79d7bd;end
  if(y>=128 && y<268 && x[4:0]!=31)begin
   bg=guide_key?(guide_onset[key_index]?target_color:held_color):24'hebf0e7;
   if(y<133 && !guide_key)bg=24'hc5d1ce;
   if(actual_keys[key_index] && (x[4:0]<3 || x[4:0]>27 || y<133 || y>=262))bg=wrong_key?24'he88874:24'h2bbd91;
  end
  if(y>=314 && y<536 && x>=24 && x<480)bg=24'h142936;
  if(y>=328 && y<526 && x>=512 && x<992)begin
   bg=24'h132633;
   if((x<744 && focus<6 && y>=332+{focus,5'b0} && y<360+{focus,5'b0}) ||
      (x>=752 && x<984 && focus>=6 && focus<12 && y>=332+{(focus-4'd6),5'b0} && y<360+{(focus-4'd6),5'b0}))bg=24'h28495a;
   if((x>=512 && x<516 && focus<6 && y>=332+{focus,5'b0} && y<360+{focus,5'b0}) ||
      (x>=752 && x<756 && focus>=6 && focus<12 && y>=332+{(focus-4'd6),5'b0} && y<360+{(focus-4'd6),5'b0}))bg=24'h79d7bd;
  end
  if(!drum_mode && x>=120 && x<312 && y>=502 && y<512)begin bg=24'h2b424d;if(x<120+(peak_width>>1))bg=peak>220?24'hec947c:24'h79d7bd;end
  if(x>=720 && x<816 && y>=32 && y<38)begin bg=24'h2b424d;if(x<720+(peak_width>>2))bg=peak>220?24'hec947c:24'h79d7bd;end
  if(y>=286 && y<296)begin
   if(x>=24 && x<32)bg=24'h67d8b8;
   if(x>=232 && x<240)bg=24'he9c38a;
   if(x>=444 && x<452)bg=24'h2bbd91;
   if(x>=624 && x<632)bg=24'he88874;
   if(x>=824 && x<832)bg=24'hb7abe6;
  end
'''
FOOTER='''  if(pattern) begin
   enable=0;
   case(x[9:7])
    0:bg=24'hffffff;1:bg=24'hffff00;2:bg=24'h00ffff;3:bg=24'h00ff00;
    4:bg=24'hff00ff;5:bg=24'hff0000;6:bg=24'h0000ff;7:bg=24'h101820;
   endcase
   if(x<4 || x>=1020 || y<4 || y>=596 || x==511 || x==512 || y==299 || y==300)bg=24'hffffff;
  end
 end
 reg [7:0] glyph1,direct1;reg direct_on1;
 reg [4:0] row1;reg [3:0] col1,col2;
 reg [15:0] bits0_2,bits1_2,bits2_2;reg [1:0] font_bank2;
 reg enable1,enable2;reg [23:0] bg1,bg2,fg1,fg2;
 reg hs1,vs1,de1,hs2,vs2,de2;
 wire [7:0] font_glyph=direct_on1?direct1:glyph1;
 wire [11:0] font_addr={font_glyph,4'b0}-{4'b0,font_glyph}+{7'd0,row1}-12'd1;
 wire [15:0] bits2=font_bank2==0?bits0_2:(font_bank2==1?bits1_2:(font_bank2==2?bits2_2:16'd0));
 always @(posedge clk) begin
  glyph1<=strings[addr];direct1<=direct;direct_on1<=direct_on;
  row1<=row;col1<=col;enable1<=enable;bg1<=bg;fg1<=fg;
  bits0_2<=font0[font_addr[9:0]];bits1_2<=font1[font_addr[9:0]];bits2_2<=font2[font_addr[9:0]];font_bank2<=font_addr[11:10];
  col2<=col1;enable2<=enable1 && row1!=0 && row1<=15;bg2<=bg1;fg2<=fg1;
  rgb<=enable2 && bits2[15-col2]?fg2:bg2;
  hs1<=hs;vs1<=vs;de1<=de;hs2<=hs1;vs2<=vs1;de2<=de1;
  hs_out<=hs2;vs_out<=vs2;de_out<=de2;
  if(rst)begin rgb<=0;de_out<=0;enable1<=0;enable2<=0;de1<=0;de2<=0;end
 end
endmodule
'''

def generate():
    key_base=scene()
    assert len(STRINGS)<=128,(len(STRINGS),STRINGS)
    chars=sorted(set('0123456789'+''.join(STRINGS)))
    assert len(chars)<=256,len(chars)
    ids={str(i):48+i for i in range(10)}
    free=iter(sorted(set(range(256))-set(ids.values())))
    for ch in chars:
        if ch not in ids:ids[ch]=next(free)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
    rows=[0]*4096
    for ch,idx in ids.items():
        im=Image.new('1',(16,32));d=ImageDraw.Draw(im)
        box=d.textbbox((0,0),ch,font=font)
        if ch=='.':
            d.rectangle((7,13,8,14),fill=1)
        else:
            d.text(((16-box[2]+box[0])//2-box[0],1-box[1]),ch,font=font,fill=1)
        for y in range(32):
            bits=sum(int(bool(im.getpixel((x,y))))<<(15-x) for x in range(16))
            if 1<=y<=16:rows[idx*16+y%16]=bits
            else:assert bits==0,(ch,y)
    # Preserve legacy row values exactly, but omit the universally blank row16.
    # IDs are contiguous here (digits retain ASCII IDs), and 198*15=2970 words.
    glyph_slots=max(ids.values())+1
    assert glyph_slots*15<=3072,(glyph_slots,len(chars))
    assert all(rows[glyph*16]==0 for glyph in range(256)), 'Nonblank row16 cannot be omitted'
    packed_rows=[rows[glyph*16+row] for glyph in range(glyph_slots) for row in range(1,16)]
    packed_rows.extend([0]*(3072-len(packed_rows)))
    for glyph in range(glyph_slots):
        for row in range(1,16):assert packed_rows[glyph*15+row-1]==rows[glyph*16+row]
    words=[0]*4096
    for i,s in enumerate(STRINGS):
        assert len(s)<=32,s
        for j,ch in enumerate(s):words[i*32+j]=ids[ch]
    # Unused string cells must render blank rather than the first assigned glyph.
    blank=ids[' ']
    for i,s in enumerate(STRINGS):
        for j in range(len(s),32):words[i*32+j]=blank
    for i in range(len(STRINGS)*32,len(words)):words[i]=blank
    code=HEADER
    for i in range(12):
        x=40+(i%4)*104;y=432+(i//4)*29
        code+=f"  if(drum_mode && x>={x} && x<{x+96} && y>={y} && y<{y+26})bg=pressed[{i}]?24'h79d7bd:24'h243b47;\n"
    for x,y,width,scale,expr,color,dig,condition in FIELDS:
        if y==240:
            code+=f"  if(y>=240 && y<260)begin enable=1;direct_on=0;addr={key_base}*32+x[9:4];row=y-240;col=x[3:0];fg={color};end\n"
            continue
        cond='' if not condition else condition+' && '
        code+=f"  if({cond}x>={x} && x<{x+width*(16<<scale)} && y>={y} && y<{y+(20<<scale)})begin enable=1;direct_on=0;addr=({expr})*32+((x-{x})>>{4+scale});row=(y-{y})>>{scale};col=(x-{x})>>{scale};fg={color};\n"
        if dig is not None:code+=f"   direct_on=1;direct=8'd48+({dig});\n"
        code+='  end\n'
    code+=FOOTER
    (FPGA/'panel_renderer.v').write_text(code,encoding='utf8')
    (FPGA/'compact_ui_font.hex').write_text(''.join(f'{v:04x}\n' for v in rows),encoding='ascii')
    for bank in range(3):
        (FPGA/f'compact_ui_font{bank}.hex').write_text(''.join(f'{v:04x}\n' for v in packed_rows[bank*1024:(bank+1)*1024]),encoding='ascii')
    (FPGA/'compact_ui_strings.hex').write_text(''.join(f'{v:02x}\n' for v in words),encoding='ascii')
    (FPGA/'font_packing.json').write_text(json.dumps(dict(glyphs_used=len(chars),strings_used=len(STRINGS),font_words=3072,font_banks=3,font_bank_words=1024,font_rows_per_glyph=15,font_used_words=glyph_slots*15,string_bytes=4096,
        key_pitch_labels=[f'{"CDEFGAB"[i%7]}{2+i//7}' for i in range(32)],generator='tools/generate_guide_panel.py'),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Generated',len(STRINGS),'strings,',len(chars),'glyphs,',len(FIELDS),'text fields')

def preview(dest):
    dest.mkdir(parents=True,exist_ok=True)
    iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe';vv=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    for drum in (0,1):
        name='guide' if not drum else 'drums'
        path=(dest/(name+'.ppm')).as_posix()
        tb=f'''`timescale 1ns/1ps
module preview;
reg clk=0,rst=1;always #5 clk=~clk;reg [10:0] x=0,y=0;wire [23:0] rgb;
panel_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
 .bend_position(4'd4),.vibrato_depth(3'd2),.focus(4'd9),.fx(3'd1),.timbre(3'd4),.volume(7'd7),.voices(6'd3),.mode(2'd2),
 .calibrated(1'b1),.fault(1'b0),.muted(1'b0),.ready(1'b1),.playing(1'b1),.pattern(1'b0),
 .loop_actual_cs(10'd600),.loop_position_cs(10'd123),.loop_layers(3'd2),.loop_notice(3'd0),.loop_duration(2'd2),
 .loop_playing(1'b1),.loop_recording(1'b0),.loop_pending(1'b0),.loop_progress(7'd20),.drum_mode(1'd{drum}),
 .notice(4'd0),.pressed(32'h{('00000211' if drum else '00054000')}),.peak(8'd100),
 .guide_valid(1'b1),.guide_playing(1'b1),.guide_loading(1'b0),.guide_demo(1'b0),
 .guide_time_cs(16'd1234),.guide_duration_cs(16'd4820),.guide_count(10'd126),.guide_index(10'd34),.guide_speed(2'd2),
 .guide_target(32'h00054000),.guide_onset(32'h00044000),.guide_next(32'h001a0000),.guide_colors(64'h0000001000000000),
 .actual_keys(32'h0004c000),.rgb(rgb));
integer i,file;
initial begin file=$fopen("{path}","wb");if(!file)$fatal;
 $fwrite(file,"P6\\n1024 600\\n255\\n");repeat(4)@(negedge clk);rst=0;
 for(i=0;i<1024*600+2;i=i+1)begin x=i%1024;y=i/1024;@(negedge clk);if(i>=2)$fwrite(file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);end
 $fclose(file);$finish;end
endmodule
'''
        with tempfile.TemporaryDirectory(prefix='guide-panel-') as work:
            p=Path(work);(p/'preview.v').write_text(tb)
            subprocess.run([iv,'-g2012','-s','preview','-o',str(p/'preview.vvp'),str(p/'preview.v'),str(FPGA/'panel_renderer.v')],check=True,cwd=FPGA)
            subprocess.run([vv,str(p/'preview.vvp')],check=True,cwd=FPGA,timeout=120)
        with Image.open(dest/(name+'.ppm')) as im:im.save(dest/(name+'.png'))
        print(dest/(name+'.png'))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--preview-dir',type=Path)
    args=ap.parse_args();generate()
    if args.preview_dir:preview(args.preview_dir.resolve())
