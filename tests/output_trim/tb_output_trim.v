`timescale 1ns/1ps
module tb_output_trim;
    reg clk=0;always #10 clk=~clk;
    reg rst=1;
    reg [15:0] left=16'h0000,right=16'hffff;
    reg [11:0] trim=683;
    wire tick,ib,iw,id,hb,hw,hd;
    integer cycles=0,frames=0,last_tick=0,icount=0,pcount=0,checks=0;
    reg [15:0] il=0,ir=0,pl=0,pr=0;
    reg [15:0] expected_left=0,expected_right=0,expected_pt_left=0,expected_pt_right=0;
    function [15:0] biased(input signed [15:0] x); integer sum;begin sum=x+$signed({1'b0,trim});biased=sum>32767?16'h7fff:sum< -32768?16'h8000:sum;end endfunction
    audio_tx #(.USE_PT_TRIM(1)) dut(.pt_mode(2'd0),.pt_trim(trim),.clk(clk),.rst(rst),.pcm_left(left),.pcm_right(right),.sample_tick(tick),
        .i2s_bclk(ib),.i2s_lrclk(iw),.i2s_data(id),.hp_bck(hb),.hp_ws(hw),.hp_din(hd));
    always @(posedge clk) begin
        cycles=cycles+1;
        if (!rst && tick) begin
            if (frames>0) begin
                if(cycles-last_tick!=1024) $fatal(1,"frame period");
                if(icount!=64 || pcount!=32) $fatal(1,"bit counts");
                if(il!==expected_left || ir!==expected_right || pl!==expected_pt_left || pr!==expected_pt_right)
                    $fatal(1,"serial mismatch I2S=%h/%h PT=%h/%h expected=%h/%h",il,ir,pl,pr,expected_left,expected_right);
                checks=checks+1;
            end
            expected_left=left;expected_right=right;expected_pt_left=biased(left);expected_pt_right=biased(right);
            frames=frames+1;last_tick=cycles;icount=0;pcount=0;
        end
    end
    // Decode from pins and independent serial bit counters, not internal serializer state.
    always @(posedge ib) if (!rst && frames>0) begin
        if(iw !== (icount>=32)) $fatal(1,"I2S channel polarity");
        if(icount%32>=1 && icount%32<=16) begin
            if(icount<32) il={il[14:0],id}; else ir={ir[14:0],id};
        end else if(id!==0) $fatal(1,"I2S padding");
        icount=icount+1;
    end
    always @(posedge hb) if (!rst && frames>0) begin
        if(hw !== (pcount>=16)) $fatal(1,"PT channel polarity");
        if(pcount<16) pr={pr[14:0],hd};else pl={pl[14:0],hd};
        pcount=pcount+1;
    end
    initial begin
        repeat(5) @(negedge clk);rst=0;
        wait(frames==3);repeat(80) @(negedge clk);left=16'h8000;right=16'h7fff;
        wait(frames==5);repeat(127) @(negedge clk);trim=789;left=-201;right=200;
        wait(frames==8);repeat(600) @(negedge clk);trim=4095;left=28000;right=-28000;
        wait(frames==11);repeat(48) @(negedge clk);trim=0;left=16'h8000;right=16'h7fff;
        wait(frames==14);
        if(checks!=13) $fatal(1,"checks missing");
        $display("PASS biased PT / unchanged I2S, zero and saturation: polarity, one-bit I2S delay, padding, 16-bit PT, frame coherence, 1024-cycle period");
        $finish;
    end
    initial begin #400000; $fatal(1,"timeout");end
endmodule
