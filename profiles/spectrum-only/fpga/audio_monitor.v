`timescale 1ns/1ps
// One 1024-sample rectangular-window DFT. Fold 64 all-real + imaginary
// dot products onto one multiplier. Each sample has 1024 system clocks of
// budget and needs 128 issued terms plus a short pipeline drain.
module monitor_dft(input wire clk,rst,sample_tick,input wire signed [7:0] sample,
                   output reg [319:0] levels,output reg [5:0] peak_count,
                   output reg complete,output reg overrun);
 reg [9:0] sample_number,phase,step;
 reg [6:0] term;
 reg run,first_sample,last_sample;
 reg signed [7:0] held;
 reg signed [24:0] sums[0:127] /* synthesis syn_ramstyle="distributed_ram" */;
 reg signed [7:0] coef1;
 reg signed [24:0] old1,old2;
 reg signed [15:0] product2;
 reg [6:0] addr1,addr2;
 reg valid1,valid2;
 function signed [7:0] sine(input [6:0] angle);
  reg [5:0] quadrant_index;reg [6:0] magnitude;
  begin
   quadrant_index=angle[5]?6'd32-{1'b0,angle[4:0]}:{1'b0,angle[4:0]};
   case(quadrant_index)
     0:magnitude=7'd0;
     1:magnitude=7'd6;
     2:magnitude=7'd12;
     3:magnitude=7'd19;
     4:magnitude=7'd25;
     5:magnitude=7'd31;
     6:magnitude=7'd37;
     7:magnitude=7'd43;
     8:magnitude=7'd49;
     9:magnitude=7'd54;
     10:magnitude=7'd60;
     11:magnitude=7'd65;
     12:magnitude=7'd71;
     13:magnitude=7'd76;
     14:magnitude=7'd81;
     15:magnitude=7'd85;
     16:magnitude=7'd90;
     17:magnitude=7'd94;
     18:magnitude=7'd98;
     19:magnitude=7'd102;
     20:magnitude=7'd106;
     21:magnitude=7'd109;
     22:magnitude=7'd112;
     23:magnitude=7'd115;
     24:magnitude=7'd117;
     25:magnitude=7'd120;
     26:magnitude=7'd122;
     27:magnitude=7'd123;
     28:magnitude=7'd125;
     29:magnitude=7'd126;
     30:magnitude=7'd126;
     31:magnitude=7'd127;
     32:magnitude=7'd127;
     default:magnitude=0;
   endcase
   sine=angle[6]?-$signed({1'b0,magnitude}):$signed({1'b0,magnitude});
  end
 endfunction
 // Preserve every product bit throughout all 1024 additions. Even 1024
 // repetitions of the worst product (+/-128*127) fit signed 25 bits.
 wire signed [24:0] sum=(first_sample?25'sd0:old2)+$signed({{9{product2[15]}},product2});
 reg signed [24:0] real_sum;
 reg [15:0] mag_real,mag_imag;
 reg mag_valid;reg [5:0] mag_bin;
 reg [16:0] magnitude;
 reg level_valid;reg [5:0] level_bin;
 function [15:0] absolute(input signed [24:0] v);
  reg [24:0] magnitude_value;
  begin magnitude_value=v[24]?-v:v;absolute=magnitude_value[24:9];end
 endfunction
 // A bar increases by about three display steps per amplitude doubling.
 // Floor 16 suppresses the lowest product-quantization noise in the plot.
 function [4:0] log_level(input [16:0] m);
  integer b;begin
   log_level=0;
   for(b=4;b<=13;b=b+1)
    if(m[b])log_level=(b-3)*3+m[b-1]+(m[b-1]&&m[b-2]);
   if(|m[16:14])log_level=31;
  end
 endfunction
 wire [4:0] level=log_level(magnitude);
 reg [319:0] work_levels;
 reg [4:0] preceding,last_level,highest,reference_level;
 reg [5:0] tally;
 // A peak must clear the absolute floor and lie within approximately 18 dB
 // of the previous complete window maximum. Bars retain the lower detail.
 wire [4:0] threshold=reference_level>18?reference_level-5'd9:5'd9;
 wire found_previous=last_level>=threshold && last_level>preceding && last_level>level;
 always @(posedge clk)begin
  valid1<=run;valid2<=valid1;mag_valid<=0;level_valid<=mag_valid;complete<=0;
  if(sample_tick)begin
   if(run || valid1 || valid2)overrun<=1;
   held<=sample;step<=sample_number;phase<=sample_number;term<=0;run<=1;
   first_sample<=sample_number==0;last_sample<=sample_number==1023;
   sample_number<=sample_number+1'b1;
  end
  if(run)begin
   old1<=sums[term];addr1<=term;
   coef1<=sine(phase[9:3]+(term[0]?7'd0:7'd32));
   if(term[0])phase<=phase+step;
   if(term==127)run<=0;else term<=term+1'b1;
  end
  if(valid1)begin product2<=held*coef1;old2<=old1;addr2<=addr1;end
  if(valid2)begin
   sums[addr2]<=sum;
   if(last_sample)begin
    if(!addr2[0])real_sum<=sum;
    else begin mag_real<=absolute(real_sum);mag_imag<=absolute(sum);mag_bin<=addr2[6:1];mag_valid<=1;end
   end
  end
  if(mag_valid)begin
   magnitude<=mag_real>=mag_imag?{1'b0,mag_real}+{2'b0,mag_imag[15:1]}:{1'b0,mag_imag}+{2'b0,mag_real[15:1]};
   level_bin<=mag_bin;
  end
  if(level_valid)begin
   work_levels<={level,work_levels[319:5]};
   if(level_bin==0 || level>highest)highest<=level;
   if(level_bin==0)begin preceding<=0;tally<=0;end
   else begin preceding<=last_level;tally<=tally+found_previous;end
   last_level<=level;
   if(level_bin==63)begin
    levels<={level,work_levels[319:5]};
    peak_count<=tally+found_previous+(level>last_level && level>=threshold);
    reference_level<=level>highest?level:highest;
    complete<=1;
   end
  end
  if(rst)begin
   sample_number<=0;run<=0;valid1<=0;valid2<=0;mag_valid<=0;level_valid<=0;
   complete<=0;overrun<=0;levels<=0;peak_count<=0;reference_level<=0;highest<=0;
  end
 end
endmodule


// Lean build: preserve the original DFT and the externally visible interface.
module audio_monitor(input wire sys_clk,sys_rst,sample_tick,input wire signed [15:0] pcm,
 input wire enable,input wire [1:0] test_state,input wire [4:0] missing_voice,
 input wire [15:0] onset_us,input wire onset_valid,
 input wire pixel_clk,pixel_rst,frame_start,input wire [10:0] x,y,
 output wire [5:0] peak_count,output wire [319:0] spectrum_levels,output wire analysis_overrun,
 output wire [23:0] rgb);
 wire reset_analysis=sys_rst || !enable;
 reg [9:0] position;
 reg [15:0] peak;
 reg [2:0] gain;
 wire [15:0] absolute_pcm=pcm[15]?-pcm:pcm;
 wire [15:0] window_peak=absolute_pcm>peak?absolute_pcm:peak;
 wire signed [21:0] amplified=$signed({{6{pcm[15]}},pcm})<<<gain;
 wire signed [7:0] scaled=amplified>32767?8'sd127:(amplified< -32768?-8'sd128:$signed(amplified[15:8]));
 monitor_dft spectrum(.clk(sys_clk),.rst(reset_analysis),.sample_tick(sample_tick),.sample(scaled),
  .levels(spectrum_levels),.peak_count(peak_count),.overrun(analysis_overrun));
 always @(posedge sys_clk)begin
  if(sample_tick)begin
   position<=position+1'b1;
   if(position==1023)begin
    peak<=0;
    if(window_peak>=16384)gain<=0;else if(window_peak>=8192)gain<=1;
    else if(window_peak>=4096)gain<=2;else if(window_peak>=2048)gain<=3;
    else if(window_peak>=1024)gain<=4;else if(window_peak>=512)gain<=5;else gain<=6;
   end else peak<=window_peak;
  end
  if(reset_analysis)begin position<=0;peak<=0;gain<=4;end
 end
 // Only the 64 small display levels and status cross clock domains. No waveform
 // history, delay line, trajectory histogram or picture BRAM is present.
 wire [349:0] snap;
 display_snapshot #(.WIDTH(350)) cdc(.sys_clk(sys_clk),.sys_rst(sys_rst),.pixel_clk(pixel_clk),.pixel_rst(pixel_rst),
   .frame_start(frame_start),.source({onset_valid,onset_us,test_state,missing_voice,peak_count,spectrum_levels}),.snapshot(snap));
 monitor_lite_renderer renderer(.clk(pixel_clk),.rst(pixel_rst),.x(x),.y(y),.levels(snap[319:0]),
  .peaks(snap[325:320]),.missing(snap[330:326]),.mode(snap[332:331]),.onset_us(snap[348:333]),.onset_valid(snap[349]),.rgb(rgb));
endmodule

module monitor_lite_renderer(input wire clk,rst,input wire [10:0] x,y,input wire [1:0] mode,
 input wire [4:0] missing,input wire [5:0] peaks,input wire [319:0] levels,
 input wire [15:0] onset_us,input wire onset_valid,output reg [23:0] rgb);
 function [63:0] glyph(input [7:0] code);
  begin case(code)
    "0":glyph=64'h000e11131519110e;
    "1":glyph=64'h000e040404040604;
    "2":glyph=64'h001f02040810110e;
    "3":glyph=64'h000f10100e10100f;
    "4":glyph=64'h0008081f090a0c08;
    "5":glyph=64'h000f10100f01011f;
    "6":glyph=64'h000e11110f01010e;
    "7":glyph=64'h000202020408101f;
    "8":glyph=64'h000e11110e11110e;
    "9":glyph=64'h000e10101e11110e;
    "A":glyph=64'h001111111f11110e;
    "B":glyph=64'h000f11110f11110f;
    "C":glyph=64'h001e01010101011e;
    "D":glyph=64'h000f11111111110f;
    "E":glyph=64'h001f01010f01011f;
    "F":glyph=64'h000101010f01011f;
    "G":glyph=64'h001e11111d01011e;
    "H":glyph=64'h001111111f111111;
    "I":glyph=64'h001f04040404041f;
    "J":glyph=64'h000609080808081c;
    "K":glyph=64'h0011090503050911;
    "L":glyph=64'h001f010101010101;
    "M":glyph=64'h0011111115151b11;
    "N":glyph=64'h0011111915151311;
    "O":glyph=64'h000e11111111110e;
    "P":glyph=64'h000101010f11110f;
    "Q":glyph=64'h001609151111110e;
    "R":glyph=64'h001109050f11110f;
    "S":glyph=64'h000f10100e01011e;
    "T":glyph=64'h000404040404041f;
    "U":glyph=64'h000e111111111111;
    "V":glyph=64'h00040a1111111111;
    "W":glyph=64'h000a151515111111;
    "X":glyph=64'h0011110a040a1111;
    "Y":glyph=64'h00040404040a1111;
    "Z":glyph=64'h001f01020408101f;
    "/":glyph=64'h0001010204081010;
    ".":glyph=64'h0004040000000000;
    ":":glyph=64'h0000040400040400;
    "-":glyph=64'h000000001f000000;
    default:glyph=0;
   endcase end
 endfunction
 function [7:0] letter(input [255:0] phrase,input [5:0] length,input [5:0] index);
  begin letter=phrase>>((length-index-1)*8);end
 endfunction
 function [7:0] decimal_2(input [5:0] number,input tens);
  reg [2:0] t;begin
   t=number>=30?3:(number>=20?2:(number>=10?1:0));
   decimal_2="0"+(tens?t:number-(t*10));
  end
 endfunction
 function [3:0] digit_at(input [19:0] bcd,input [2:0] index);
  begin case(index)
   0:digit_at=bcd[19:16];1:digit_at=bcd[15:12];2:digit_at=bcd[11:8];
   3:digit_at=bcd[7:4];default:digit_at=bcd[3:0];
  endcase end
 endfunction
 reg [19:0] bcd_work,bcd_adjust,bcd_value;
 reg [15:0] bcd_shift;
 reg [4:0] bcd_step;
 integer digit;
 always @*begin
  bcd_adjust=bcd_work;
  for(digit=0;digit<5;digit=digit+1)
   if(bcd_work[digit*4+:4]>=5)bcd_adjust[digit*4+:4]=bcd_work[digit*4+:4]+3;
 end
 always @(posedge clk)begin
  if(rst)begin bcd_step<=0;bcd_value<=0;bcd_work<=0;bcd_shift<=0;end
  else if(bcd_step==0)begin bcd_step<=1;bcd_work<=0;bcd_shift<=onset_us;end
  else begin
   bcd_work<={bcd_adjust[18:0],bcd_shift[15]};bcd_shift<={bcd_shift[14:0],1'b0};
   if(bcd_step==16)begin bcd_value<={bcd_adjust[18:0],bcd_shift[15]};bcd_step<=0;end
   else bcd_step<=bcd_step+1'b1;
  end
 end

 function [7:0] static_char(input [11:0] cell_position);
  begin case(cell_position)
    12'h18e, 12'h1ac, 12'h81f, 12'h82f, 12'h83c: static_char=".";
    12'h047, 12'h18a, 12'h8ca, 12'h8cf, 12'h8f8: static_char="/";
    12'h83d: static_char="0";
    12'h81e, 12'h8d2: static_char="1";
    12'h1ae, 12'h82e, 12'h830, 12'h8cd: static_char="2";
    12'h811, 12'h821, 12'h83b, 12'h8cc, 12'h8d1: static_char="3";
    12'h183, 12'h18c, 12'h1aa, 12'h801: static_char="4";
    12'h820, 12'h83e: static_char="5";
    12'h182, 12'h18f, 12'h810: static_char="6";
    12'h18d, 12'h80f: static_char="7";
    12'h190, 12'h1ab, 12'h1ad, 12'h1af, 12'h802: static_char="8";
    12'h831: static_char="9";
    12'h8c3, 12'h8f1: static_char=":";
    12'h043, 12'h8f0: static_char="A";
    12'h185, 12'h8c2: static_char="B";
    12'h04c, 12'h1a7: static_char="C";
    12'h04b, 12'h8c8, 12'h8f6, 12'h8fa: static_char="E";
    12'h045: static_char="G";
    12'h192, 12'h1b2: static_char="H";
    12'h055, 12'h186, 12'h8c6, 12'h8fc: static_char="I";
    12'h1b1, 12'h822, 12'h832, 12'h83f: static_char="K";
    12'h8c5: static_char="L";
    12'h050, 12'h052, 12'h1a8, 12'h8f3: static_char="M";
    12'h044, 12'h054, 12'h187: static_char="N";
    12'h053, 12'h057: static_char="O";
    12'h04a, 12'h1a6: static_char="P";
    12'h04e, 12'h058: static_char="R";
    12'h049, 12'h188: static_char="S";
    12'h042, 12'h04d, 12'h056, 12'h8f5, 12'h8fd: static_char="T";
    12'h04f, 12'h8f4: static_char="U";
    12'h8c7: static_char="V";
    12'h8fb: static_char="X";
    12'h193, 12'h1b3: static_char="Z";
    default:static_char=" ";
   endcase end
 endfunction
 wire test_mode=mode==1 || mode==2;
 wire [5:0] column=x[9:4],row=y[9:4];
 reg [7:0] character;
 always @*begin
  character=static_char({row,column});
  if(row==4)begin
   if(column>=2 && column<18 && mode==1) character=letter("TEST / 32 VOICES",16,column-2);
   if(column>=2 && column<18 && mode==2) character=letter("TEST / 31 VOICES",16,column-2);
   if(column>=2 && column<10 && mode==0) character=letter("LIVE PCM",8,column-2);
   if(column>=2 && column<24 && mode==3) character=letter("LIVE / STOP LOOP FIRST",22,column-2);
   if(!test_mode)begin
    if(column>=37 && column<45)character=letter("LAST I2S",8,column-37);
    if(column>=47 && column<52)character=onset_valid?("0"+digit_at(bcd_value,column-47)):"-";
    if(column>=53 && column<55)character=letter("US",2,column-53);
   end else begin
    if(column>=37 && column<42)character=letter("PEAKS",5,column-37);
    if(column==43 || column==44)character=decimal_2(peaks,column==43);
    if(column>=48 && column<54 && mode==1)character=letter("SELECT",6,column-48);
    if(column>=48 && column<55 && mode==2)character=letter("MISSING",7,column-48);
    if(column==56 || column==57)character=decimal_2({1'b0,missing}+1'b1,column==56);
   end
  end
  if(row==35 && column>=24 && column<36 && test_mode)character=letter("TURN: SELECT",12,column-24);
  if(row==35 && column>=24 && column<34 && !test_mode)character=letter("TURN: EXIT",10,column-24);
 end
 reg [10:0] x1,y1;reg [1:0] mode1;reg [4:0] missing1,height1;
 reg [7:0] char1;reg [5:0] bit1;reg ink2;
 wire [63:0] bitmap=glyph(char1);
 wire [8:0] height_px={height1,3'b000}+{height1,1'b0};
 reg [23:0] shade,shade2;
 always @*begin
  shade=24'h101b27;
  if(y1<48 || y1>=552)shade=24'h0a1520;
  if(y1>=136 && y1<=480)begin
   shade=24'h0e202a;
   if(x1[6:0]==0 || y1==480 || y1==400 || y1==320 || y1==240 || y1==160)shade=24'h2d414b;
   if(height1!=0 && y1<480 && y1+height_px>=480 && x1[3:0]<12)shade=24'h77cee0;
  end
  if((mode1==1 || mode1==2) && !x1[4] && x1[3:0]<12 && y1>=489 && y1<495)
   shade=x1[9:5]==missing1?(mode1==2?24'hf57d68:24'hfffaf0):24'he9ba71;
 end
 always @(posedge clk)begin
  x1<=x;y1<=y;mode1<=mode;missing1<=missing;height1<=levels[column*5+:5];
  char1<=character;bit1<={y[3:1],x[3:1]};
  shade2<=shade;ink2<=bitmap[bit1];rgb<=ink2?24'he6eeed:shade2;
  if(rst)begin char1<=0;ink2<=0;rgb<=0;end
 end
endmodule
