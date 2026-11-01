`timescale 1ns/1ps
module tb_score;
 reg clk=0,pixel_clk=0,rst=1,rx_valid=0,probe=0,score_probe=0,visible=0,fake_busy=0,recorder_active=0;
 reg [7:0] rx_data=0;
 always #10 clk=~clk;
 always #7 pixel_clk=~pixel_clk;
 wire tx_valid;wire[7:0]tx_data;reg tx_ready=1;integer cycle=0;
 always @(negedge clk)begin cycle=cycle+1;tx_ready=(cycle%5)!=0;end
 wire valid,show_requested,loading,reserved,write_enable,ui_ready;
 wire[14:0]write_address;wire[15:0]write_data,page_index,page_count;
 wire[31:0]received_compressed,decoded;
 reg ui_valid=0;reg[1:0]ui_action=0;
 reg cap_cv=0,cap_arm=0,cap_tick=0;reg[15:0]cap_length=8;
 wire cap_busy,cap_ready;wire[15:0]cap_count,cap_q;wire[31:0]cap_crc;
 reg[14:0]cap_address=0,pixel_address=0;wire[15:0]pixel_q;
 wire[7:0]cap_flags;
 wire compat_ready;wire[15:0]compat_q,compat_count;wire[31:0]compat_crc;
 // All new score pins intentionally omitted: default parameter keeps old
 // capture-only instances fully functional instead of propagating Z inputs.
 pcm_capture #(.DEPTH(16)) legacy_capture(.clk(clk),.rst(rst),.sample_tick(cap_tick),.pcm(16'h2468),
  .command_valid(cap_cv),.command_arm(cap_arm),.trigger_nonzero(1'b0),.requested_length(cap_length),.requested_delay(32'd0),
  .read_address(cap_address),.read_data(compat_q),.ready(compat_ready),.count(compat_count),.checksum(compat_crc));
 guide_transport #(.RX_TIMEOUT_CYCLES(300),.UPLOAD_TIMEOUT_CYCLES(200000)) dut(
  .clk(clk),.rst(rst),.audio_tick(1'b0),.probe(probe),.score_probe(score_probe),
  .rx_valid(rx_valid),.rx_data(rx_data),.tx_ready(tx_ready),.tx_valid(tx_valid),.tx_data(tx_data),
  .recorder_active(recorder_active),.ui_valid(1'b0),.ui_action(4'd0),
  .score_video_visible(visible),.capture_busy(cap_busy||fake_busy||(cap_cv&&cap_arm)),.capture_ready(cap_ready),
  .score_ui_valid(ui_valid),.score_ui_action(ui_action),.score_ui_ready(ui_ready),
  .score_write_enable(write_enable),.score_write_address(write_address),.score_write_data(write_data),
  .score_valid(valid),.score_show_requested(show_requested),.score_loading(loading),.score_reserved(reserved),
  .score_received_compressed(received_compressed),.score_decoded_bytes(decoded),
  .score_page_index(page_index),.score_page_count(page_count));
 pcm_capture #(.SCORE_SHARED(1)) capture(.clk(clk),.rst(rst),.sample_tick(cap_tick),.pcm(16'h2468),
  .command_valid(cap_cv),.command_arm(cap_arm),.trigger_nonzero(1'b0),.requested_length(cap_length),.requested_delay(32'd0),
  .read_address(cap_address),.read_data(cap_q),.busy(cap_busy),.ready(cap_ready),.flags(cap_flags),.count(cap_count),.checksum(cap_crc),
  .score_reserved(reserved),.score_write_enable(write_enable),.score_write_address(write_address),.score_write_data(write_data),
  .pixel_clk(pixel_clk),.pixel_read_address(pixel_address),.pixel_read_data(pixel_q));
 reg[7:0] wirebytes[0:23659],raw[0:65535],packet[0:27],ack[0:23],previous[0:23];
 integer ack_count=0,total_acks=0,write_count=0,ack_file,k,p,n,limit,seq=100;
 reg[8*240-1:0] ack_path;
 always @(posedge clk)begin
  if(tx_valid)begin
   if(ack_count>=24)$fatal(1,"unexpected extra response");
   ack[ack_count]=tx_data;ack_count=ack_count+1;
   $fdisplay(ack_file,"%02x",tx_data);
  end
  if(write_enable)begin
   write_count=write_count+1;
   if(visible || !reserved || cap_busy || cap_ready)$fatal(1,"unsafe shared RAM write");
  end
 end
 function[15:0]crc16(input[15:0]acc,input[7:0]value);
  reg[15:0]q;integer i;begin q=acc^{value,8'd0};for(i=0;i<8;i=i+1)q=(q<<1)^(q[15]?16'h1021:16'd0);crc16=q;end
 endfunction
 function[31:0]crc32(input[31:0]acc,input[7:0]value);
  reg[31:0]q;integer i;begin q=acc^{24'd0,value};for(i=0;i<8;i=i+1)q=(q>>1)^(q[0]?32'hedb88320:32'd0);crc32=q;end
 endfunction
 task send_packet(input integer expected_status,input integer expected_magic);
  reg[15:0]check;integer j,t;
  begin
   ack_count=0;
   for(j=0;j<28;j=j+1)begin
    @(negedge clk);rx_valid=1;rx_data=packet[j];@(negedge clk);rx_valid=0;
   end
   t=0;while(ack_count<24 && t<210000)begin @(negedge clk);t=t+1;end
   if(ack_count!=24)$fatal(1,"no ACK op=%d",packet[4]);
   if(ack[0]!="T"||ack[1]!=expected_magic||ack[2]!="A"||ack[3]!="K"||ack[4]!=1||ack[5]!=packet[3]||ack[6]!=packet[4]||ack[7]!=expected_status)
    $fatal(1,"ACK op%d seq%d status%d wanted%d magic%d",packet[4],packet[3],ack[7],expected_status,ack[1]);
   check=16'hffff;for(j=4;j<22;j=j+1)check=crc16(check,ack[j]);
   if(check!={ack[23],ack[22]})$fatal(1,"ACK CRC");
   total_acks=total_acks+1;repeat(3)@(negedge clk);
  end
 endtask
 task make_packet(input[7:0]op,input[7:0]len,input[159:0]payload);
  reg[15:0]check;integer j;
  begin
   seq=(seq+1)&255;for(j=0;j<28;j=j+1)packet[j]=0;
   packet[0]=8'ha5;packet[1]=8'h47;packet[2]=1;packet[3]=seq;packet[4]=op;packet[5]=len;
   for(j=0;j<20;j=j+1)packet[j+6]=payload[j*8+:8];
   check=16'hffff;for(j=2;j<26;j=j+1)check=crc16(check,packet[j]);packet[26]=check[7:0];packet[27]=check[15:8];
  end
 endtask
 task command(input[7:0]op,input[7:0]len,input[159:0]payload,input[7:0]status);
  begin make_packet(op,len,payload);send_packet(status,"P");end
 endtask
 task begin_page(input[31:0]size,input[31:0]sum,input[7:0]status);
  begin command(17,16,{32'd0,16'd512,16'd1024,16'd2,16'd1,sum,size},status);end
 endtask
 task pair_data(input[23:0]offset,input[7:0]cnt,input[127:0]data,input[7:0]status);
  begin command(18,4+cnt,{data,cnt,offset},status);end
 endtask
 task cap_command(input arm);
  begin @(negedge clk);cap_cv=1;cap_arm=arm;@(negedge clk);cap_cv=0;end
 endtask
 task ui(input[1:0]action);
  begin wait(ui_ready);@(negedge clk);ui_action=action;ui_valid=1;@(negedge clk);ui_valid=0;repeat(5)@(negedge clk);end
 endtask
 task assert_duplicate;
  integer j,before_write;begin
   for(j=0;j<24;j=j+1)previous[j]=ack[j];before_write=write_count;
   send_packet(0,"P");
   for(j=0;j<24;j=j+1)if(previous[j]!==ack[j])$fatal(1,"duplicate ACK changed byte%d",j);
   if(write_count!=before_write)$fatal(1,"duplicate DATA rewrote memory");
  end
 endtask
 task capability(input score_kind);
  reg[15:0]check;integer j;begin
   ack_count=0;@(negedge clk);probe=!score_kind;score_probe=score_kind;
   @(negedge clk);probe=0;score_probe=0;wait(ack_count==24);@(negedge clk);
   if(ack[0]!="T"||ack[1]!=(score_kind?"P":"G")||ack[5]!=0||ack[6]!=(score_kind?16:0)||ack[7]!=0)$fatal(1,"capability magic/op");
   check=16'hffff;for(j=4;j<22;j=j+1)check=crc16(check,ack[j]);
   if(check!={ack[23],ack[22]})$fatal(1,"capability CRC");total_acks=total_acks+1;
   repeat(4)@(negedge clk);
  end
 endtask
 reg[31:0]sum;integer before_write,before_acks;
 initial begin
  $readmemh("score-upload.hex",wirebytes);$readmemh("score-raw.hex",raw);
  if(!$value$plusargs("ACK=%s",ack_path))ack_path="score-acks.hex";
  ack_file=$fopen(ack_path,"w");if(!ack_file)$fatal;
  repeat(10)@(negedge clk);rst=0;
  // Actual Java protocol, including sequence 255 -> 0 multiple times.
  for(p=0;p<845;p=p+1)begin
   for(k=0;k<28;k=k+1)packet[k]=wirebytes[p*28+k];
   send_packet(0,"P");
   if(p==0 || p==150 || p==843)assert_duplicate();
   if(p<843 && (valid||show_requested))$fatal(1,"partial image became visible");
  end
  if(!valid||!show_requested||loading||!reserved||decoded!=65536||received_compressed!=13464||page_index!=0||page_count!=2)
   $fatal(1,"Java final state pg=%d/%d raw=%d compressed=%d",page_index,page_count,decoded,received_compressed);
  visible=1;
  // Every bitmap word, both asynchronous pixel RAM and sysclk PC readback.
  for(k=0;k<32768;k=k+1)begin
   @(negedge pixel_clk);pixel_address=k;@(posedge pixel_clk);#1;
   if(pixel_q!=={raw[k*2],raw[k*2+1]})$fatal(1,"pixel byte ordering/address %d",k);
   @(negedge clk);cap_address=k;@(posedge clk);#1;
   if(cap_q!=={raw[k*2],raw[k*2+1]})$fatal(1,"sys readback %d",k);
  end
  before_write=write_count;
  // Invalid headers and capture BUSY preserve an existing visible image.
  command(17,16,{32'd0,16'd512,16'd1023,16'd2,16'd1,32'd0,32'd2},3);
  begin_page(131073,0,3);
  fake_busy=1;begin_page(2,0,4);fake_busy=0;
  if(!valid||!show_requested||!reserved||write_count!=before_write)$fatal(1,"rejected begin destroyed old page");
  // Guide remains a separate TGAK transaction namespace.
  make_packet(0,0,0);send_packet(0,"G");
  make_packet(16,0,0);packet[26]=packet[26]^1;send_packet(1,"P");
  packet[26]=packet[26]^1;send_packet(0,"P");
  // Accepted BEGIN revokes old image but waits until frame-boundary hide ACK.
  fork
   begin begin_page(2,0,0);end
   begin repeat(80)@(negedge clk);if(!reserved||show_requested||valid||!loading||write_count!=before_write)$fatal(1,"BEGIN hide ordering");repeat(100)@(negedge clk);visible=0;end
  join
  cap_command(1);if(cap_busy)$fatal(1,"capture armed into reserved score RAM");
  @(negedge clk);ui_action=2;ui_valid=1;@(negedge clk);ui_valid=0;repeat(3)@(negedge clk);
  if(!loading||!reserved)$fatal(1,"UI cleared an active upload");
  // A complete packet can end after an RLE count; next packet supplies value.
  pair_data(0,1,128'd3,0);
  assert_duplicate();
  if(decoded!=0||received_compressed!=1)$fatal(1,"split RLE count");
  pair_data(0,1,128'h55,5); // Wrong offset must not consume bytes.
  pair_data(1,1,128'h5a,0);
  if(decoded!=3||received_compressed!=2)$fatal(1,"split RLE value");
  command(19,0,0,5);if(valid||show_requested||reserved)$fatal(1,"short page committed");
  begin_page(2,0,0);pair_data(0,2,128'h1100,3);if(reserved)$fatal(1,"zero run retained reservation");
  begin_page(1,0,0);pair_data(0,2,128'h2201,5);command(19,0,0,5);
  // Upload a full constant page with a wrong raw CRC, then a correct page.
  for(n=0;n<3;n=n+1)begin
   sum=32'hffffffff;for(k=0;k<65536;k=k+1)sum=crc32(sum,8'ha6);
   begin_page(n==1?518:516,(~sum)^(n==0?1:0),0);
   for(k=0;k<257;k=k+1)pair_data(k*2,2,128'ha6ff,0);
   pair_data(514,2,128'ha601,0);
   if(decoded!=65536)$fatal(1,"full RLE count");
   if(n==1)begin
    pair_data(516,2,128'ha601,3);
    if(valid||reserved||show_requested)$fatal(1,"overflow page retained");
    command(19,0,0,5);
   end else command(19,0,0,n==0?1:0);
   if(n==0 && (valid||reserved||show_requested))$fatal(1,"bad raw CRC published");
  end
  if(!valid||!show_requested)$fatal(1,"good CRC rejected");
  visible=1;ui(0);if(show_requested||!valid||!reserved)$fatal(1,"local hide cleared cache");visible=0;
  ui(1);if(!show_requested)$fatal(1,"local show failed");visible=1;
  before_acks=total_acks;
  fork
   begin ui(2);end
   begin repeat(30)@(negedge clk);if(!reserved||show_requested||valid)$fatal(1,"CLEAR early release");repeat(70)@(negedge clk);visible=0;end
  join
  repeat(10)@(negedge clk);if(reserved||valid||show_requested||total_acks!=before_acks)$fatal(1,"UI clear response/reservation");
  // Original capture mode after releasing the score; raw bytes/checksum intact.
  cap_command(1);
  for(k=0;k<8;k=k+1)begin @(negedge clk);cap_tick=1;@(negedge clk);cap_tick=0;repeat(30)@(negedge clk);end
  wait(cap_ready);if(cap_count!=8)$fatal(1,"capture sample count");
  sum=32'hffffffff;for(k=0;k<8;k=k+1)begin sum=crc32(sum,8'h68);sum=crc32(sum,8'h24);end
  if(cap_crc!==(~sum))$fatal(1,"capture CRC");
  if(!compat_ready||compat_count!=8||compat_crc!==cap_crc)$fatal(1,"capture-only compatibility");
  before_write=write_count;begin_page(2,0,4);
  if(write_count!=before_write||!cap_ready||reserved)$fatal(1,"ready capture overwritten");
  for(k=0;k<8;k=k+1)begin @(negedge clk);cap_address=k;@(posedge clk);#1;if(cap_q!==16'h2468||compat_q!==16'h2468)$fatal(1,"capture readback");end
  cap_command(0);
  // Timed-out staging and incomplete outer frame recover without publishing.
  begin_page(2,0,0);repeat(200010)@(negedge clk);
  if(reserved||valid||loading)$fatal(1,"upload timeout");command(19,0,0,5);
  @(negedge clk);rx_valid=1;rx_data=8'ha5;@(negedge clk);rx_valid=0;repeat(310)@(negedge clk);
  command(16,0,0,0);
  recorder_active=1;begin_page(2,0,4);command(16,0,0,0);recorder_active=0;
  fake_busy=1;begin_page(2,0,4);fake_busy=0;send_packet(0,"P");command(19,0,0,5);
  // Even a missing video hide ACK cannot release RAM for premature capture.
  visible=1;begin_page(2,0,5);
  if(!reserved||loading||valid)$fatal(1,"hide timeout unsafe release");
  visible=0;repeat(5)@(negedge clk);if(reserved)$fatal(1,"hide timeout no recovery");
  capability(1);capability(0);
  $fclose(ack_file);
  $display("PASS score: %d CRC-checked replies, Java 845 frames including sequence wrap, full 65536-byte dual-clock readback, RLE/CRC/bounds/retry/visibility/capture/UI/timeouts",total_acks);
  $finish;
 end
 initial begin #200000000;$fatal(1,"overall timeout");end
endmodule
