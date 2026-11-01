`timescale 1ns/1ps
module tb_ab;
    reg clk=0, rst=1, start=0, gate=0, retrigger=0;
    always #10 clk=!clk;
    localparam FRAMES=60000, RELEASE_AT=50000;
    wire done16,done32;
    wire signed [15:0] sample16,sample32;
    piano_modal_mixed #(.MODE_MASK(32'h0000ffff)) a(
        .clk(clk),.rst(rst),.start(start),.voice(5'd0),.gate(gate),.retrigger(retrigger),
        .step(32'd23012828),.level(16'd16384),.attack(16'd672),.release_step(16'd8),
        .done(done16),.sample(sample16));
    piano_modal_mixed #(.MODE_MASK(32'hffffffff)) b(
        .clk(clk),.rst(rst),.start(start),.voice(5'd0),.gate(gate),.retrigger(retrigger),
        .step(32'd23012828),.level(16'd16384),.attack(16'd672),.release_step(16'd8),
        .done(done32),.sample(sample32));
    integer i,fd;
    initial begin
        fd=$fopen("samples.txt","w");if(fd==0)$fatal(1,"samples.txt");
        repeat(4)@(negedge clk);rst=0;
        // Skip only idle clocks between requests. Each output sample still runs
        // the real READ/CALC/ENV/MUL/ADD state, sine ROM and all release updates.
        for(i=0;i<FRAMES;i=i+1)begin
            @(negedge clk);gate=i<RELEASE_AT;retrigger=i==0;start=1;
            @(negedge clk);start=0;
            @(posedge done32);#1;
            if(!done16 || (^sample16)===1'bx || (^sample32)===1'bx)$fatal(1,"unaligned/unknown output");
            $fdisplay(fd,"%0d %0d",sample16,sample32);
        end
        $fclose(fd);$display("PASS 60000 C4 frames per take, only MODE_MASK differs");$finish;
    end
    initial begin #40000000;$fatal(1,"audition timeout");end
endmodule
