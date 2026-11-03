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

def select_expr(selector, values):
    """Select string addresses; pages share one glyph/geometry path per row."""
    result = str(values[-1])
    for i in reversed(range(len(values)-1)):
        result = f'({selector}=={i}?({values[i]}):{result})'
    return result

def label_expr(value):
    return str(string(value))

def state_expr(selector, values):
    first = choices(values)
    return f'({first}+({selector}))'

def scene():
    # Navigation, preset names and transport state are shared across pages.
    # One dynamic string field per row keeps pixel logic small and deterministic.
    pages=choices(['演奏首页','选择音色','音频效果','循环录制','曲目指引','系统设置'])
    tone=state_expr('timbre',['纯净正弦','风琴','柔和复合','弦乐','敲击钢琴'])
    effect=state_expr('fx',['原声','混响','延时','混响延时','合唱','混响合唱','延时合唱','组合效果'])
    amp=state_expr('muted?0:(ready?1:2)',['已静音','演奏就绪','功放预热'])
    scan=state_expr('mode==3?4:(fault?3:(mode==0?2:(calibrated?0:1)))',['已校准','校准中','扫描未开','ADC故障','MIDI'])
    loop=state_expr('loop_pending?3:(loop_recording?2:(loop_playing?1:0))',['等待录制','循环播放','正在录制','录制准备'])
    guide=state_expr('guide_loading?3:(guide_playing?2:(guide_valid?1:0))',['等待曲目','曲目就绪','跟拍进行','接收曲目'])
    speed=state_expr('guide_speed',['速度 0.50倍','速度 0.75倍','速度 1.00倍','速度 1.25倍'])
    caps=state_expr('loop_duration',['上限 2 秒','上限 4 秒','上限 8 秒'])
    level=state_expr('drum_mode',['琴键音量','鼓组音量'])
    play=state_expr('playing',['开始演奏','停止演奏'])
    record=state_expr('loop_pending?2:(loop_recording?1:0)',['录制一轮','结束录制','取消准备'])
    loop_play=state_expr('loop_playing',['播放循环','停止循环'])
    guide_play=state_expr('guide_playing',['播放指引','暂停指引'])
    toggle_scan=state_expr('mode==3?2:(mode==0?0:1)',['输入 PC','输入 扫描','输入 MIDI'])
    volume_target=state_expr('drum_mode',['音量对象  琴键','音量对象  鼓组'])
    clear=state_expr('ui_confirm',['清空循环','再次点按确认清空'])
    home=label_expr('返回首页')
    menus=[
      [play,*map(label_expr,['音色','效果','循环录制','曲目指引','设置'])],
      [home,*map(label_expr,['敲击钢琴','纯净正弦','风琴','柔和复合','弦乐'])],
      [home,*map(label_expr,['原声','混响','延时','合唱','组合'])],
      [home,record,loop_play,label_expr('撤销末轮'),caps,clear],
      [home,guide_play,label_expr('返回开头'),speed,label_expr('查看曲谱'),label_expr('')],
      [home,toggle_scan,label_expr('松键校准'),volume_target,label_expr('声谱观察'),label_expr('屏幕检测')],
    ]
    text(24,19,'TANG',1,color="24'hf0f4eb")
    text(190,25,(f'{pages}+ui_page',4),color="24'hc6d3d6")
    text(768,25,'输出',color="24'h708b96")
    text(888,25,(amp,4),color="muted?24'h9aaeb6:24'h79d7bd")
    text(24,76,'跟着亮键演奏',color="24'hdce7e5")
    text(260,76,(guide,4),color="guide_loading?24'he9bc79:24'h79d7bd")
    fixed_bcd(480,76,'time_bcd',3,color="24'hdce7e5")
    text(586,76,'/',color="24'h637f8c")
    fixed_bcd(614,76,'duration_bcd',3,color="24'h8ca7b3")
    text(720,76,'秒',color="24'h8ca7b3")
    text(840,76,(speed,10),color="24'h93adb6")
    text(24,99,'下一组',color="24'h708b96")
    text(824,99,'32白键 C2-F6',color="24'h708b96")

    notes=[36+12*(i//7)+(0,2,4,5,7,9,11)[i%7] for i in range(32)]
    labels=[f'{"CDEFGAB"[i%7]}{n//12-1}' for i,n in enumerate(notes)]
    key_base=choices([''.join(labels[:16]),''.join(labels[16:])])
    text(0,240,(str(key_base),2),color="24'h24414b",width=64)
    text(40,283,'新弹 / 延音',color="24'h8fa8b2")
    text(256,283,'下一组预告',color="24'h8fa8b2")
    text(472,283,'实按正确',color="24'h8fa8b2")
    text(680,283,'实按偏离',color="24'h8fa8b2")
    text(864,283,'音轨配色',color="24'h8fa8b2")

    titles=[label_expr(v) for v in ['当前音色','当前音色','当前效果','循环状态','指引状态','琴键状态']]
    values=[tone,tone,effect,loop,guide,scan]
    text(40,340,(select_expr('ui_page',titles),4),color="24'h8ca7b3")
    text(40,372,(select_expr('ui_page',values),6),1,color="ui_confirm?24'heab17e:24'hf0f4eb")
    text(480,340,(level,4),color="24'h8ca7b3")
    digit(480,372,'volume/10',1,color="24'hf0f4eb")
    digit(512,372,'volume%10',1,color="24'hf0f4eb")
    text(554,384,'%',color="24'h79d7bd")
    text(480,415,'声部',color="24'h708b96")
    digit(568,415,'voices/10',color="24'hc6d3d6")
    digit(584,415,'voices%10',color="24'hc6d3d6")

    # The overview remains available while selecting a preset. More detailed
    # context belongs to its own page, not to an ever-growing flat menu.
    text(40,434,'效果',color="24'h708b96",condition='ui_page<2 || ui_page==5')
    text(120,434,(effect,8),color="24'hc6d3d6",condition='ui_page<2 || ui_page==5')
    text(40,463,'琴键',color="24'h708b96",condition='ui_page<3')
    text(120,463,(scan,4),color="fault?24'heca27f:24'h79d7bd",condition='ui_page<3')
    text(304,463,(loop,4),color="loop_recording?24'heca27f:24'h8ca7b3",condition='ui_page<3')
    text(40,434,'实时音色 / 音频效果',color="24'h8ca7b3",condition='ui_page==2')
    text(40,495,'点按 B 切换 · A 静音返回',color="24'h708b96",condition='ui_page==1 || ui_page==2')
    text(40,495,'B 选择功能 · 按转调音量',color="24'h708b96",condition='ui_page==0')

    text(40,430,'时长',color="24'h708b96",condition='ui_page==3')
    fixed_bcd(120,430,'loop_bcd',1,color="24'hc6d3d6",condition='ui_page==3')
    text(184,430,'秒',color="24'h708b96",condition='ui_page==3')
    digit(248,430,'loop_layers',color="24'h79d7bd",condition='ui_page==3')
    text(264,430,'/4轮',color="24'h708b96",condition='ui_page==3')
    text(360,430,(caps,6),color="24'h8ca7b3",condition='ui_page==3')
    text(40,458,'再按录制可提前结束本轮',color="24'h8ca7b3",condition='ui_page==3 && !ui_confirm')
    text(40,458,'清空全部循环？',color="24'heab17e",condition='ui_page==3 && ui_confirm')
    text(40,491,'再次点按 B 确认 · 旋转取消',color="24'heab17e",condition='ui_page==3 && ui_confirm')
    for i in range(12):
        x=40+i*48
        digit(x+12,491,str((i+1)//10),color=f"drum_mode && pressed[{i}]?24'h123d36:24'h718d99",condition='ui_page==3 && !ui_confirm')
        digit(x+28,491,str((i+1)%10),color=f"drum_mode && pressed[{i}]?24'h123d36:24'h718d99",condition='ui_page==3 && !ui_confirm')

    text(40,434,'曲目事件',color="24'h708b96",condition='ui_page==4')
    for i in range(3):digit(184+i*16,434,f'index_bcd[{(2-i)*4} +: 4]',color="24'h79d7bd",condition='ui_page==4')
    text(240,434,'/',color="24'h637f8c",condition='ui_page==4')
    for i in range(3):digit(272+i*16,434,f'count_bcd[{(2-i)*4} +: 4]',color="24'h8ca7b3",condition='ui_page==4')
    text(40,463,'手机传曲后可独立跟拍',color="24'h8ca7b3",condition='ui_page==4')
    text(40,495,'曲谱需先在手机发送',color="notice==3?24'heab17e:24'h708b96",condition='ui_page==4')
    text(40,463,'校准时请松开全部琴键',color="24'h8ca7b3",condition='ui_page==5 && mode!=3')
    text(40,495,'鼓组按键始终可以演奏',color="24'h708b96",condition='ui_page==5 && mode!=3')

    text(680,309,'B 选择 / 点按确认',color="24'h8ca7b3")
    for i in range(6):
        condition='ui_page!=4' if i==5 else None
        expr=select_expr('ui_page',[page[i] for page in menus])
        text(704,333+36*i,(expr,9),1,color="ui_confirm && ui_page==3 && ui_cursor==5?24'hffe0b7:24'he0e9e7",condition=condition)
    text(40,533,'输出',color="24'h708b96",condition='ui_page!=1')
    text(360,533,'校准异常',color="24'heca27f",condition='(fault && mode!=3) || notice==2')
    text(360,533,'请先开启扫描',color="24'heab17e",condition='!fault && notice==1')
    text(360,533,'循环操作受限',color="24'heca27f",condition='notice==4 || (!fault && notice==0 && loop_notice!=0)')
    text(40,533,'滑音',color="24'h8ca7b3",condition='ui_page==1')
    text(120,533,(state_expr('bend_position<4',['+','-']),1),color="24'h8ca7b3",condition='ui_page==1')
    for i in range(3):digit(136+i*16,533,f'(bend_value/{10**(2-i)})%10',color="24'h8ca7b3",condition='ui_page==1')
    text(216,533,'颤音',color="24'h8ca7b3",condition='ui_page==1')
    digit(296,533,'vibrato_depth',color="24'h8ca7b3",condition='ui_page==1')
    digit(312,533,'0',color="24'h8ca7b3",condition='ui_page==1')
    text(40,463,'接收',color="24'h8ca7b3",condition='ui_page==5 && mode==3')
    text(280,463,'事件',color="24'h8ca7b3",condition='ui_page==5 && mode==3')
    text(40,495,'异常',color="midi_errors!=0?24'heab17e:24'h8ca7b3",condition='ui_page==5 && mode==3')
    for i in range(5):
        for x,y,name in [(120,463,'midi_rx_bcd'),(360,463,'midi_event_bcd'),(120,495,'midi_error_bcd')]:
            digit(x+16*i,y,f'{name}[{(4-i)*4} +: 4]',color="24'hc6d3d6",condition='ui_page==5 && mode==3')
    text(280,495,'延音',color="24'h8ca7b3",condition='ui_page==5 && mode==3')
    digit(360,495,'midi_pedal',color="24'h79d7bd",condition='ui_page==5 && mode==3')
    text(24,574,'A 点按静音返回 · 旋转滑音 · 按转颤音',color="24'h708b96")
    text(632,574,'B 旋转选择 · 按转音量',color="24'h8ca7b3")
    return key_base

HEADER='''`timescale 1ns/1ps
// Generated by tools/generate_guide_panel.py. Three-cycle pixel pipeline.
module panel_renderer(input wire clk,rst,input wire [10:0] x,y,input wire hs,vs,de,
 input wire [15:0] midi_bytes,midi_messages,midi_errors,input wire midi_pedal,
 input wire [2:0] ui_page,input wire [3:0] ui_cursor,input wire ui_confirm,
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
 // pixel path. All eight values refresh within 136 pixel clocks.
 reg [2:0] bcd_slot;
 reg [4:0] bcd_step;
 reg [15:0] bcd_binary;
 reg [19:0] bcd_work,bcd_adjust;
 reg [19:0] time_bcd,duration_bcd,count_bcd,index_bcd,loop_bcd,midi_rx_bcd,midi_event_bcd,midi_error_bcd;
 wire [8:0] bend_value=(bend_position<4?4-bend_position:bend_position-4)*50;
 integer digit_index;
 always @* begin
  bcd_adjust=bcd_work;
  for(digit_index=0;digit_index<5;digit_index=digit_index+1)
   if(bcd_work[digit_index*4 +: 4]>=5)bcd_adjust[digit_index*4 +: 4]=bcd_work[digit_index*4 +: 4]+4'd3;
 end
 always @(posedge clk) begin
  if(rst) begin bcd_slot<=0;bcd_step<=0;bcd_binary<=0;bcd_work<=0;time_bcd<=0;duration_bcd<=0;count_bcd<=0;index_bcd<=0;loop_bcd<=0;midi_rx_bcd<=0;midi_event_bcd<=0;midi_error_bcd<=0;end
  else if(bcd_step==0) begin
   bcd_work<=0;bcd_step<=1;
   case(bcd_slot)
    0:bcd_binary<=guide_time_cs;1:bcd_binary<=guide_duration_cs;
    2:bcd_binary<={6'd0,guide_count};3:bcd_binary<={6'd0,guide_index};
    4:bcd_binary<={6'd0,(loop_recording?loop_position_cs:loop_actual_cs)};
    5:bcd_binary<=midi_bytes;6:bcd_binary<=midi_messages;default:bcd_binary<=midi_errors;
   endcase
  end else begin
   bcd_work<={bcd_adjust[18:0],bcd_binary[15]};bcd_binary<={bcd_binary[14:0],1'b0};
   if(bcd_step==16) begin
    case(bcd_slot)
     0:time_bcd<={bcd_adjust[18:0],bcd_binary[15]};1:duration_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     2:count_bcd<={bcd_adjust[18:0],bcd_binary[15]};3:index_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     4:loop_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     5:midi_rx_bcd<={bcd_adjust[18:0],bcd_binary[15]};6:midi_event_bcd<={bcd_adjust[18:0],bcd_binary[15]};
     7:midi_error_bcd<={bcd_adjust[18:0],bcd_binary[15]};
    endcase
    bcd_slot<=bcd_slot+1'b1;bcd_step<=0;
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
  if(y>=128 && y<268 && x[4:0]!=31)begin
   bg=guide_key?(guide_onset[key_index]?target_color:held_color):24'hebf0e7;
   if(y<133 && !guide_key)bg=24'hc5d1ce;
   if(actual_keys[key_index] && (x[4:0]<3 || x[4:0]>27 || y<133 || y>=262))bg=wrong_key?24'he88874:24'h2bbd91;
  end
  // Two clear working areas: current context and one six-row navigation list.
  if(x>=24 && x<640 && y>=324 && y<552)bg=24'h132630;
  if(x>=456 && x<458 && y>=340 && y<438)bg=24'h29414a;
  if(x>=40 && x<624 && y>=449 && y<450)bg=24'h243b45;
  if(ui_page==3 && x>=40 && x<440 && y>=521 && y<525)begin bg=24'h263c48;if(x<40+{loop_progress,2'b00})bg=loop_recording?24'heca27f:24'h79d7bd;end
  if(x>=672 && x<1000 && y>=330 && y<546)begin
   bg=24'h10212b;
   if(x>=680 && x<992 && y>=334+ui_cursor*36 && y<366+ui_cursor*36 && (ui_page!=4 || ui_cursor<5))
    bg=ui_confirm?24'h513d2f:24'h244d50;
   if(x>=680 && x<684 && y>=334+ui_cursor*36 && y<366+ui_cursor*36 && (ui_page!=4 || ui_cursor<5))
    bg=ui_confirm?24'heab17e:24'h79d7bd;
  end
  // A small right-hand marker identifies the applied preset independently of focus.
  if(x>=974 && x<980)begin
   if(ui_page==1 && y>=348+((timbre==4)?1:(timbre+2))*36 && y<354+((timbre==4)?1:(timbre+2))*36)bg=24'h79d7bd;
   if(ui_page==2 && (fx==0 || fx==1 || fx==2 || fx==4 || fx==7) && y>=348+((fx==0)?1:(fx==1?2:(fx==2?3:(fx==4?4:5))))*36 && y<354+((fx==0)?1:(fx==1?2:(fx==2?3:(fx==4?4:5))))*36)bg=24'h79d7bd;
  end
  if(ui_page==4 && y>=510 && y<546 && x>=672 && x<1000)bg=24'h0c1925;
  if(ui_page!=1 && x>=120 && x<312 && y>=536 && y<542)begin bg=24'h2b424d;if(x<120+(peak_width>>1))bg=peak>220?24'hec947c:24'h79d7bd;end
  if(x>=824 && x<872 && y>=28 && y<34)begin bg=24'h2b424d;if(x<824+(peak_width>>3))bg=peak>220?24'hec947c:24'h79d7bd;end
  if(y==62 || y==563)bg=24'h253942;
  if(y>=286 && y<295)begin
   if(x>=24 && x<32)bg=24'h67d8b8;
   if(x>=240 && x<248)bg=24'he9c38a;
   if(x>=456 && x<464)bg=24'h2bbd91;
   if(x>=664 && x<672)bg=24'he88874;
   if(x>=848 && x<856)bg=24'hb7abe6;
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
    STRINGS[:]=[''];FIELDS.clear()
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
    # IDs stay contiguous (digits retain ASCII IDs); at most 204 glyph slots.
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
        x=40+i*48;y=485
        code+=f"  if(ui_page==3 && !ui_confirm && x>={x} && x<{x+44} && y>={y} && y<{y+30})bg=drum_mode && pressed[{i}]?24'h79d7bd:24'h243b47;\n"
    for x,y,width,scale,expr,color,dig,condition in FIELDS:
        if y==240:
            code+=f"  if(y>=240 && y<260)begin enable=1;direct_on=0;addr={key_base}*32+x[9:4];row=y-240;col=x[3:0];fg={color};end\n"
            continue
        cond='' if not condition else '('+condition+') && '
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
    for name,page,cursor,confirm,drum in [('home',0,1,0,0),('tones',1,1,0,0),('effects',2,2,0,0),('loop_confirm',3,5,1,1),('guide',4,1,0,0),('settings',5,2,0,0),('drums',3,1,0,1)]:
        path=(dest/(name+'.ppm')).as_posix()
        tb=f'''`timescale 1ns/1ps
module preview;
reg clk=0,rst=1;always #5 clk=~clk;reg [10:0] x=0,y=0;wire [23:0] rgb;
panel_renderer dut(.clk(clk),.rst(rst),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(1'b1),
 .ui_page(3'd{page}),.ui_cursor(4'd{cursor}),.ui_confirm(1'b{confirm}),
 .bend_position(4'd4),.vibrato_depth(3'd2),.focus(4'd9),.fx(3'd1),.timbre(3'd4),.volume(7'd25),.voices(6'd3),.mode(2'd2),
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
