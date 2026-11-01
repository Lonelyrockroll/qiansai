`timescale 1ns/1ps
module tb_tone;
    localparam FRAMES=38000, NOTE_OFF=24000;
    reg clk=0,rst=1,start=0,gate=0,retrigger=0;
    always #10 clk=~clk;
    reg [4:0] voice;
    reg [31:0] step;
    wire signed [15:0] sample;
    wire done;
    piano_modal_mixed dut(.clk(clk),.rst(rst),.start(start),.voice(voice),
        .gate(gate),.retrigger(retrigger),.step(step),.level(16'd16384),
        .attack(16'd672),.release_step(16'd8),.sample(sample),.done(done));
    integer frame,fd,lane;
    reg [31:0] contributed=0,held=0;
    // Count actual nonzero lane products. No inference from the ROM coefficients.
    always @(posedge clk) if(!rst && frame<2048)begin
`ifdef ORIGINAL16
        if(dut.state==dut.ADD)
            for(lane=0;lane<4;lane=lane+1)begin
                held[{dut.group,lane[1:0]}]=dut.alive[lane];
                if(($signed(dut.products[lane])>>>15)!=0)
                    contributed[{dut.group,lane[1:0]}]=1;
            end
`else
        if(dut.valid[3])
            for(lane=0;lane<4;lane=lane+1)begin
                held[{dut.add_index[2:0],lane[1:0]}]=dut.alive[lane];
                if(($signed(dut.products[lane])>>>15)!=0)
                    contributed[{dut.add_index[2:0],lane[1:0]}]=1;
            end
`endif
    end
    reg [2047:0] filename;
    initial begin
        if(!$value$plusargs("step=%d",step) || !$value$plusargs("voice=%d",voice) ||
           !$value$plusargs("output=%s",filename)) $fatal(1,"Missing tone/voice/path");
        fd=$fopen(filename,"wb");if(fd==0)$fatal(1,"Cannot open sample output");
        repeat(4)@(negedge clk);rst=0;
        for(frame=0;frame<FRAMES;frame=frame+1)begin
            @(negedge clk);gate=frame<NOTE_OFF;retrigger=frame==0;start=1;
            @(negedge clk);start=0;@(posedge done);#1;
            if((^sample)===1'bx)$fatal(1,"Undefined wave at %d",frame);
            $fwrite(fd,"%c%c",sample[7:0],sample[15:8]);
        end
        $fclose(fd);
        $display("PASS early_nonzero=%08h alive_at_2048=%08h",contributed,held);
        $finish;
    end
endmodule
