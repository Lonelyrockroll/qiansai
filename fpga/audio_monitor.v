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

module audio_monitor(input wire sys_clk,sys_rst,sample_tick,input wire signed [15:0] pcm,
 input wire enable,input wire [1:0] test_state,input wire [4:0] missing_voice,
 input wire [15:0] onset_us,input wire onset_valid,
 input wire pixel_clk,pixel_rst,frame_start,input wire [10:0] x,y,
 output wire [5:0] peak_count,output wire [319:0] spectrum_levels,output wire analysis_overrun,
 output wire [23:0] rgb);
 wire analysis_reset=sys_rst || !enable;
 reg [9:0] position;
 reg [15:0] peak;
 reg [2:0] gain;
 wire [15:0] absolute_pcm=pcm[15]? -pcm:pcm;
 wire [15:0] window_peak=absolute_pcm>peak?absolute_pcm:peak;
 wire signed [21:0] amplified=$signed({{6{pcm[15]}},pcm})<<<gain;
 wire signed [7:0] scaled=amplified>32767?8'sd127:(amplified< -32768?-8'sd128:$signed(amplified[15:8]));
 wire [5:0] point=scaled[7:2]^6'h20;
 reg [383:0] wave_work;
 // Delay *raw* samples, then apply the same current gain to X and Y:
 // changing display gain at a window boundary does not bend the phase plot.
 reg signed [15:0] delay_pipe[0:15];
 wire signed [21:0] delayed_amplified=$signed({{6{delay_pipe[15][15]}},delay_pipe[15]})<<<gain;
 wire signed [7:0] delayed_scaled=delayed_amplified>32767?8'sd127:(delayed_amplified< -32768?-8'sd128:$signed(delayed_amplified[15:8]));
 wire [3:0] x_bin=point[5:2];
 wire [3:0] y_bin=~(delayed_scaled[7:4]^4'h8);
 reg [4:0] delay_fill;
 reg [255:0] phase_work;
 wire complete;
 monitor_dft spectrum(.clk(sys_clk),.rst(analysis_reset),.sample_tick(sample_tick),.sample(scaled),
   .levels(spectrum_levels),.peak_count(peak_count),.complete(complete),.overrun(analysis_overrun));
 integer d;
 always @(posedge sys_clk)begin
  if(sample_tick)begin
   delay_pipe[0]<=pcm;for(d=1;d<16;d=d+1)delay_pipe[d]<=delay_pipe[d-1];
   if(delay_fill!=16)delay_fill<=delay_fill+1'b1;
   position<=position+1'b1;
   if(position[2:0]==0)wave_work<={point,wave_work[383:6]};
   if(position==1023)begin
    peak<=0;
    if(window_peak>=16384)gain<=0;else if(window_peak>=8192)gain<=1;
    else if(window_peak>=4096)gain<=2;else if(window_peak>=2048)gain<=3;
    else if(window_peak>=1024)gain<=4;else if(window_peak>=512)gain<=5;else gain<=6;
   end else peak<=window_peak;
   if(delay_fill==16)phase_work[{y_bin,x_bin}]<=1;
  end
  // At this point the last sample is complete, and the next is >800 clocks away.
  if(complete)phase_work<=0;
  if(analysis_reset)begin
   position<=0;peak<=0;gain<=4;delay_fill<=0;phase_work<=0;
   wave_work<={64{6'd32}};
  end
 end
 // One 512x16 dual-clock display RAM. The inactive bank receives a complete
 // window, then a one-bit bank token crosses clock domains. The producer
 // waits for the displayed bank ACK before reusing the previous bank.
 localparam IDLE=0,WAVE=1,BARS=2,PHASE=3;
 reg [1:0] writer;
 reg [5:0] index;reg write_bank,published_bank,display_bank,frame_valid;
 reg [1:0] ack_sync,pub_sync;
 reg [383:0] wave_shift;reg [319:0] level_shift;reg [255:0] phase_shift;
 reg [5:0] previous_sample;
 reg [29:0] metadata0,metadata1,metadata_pixel;
 wire [7:0] write_offset=writer==WAVE?{2'b00,index}:
                          writer==BARS?{2'b01,index}:{4'b1000,index[3:0]};
 wire [15:0] write_data=writer==WAVE?{4'd0,(index==0?wave_shift[5:0]:previous_sample),wave_shift[5:0]}:
                        writer==BARS?{11'd0,level_shift[4:0]}:phase_shift[15:0];
 reg [15:0] display_ram[0:511];
 wire [7:0] read_offset;reg [15:0] pixel_word;
 always @(posedge sys_clk)if(writer!=IDLE && !analysis_reset)
    display_ram[{write_bank,write_offset}]<=write_data;
 always @(posedge pixel_clk)pixel_word<=display_ram[{display_bank,read_offset}];
 always @(posedge sys_clk)begin
   ack_sync<={ack_sync[0],display_bank};
   if(sys_rst)begin
    writer<=IDLE;index<=0;published_bank<=0;metadata0<=0;metadata1<=0;
   end else if(!enable)begin
    // Abandon incomplete writes but retain the last published token and bank.
    writer<=IDLE;index<=0;
   end else case(writer)
    IDLE:if(complete && ack_sync[1]==published_bank)begin
      write_bank<=!published_bank;index<=0;writer<=WAVE;
      wave_shift<=wave_work;level_shift<=spectrum_levels;phase_shift<=phase_work;
      if(published_bank)metadata0<={onset_valid,onset_us,test_state,missing_voice,peak_count};
      else metadata1<={onset_valid,onset_us,test_state,missing_voice,peak_count};
    end
    WAVE:begin
      previous_sample<=wave_shift[5:0];wave_shift<=wave_shift>>6;index<=index+1'b1;
      if(index==63)begin index<=0;writer<=BARS;end
    end
    BARS:begin
      level_shift<=level_shift>>5;index<=index+1'b1;
      if(index==63)begin index<=0;writer<=PHASE;end
    end
    PHASE:begin
      phase_shift<=phase_shift>>16;index<=index+1'b1;
      if(index==15)begin writer<=IDLE;published_bank<=write_bank;end
    end
   endcase
 end
 always @(posedge pixel_clk)begin
  pub_sync<={pub_sync[0],published_bank};
  if(pixel_rst)begin
   pub_sync<=0;display_bank<=0;frame_valid<=0;metadata_pixel<=0;
  end else if(frame_start && pub_sync[1]!=display_bank)begin
   display_bank<=pub_sync[1];frame_valid<=1;
   metadata_pixel<=pub_sync[1]?metadata1:metadata0;
  end
 end
 monitor_renderer renderer(.clk(pixel_clk),.rst(pixel_rst),.x(x),.y(y),
   .onset_valid(metadata_pixel[29]),.onset_us(metadata_pixel[28:13]),
   .mode(metadata_pixel[12:11]),.missing(metadata_pixel[10:6]),.peaks(metadata_pixel[5:0]),
   .frame_valid(frame_valid),.pixel_word(pixel_word),.read_offset(read_offset),.rgb(rgb));
endmodule

module monitor_renderer(input wire clk,rst,input wire [10:0] x,y,input wire [1:0] mode,
 input wire [4:0] missing,input wire [5:0] peaks,input wire [15:0] onset_us,input wire onset_valid,
 input wire frame_valid,input wire [15:0] pixel_word,output wire [7:0] read_offset,
 output reg [23:0] rgb);
 // Constant 5x7 uppercase glyphs. Spacing is included in each 8x8 cell.
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
 wire test_label=mode==1 || mode==2;
 reg [7:0] character;reg [2:0] font_x,font_y;
 always @*begin
   character=" ";font_x=0;font_y=0;
   if(x>=24 && x<440 && y>=15 && y<47)begin
    character=letter("AUDIO MONITOR",13,(x-24)>>5);font_x=(x-24)>>2;font_y=(y-15)>>2;
   end
   if(mode==0 && x>=560 && x<688 && y>=10 && y<26)begin
    character=letter("LIVE PCM",8,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-10)>>1;
   end
   if(mode==3 && x>=560 && x<912 && y>=10 && y<26)begin
    character=letter("LIVE / STOP LOOP FIRST",22,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-10)>>1;
   end
   if(mode==1 && x>=560 && x<816 && y>=10 && y<26)begin
    character=letter("TEST / 32 VOICES",16,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-10)>>1;
   end
   if(mode==2 && x>=560 && x<816 && y>=10 && y<26)begin
    character=letter("TEST / 31 VOICES",16,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-10)>>1;
   end
   if(!test_label && x>=560 && x<704 && y>=38 && y<54)begin
    character=letter("LAST I2S ",9,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-38)>>1;
   end
   if(!test_label && x>=720 && x<800 && y>=38 && y<54)begin
    character=onset_valid?("0"+digit_at(bcd_value,(x-720)>>4)):"-";font_x=(x-720)>>1;font_y=(y-38)>>1;
   end
   if(!test_label && x>=816 && x<848 && y>=38 && y<54)begin
    character=letter("US",2,(x-816)>>4);font_x=(x-816)>>1;font_y=(y-38)>>1;
   end
   if(test_label && x>=560 && x<640 && y>=38 && y<54)begin
    character=letter("PEAKS",5,(x-560)>>4);font_x=(x-560)>>1;font_y=(y-38)>>1;
   end
   if(test_label && x>=656 && x<688 && y>=38 && y<54)begin
    character=decimal_2(peaks,x<672);font_x=(x-656)>>1;font_y=(y-38)>>1;
   end
   if(mode==1 && x>=768 && x<864 && y>=38 && y<54)begin
    character=letter("SELECT",6,(x-768)>>4);font_x=(x-768)>>1;font_y=(y-38)>>1;
   end
   if(mode==2 && x>=768 && x<880 && y>=38 && y<54)begin
    character=letter("MISSING",7,(x-768)>>4);font_x=(x-768)>>1;font_y=(y-38)>>1;
   end
   if(test_label && x>=896 && x<928 && y>=38 && y<54)begin
    character=decimal_2({1'b0,missing}+6'd1,x<912);font_x=(x-896)>>1;font_y=(y-38)>>1;
   end
   if(x>=32 && x<240 && y>=79 && y<95)begin
    character=letter("01 / WAVEFORM",13,(x-32)>>4);font_x=(x-32)>>1;font_y=(y-79)>>1;
   end
   if(x>=496 && x<624 && y>=79 && y<95)begin
    character=letter("10.49 MS",8,(x-496)>>4);font_x=(x-496)>>1;font_y=(y-79)>>1;
   end
   if(x>=712 && x<856 && y>=79 && y<95)begin
    character=letter("AUTO GAIN",9,(x-712)>>4);font_x=(x-712)>>1;font_y=(y-79)>>1;
   end
   if(x>=32 && x<240 && y>=265 && y<281)begin
    character=letter("02 / SPECTRUM",13,(x-32)>>4);font_x=(x-32)>>1;font_y=(y-265)>>1;
   end
   if(x>=32 && x<320 && y>=293 && y<309)begin
    character=letter("64 BINS / 47.68 HZ",18,(x-32)>>4);font_x=(x-32)>>1;font_y=(y-293)>>1;
   end
   if(x>=32 && x<256 && y>=315 && y<331)begin
    character=letter("PCM 48.828 KHZ",14,(x-32)>>4);font_x=(x-32)>>1;font_y=(y-315)>>1;
   end
   if(x>=650 && x<858 && y>=265 && y<281)begin
    character=letter("03 / XY 16X16",13,(x-650)>>4);font_x=(x-650)>>1;font_y=(y-265)>>1;
   end
   if(x>=646 && x<966 && y>=542 && y<558)begin
    character=letter("Y DELAY 16 / 0.33 MS",20,(x-646)>>4);font_x=(x-646)>>1;font_y=(y-542)>>1;
   end
   if(x>=26 && x<58 && y>=520 && y<536)begin
    character=letter("48",2,(x-26)>>4);font_x=(x-26)>>1;font_y=(y-520)>>1;
   end
   if(x>=141 && x<189 && y>=520 && y<536)begin
    character=letter("763",3,(x-141)>>4);font_x=(x-141)>>1;font_y=(y-520)>>1;
   end
   if(x>=245 && x<325 && y>=520 && y<536)begin
    character=letter("1.53K",5,(x-245)>>4);font_x=(x-245)>>1;font_y=(y-520)>>1;
   end
   if(x>=374 && x<454 && y>=520 && y<536)begin
    character=letter("2.29K",5,(x-374)>>4);font_x=(x-374)>>1;font_y=(y-520)>>1;
   end
   if(x>=485 && x<565 && y>=520 && y<536)begin
    character=letter("3.05K",5,(x-485)>>4);font_x=(x-485)>>1;font_y=(y-520)>>1;
   end
   if(x>=24 && x<296 && y>=573 && y<589)begin
    character=letter("B: LIVE / 32 / 31",17,(x-24)>>4);font_x=(x-24)>>1;font_y=(y-573)>>1;
   end
   if(!test_label && x>=350 && x<510 && y>=573 && y<589)begin
    character=letter("TURN: EXIT",10,(x-350)>>4);font_x=(x-350)>>1;font_y=(y-573)>>1;
   end
   if(test_label && x>=350 && x<542 && y>=573 && y<589)begin
    character=letter("TURN: SELECT",12,(x-350)>>4);font_x=(x-350)>>1;font_y=(y-573)>>1;
   end
   if(x>=712 && x<936 && y>=573 && y<589)begin
    character=letter("A: MUTE / EXIT",14,(x-712)>>4);font_x=(x-712)>>1;font_y=(y-573)>>1;
   end
 end
 reg [7:0] char1;reg [5:0] font_bit1;reg ink2;
 wire [63:0] bitmap=glyph(char1);
 reg [10:0] x1,y1;reg [1:0] mode1;reg [4:0] missing1;
 wire [5:0] wave_column=x[9:4];
 wire [5:0] bar_column=(x-32)>>3;
 wire [3:0] phase_row=(y-286)>>4;
 wire [3:0] phase_column=(x-704)>>4;
 wire phase_area=x>=704 && x<960 && y>=286 && y<542;
 wire spectrum_area=x>=32 && x<544 && y>=341 && y<=501;
 assign read_offset=phase_area?{4'b1000,phase_row}:
                    spectrum_area?{2'b01,bar_column}:{2'b00,wave_column};
 wire [5:0] current1=frame_valid?pixel_word[5:0]:6'd32;
 wire [5:0] previous1=frame_valid?pixel_word[11:6]:6'd32;
 wire [4:0] height1=frame_valid?pixel_word[4:0]:5'd0;
 reg [5:0] bar_column1;reg [3:0] phase_column1;
 wire [8:0] wave_y=9'd239-{current1,1'b0};
 wire [8:0] prev_y=9'd239-{previous1,1'b0};
 wire [7:0] height_px={height1,2'b00}+height1;
 reg [23:0] shade,shade2;
 always @*begin
  shade=24'h101b27;
  if(y1<66)shade=24'h0a1520;
  if(y1>=70 && y1<249)shade=24'h142b34;
  if(y1>=109 && y1<245)begin
   if(x1[6:0]==0 || y1==177)shade=24'h33515a;
   if(y1==wave_y || y1==wave_y+1 ||
     (x1[3:0]<2 && ((y1>=wave_y && y1<=prev_y) || (y1>=prev_y && y1<=wave_y))))shade=24'h76e5c0;
  end
  if(x1>=16 && x1<608 && y1>=255 && y1<554)shade=24'h162632;
  if(x1>=624 && x1<1008 && y1>=255 && y1<554)shade=24'h162632;
  if(x1>=32 && x1<544 && y1>=341 && y1<=501)begin
   shade=24'h0e202a;
   if(x1[6:0]==32 || y1==500 || y1==452 || y1==404 || y1==356)shade=24'h2d414b;
   if(height1!=0 && y1<500 && y1+height_px>=500 && x1[2:0]<6)shade=24'h77cee0;
  end
  if((mode1==1 || mode1==2) && x1>=32 && x1<544 && x1[2:0]<6 && !bar_column1[0] && y1>=506 && y1<511)
   shade=(bar_column1[5:1]==missing1)?(mode1==2?24'hf57d68:24'hfffaf0):24'he9ba71;
  if(x1>=704 && x1<960 && y1>=286 && y1<542)begin
   shade=24'h0e202a;
   if(x1==832 || y1==414)shade=24'h507079;
   else if(x1[5:0]==0 || ((y1-286)&63)==0)shade=24'h293e47;
   if(frame_valid && pixel_word[phase_column1])shade=24'hd3b2fa;
  end
  if(y1>=564)shade=24'h0a1520;
 end
 always @(posedge clk)begin
  // Stage one selects samples/rows; stage two selects a cell and composes
  // plots. RGB is registered in stage three, aligned with the panel syncs.
  x1<=x;y1<=y;mode1<=mode;missing1<=missing;
  char1<=character;font_bit1<={font_y,font_x};
  bar_column1<=bar_column;phase_column1<=phase_column;
  ink2<=bitmap[font_bit1];shade2<=shade;
  rgb<=ink2?24'he6eeed:shade2;
  if(rst)begin char1<=0;ink2<=0;rgb<=0;end
 end
endmodule
