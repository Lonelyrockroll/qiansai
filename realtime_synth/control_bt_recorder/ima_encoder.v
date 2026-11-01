// IMA ADPCM; a block's first sample is sent as a literal predictor.
module ima_encoder(input wire clk,rst,seed,encode,input wire signed [15:0] sample,
 output reg valid,output reg [3:0] code,output reg [6:0] step_index);
 reg signed [15:0] predictor;
 reg signed [16:0] diff;
 reg sign_bit,b4,b2;
 reg [16:0] remaining,restore_delta;
 reg [14:0] step;
 reg [2:0] state;
 function [14:0] lookup(input [6:0] ix);
 begin case(ix)
   0:lookup=15'd7;
   1:lookup=15'd8;
   2:lookup=15'd9;
   3:lookup=15'd10;
   4:lookup=15'd11;
   5:lookup=15'd12;
   6:lookup=15'd13;
   7:lookup=15'd14;
   8:lookup=15'd16;
   9:lookup=15'd17;
   10:lookup=15'd19;
   11:lookup=15'd21;
   12:lookup=15'd23;
   13:lookup=15'd25;
   14:lookup=15'd28;
   15:lookup=15'd31;
   16:lookup=15'd34;
   17:lookup=15'd37;
   18:lookup=15'd41;
   19:lookup=15'd45;
   20:lookup=15'd50;
   21:lookup=15'd55;
   22:lookup=15'd60;
   23:lookup=15'd66;
   24:lookup=15'd73;
   25:lookup=15'd80;
   26:lookup=15'd88;
   27:lookup=15'd97;
   28:lookup=15'd107;
   29:lookup=15'd118;
   30:lookup=15'd130;
   31:lookup=15'd143;
   32:lookup=15'd157;
   33:lookup=15'd173;
   34:lookup=15'd190;
   35:lookup=15'd209;
   36:lookup=15'd230;
   37:lookup=15'd253;
   38:lookup=15'd279;
   39:lookup=15'd307;
   40:lookup=15'd337;
   41:lookup=15'd371;
   42:lookup=15'd408;
   43:lookup=15'd449;
   44:lookup=15'd494;
   45:lookup=15'd544;
   46:lookup=15'd598;
   47:lookup=15'd658;
   48:lookup=15'd724;
   49:lookup=15'd796;
   50:lookup=15'd876;
   51:lookup=15'd963;
   52:lookup=15'd1060;
   53:lookup=15'd1166;
   54:lookup=15'd1282;
   55:lookup=15'd1411;
   56:lookup=15'd1552;
   57:lookup=15'd1707;
   58:lookup=15'd1878;
   59:lookup=15'd2066;
   60:lookup=15'd2272;
   61:lookup=15'd2499;
   62:lookup=15'd2749;
   63:lookup=15'd3024;
   64:lookup=15'd3327;
   65:lookup=15'd3660;
   66:lookup=15'd4026;
   67:lookup=15'd4428;
   68:lookup=15'd4871;
   69:lookup=15'd5358;
   70:lookup=15'd5894;
   71:lookup=15'd6484;
   72:lookup=15'd7132;
   73:lookup=15'd7845;
   74:lookup=15'd8630;
   75:lookup=15'd9493;
   76:lookup=15'd10442;
   77:lookup=15'd11487;
   78:lookup=15'd12635;
   79:lookup=15'd13899;
   80:lookup=15'd15289;
   81:lookup=15'd16818;
   82:lookup=15'd18500;
   83:lookup=15'd20350;
   84:lookup=15'd22385;
   85:lookup=15'd24623;
   86:lookup=15'd27086;
   87:lookup=15'd29794;
   88:lookup=15'd32767;
   default:lookup=32767;
 endcase end endfunction
 wire [16:0] quarter={2'b0,step}>>2;
 wire b1=remaining>=quarter;
 wire [16:0] reconstructed=restore_delta+(b1?quarter:17'd0);
 wire signed [17:0] next_pred=$signed({{2{predictor[15]}},predictor})+
      (sign_bit?-$signed({1'b0,reconstructed}):$signed({1'b0,reconstructed}));
 wire [7:0] increase=step_index+({6'd0,b2,b1}<<1)+8'd2;
 always @(posedge clk)begin
  if(rst)begin valid<=0;state<=0;step_index<=0;predictor<=0;code<=0;end
  else begin
   valid<=0;
   if(seed)begin predictor<=sample;state<=0;end
   else case(state)
    0:if(encode)begin
     diff<=$signed({sample[15],sample})-$signed({predictor[15],predictor});
     step<=lookup(step_index);state<=1;
    end
    1:begin sign_bit<=diff[16];remaining<=diff[16]?-diff:diff;state<=2;end
    2:begin
     b4<=remaining>=step;
     if(remaining>=step)remaining<=remaining-step;
     restore_delta<=(step>>3)+(remaining>=step?{2'b0,step}:17'd0);state<=3;
    end
    3:begin
     b2<=remaining>=(step>>1);
     if(remaining>=(step>>1))begin remaining<=remaining-(step>>1);restore_delta<=restore_delta+(step>>1);end
     state<=4;
    end
    4:begin
     code<={sign_bit,b4,b2,b1};valid<=1;state<=0;
     predictor<=next_pred>32767?16'sh7fff:next_pred< -32768?16'sh8000:next_pred[15:0];
     if(b4)step_index<=increase>88?7'd88:increase[6:0];
     else if(step_index!=0)step_index<=step_index-1'b1;
    end
    default:state<=0;
   endcase
  end
 end
endmodule
