`timescale 1ns/1ps
// Independent full raster scoreboard: row=floor(y*512/600), MSB-left.
module score_raster_tb;
 reg clk=0,sys_clk=0,rst=1,request=0;
 always #5 clk=~clk;
 always #7 sys_clk=~sys_clk;
 wire [10:0] x,y;wire hs,vs,de,frame_start;
 video_timing timing(.clk(clk),.rst(rst),.x(x),.y(y),.hs(hs),.vs(vs),.de(de),.frame_start(frame_start));
 wire [14:0] address;wire [15:0] data,sys_q;
 wire visible,selected;wire [23:0] rgb;
 reg [14:0] sys_address=0;
 score_capture_ram ram(.sys_clk(sys_clk),.sys_write(1'b0),.sys_address(sys_address),.sys_data(16'd0),.sys_q(sys_q),
  .pixel_clk(clk),.pixel_address(address),.pixel_q(data));
 score_renderer dut(.clk(clk),.rst(rst),.show_requested(request),.x(x),.y(y),.de(de),.frame_start(frame_start),
  .read_address(address),.read_data(data),.visible(visible),.select_page(selected),.rgb(rgb));
 reg [7:0] raw[0:65535];
 integer mode=0,frame_limit=5,image_frame=1,fd=0,input_file,loaded,i;
 string raw_path,image_path;
 function [15:0] pattern_word(input integer a);
 begin pattern_word=((a*16'h1021)^(a>>3)^16'ha6d3)&16'hffff;end endfunction
 function [15:0] expected_word(input integer a);
 begin expected_word=mode?{raw[a*2],raw[a*2+1]}:pattern_word(a);end endfunction
 function [23:0] expected_pixel(input integer px,py);
 integer row,bit_index;reg black;
 begin
  row=(py*512)/600;
  if(mode)begin bit_index=row*128+px/8;black=(raw[bit_index]>>(7-(px%8)))&1;end
  else begin bit_index=row*64+px/16;black=(pattern_word(bit_index)>>(15-(px%16)))&1;end
  expected_pixel=black?24'h000000:24'hffffff;
 end endfunction
 initial begin
  if(!$value$plusargs("MODE=%d",mode))mode=0;
  if(!$value$plusargs("FRAMES=%d",frame_limit))frame_limit=5;
  if(mode)begin
   if(!$value$plusargs("RAW=%s",raw_path))$fatal(1,"Need +RAW input");
   input_file=$fopen(raw_path,"rb");if(!input_file)$fatal(1,"Cannot open raw input");
   loaded=$fread(raw,input_file);$fclose(input_file);if(loaded!=65536)$fatal(1,"Raw input size %d",loaded);
  end
  for(i=0;i<32768;i=i+1)ram.memory[i]=expected_word(i);
  if($value$plusargs("IMAGE=%s",image_path))begin
   fd=$fopen(image_path,"wb");if(!fd)$fatal(1,"Cannot open frame output");
   $fwrite(fd,"P6\n1024 600\n255\n");
  end
  repeat(4)@(negedge clk);rst=0;
 end
 // The requests are deliberately not aligned with a pixel clock edge.
 // Final request is too close to the frame latch and must wait another frame.
 integer input_frame=-1;
 always @(negedge clk)if(!rst)begin
  if(input_frame==0 && y==100 && x==100)#2 request=1;
  if(input_frame==1 && y==200 && x==101)#2 request=0;
  if(input_frame==2 && y==599 && x==1311)#2 request=1;
 end
 integer pixels=0,cycles=0,frame_pixels[0:7],image_pixels=0,edges=0,last_rows=0;
 reg [23:0] exp_rgb[0:2];reg exp_de[0:2],exp_select[0:2],valid[0:2];
 integer exp_x[0:2],exp_y[0:2],exp_frame[0:2];
 reg golden_visible=0,sync1=0,sync2=0;
 initial begin for(i=0;i<8;i=i+1)frame_pixels[i]=0;end
 integer j;
 always @(posedge clk)begin
  if(rst)begin
   for(j=0;j<3;j=j+1)begin valid[j]=0;exp_de[j]=0;exp_select[j]=0;end
   golden_visible=0;sync1=0;sync2=0;input_frame=-1;
  end else begin
   cycles=cycles+1;
   if(x==0 && y==0)begin
    input_frame=input_frame+1;
    case(input_frame)
     0,2,3:if(visible!==0)$fatal(1,"Frame %d became visible too early",input_frame);
     1,4:if(visible!==1)$fatal(1,"Frame %d did not become visible",input_frame);
    endcase
   end
   if(de && address!==((y*512/600)*64+x/16))$fatal(1,"Address at frame %d x=%d y=%d got %d expected %d",input_frame,x,y,address,(y*512/600)*64+x/16);
   for(j=2;j>0;j=j-1)begin
    exp_rgb[j]=exp_rgb[j-1];exp_de[j]=exp_de[j-1];exp_select[j]=exp_select[j-1];valid[j]=valid[j-1];
    exp_x[j]=exp_x[j-1];exp_y[j]=exp_y[j-1];exp_frame[j]=exp_frame[j-1];
   end
   valid[0]=1;exp_de[0]=de;exp_select[0]=golden_visible;
   exp_rgb[0]=expected_pixel(x,y);exp_x[0]=x;exp_y[0]=y;exp_frame[0]=input_frame;
   if(frame_start)golden_visible=sync2;
   sync2=sync1;sync1=request;
   #1;
   if(visible!==golden_visible)$fatal(1,"Visible changed outside expected frame latch");
   if(valid[2])begin
    if(selected!==exp_select[2])$fatal(1,"Page select latency differs from three pixel stages");
    if(exp_de[2] && exp_frame[2]<frame_limit)begin
     if(rgb!==exp_rgb[2])$fatal(1,"RGB frame %d x=%d y=%d got %h expected %h",exp_frame[2],exp_x[2],exp_y[2],rgb,exp_rgb[2]);
     pixels=pixels+1;frame_pixels[exp_frame[2]]=frame_pixels[exp_frame[2]]+1;
     if(exp_x[2]==0 || exp_x[2]==1023)edges=edges+1;
     if(exp_y[2]==599)last_rows=last_rows+1;
     if(fd && exp_frame[2]==image_frame)begin $fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);image_pixels=image_pixels+1;end
     if(pixels==frame_limit*614400)begin
      for(j=0;j<frame_limit;j=j+1)if(frame_pixels[j]!=614400)$fatal(1,"Incomplete frame %d",j);
      if(fd)begin if(image_pixels!=614400)$fatal(1,"Incomplete exported image");$fclose(fd);end
      $display("PASS raster mode=%0d frames=%0d pixels=%0d line_edges=%0d last_row_pixels=%0d cycles=%0d",mode,frame_limit,pixels,edges,last_rows,cycles);
      $finish;
     end
    end
   end
  end
 end
 // Separate actual system port with unrelated clock; result is sampled one
 // clock after each address setup, exercising the same RAM's synchronous read.
 always @(negedge sys_clk)if(!rst)sys_address<=sys_address+15'd173;
 always @(posedge sys_clk)if(!rst)begin
  #1;if(sys_q!==expected_word(sys_address))$fatal(1,"System RAM read latency/data error at %d",sys_address);
 end
 initial begin #100000000;$fatal(1,"Raster test timeout");end
endmodule
