package cn.tangsynth.recorder;
import java.nio.file.*;
import java.util.Arrays;

/** Decode the FPGA simulation's actual byte-for-byte replies with the Android decoder. */
public final class GuideAckTest {
    public static void main(String[] args)throws Exception{
        String[] text=new String(Files.readAllBytes(Paths.get(args[0])),"US-ASCII").trim().split("\\s+");
        byte[] bytes=new byte[text.length];for(int i=0;i<text.length;i++)bytes[i]=(byte)Integer.parseInt(text[i],16);
        if(bytes.length!=24*24)throw new AssertionError("expected 24 complete replies");
        for(int i=0;i<24;i++){
            GuideProtocol.Ack a=new GuideProtocol.Ack(Arrays.copyOfRange(bytes,i*24,(i+1)*24));
            int operation=i==0?1:i<22?2:i==22?3:4;
            if(a.sequence!=i+1 || a.operation!=operation || a.status!=0)throw new AssertionError("reply "+i);
            if(i>0 && i<22 && a.received!=i*4)throw new AssertionError("write progress");
            if(i>=22 && (a.count!=84 || a.durationCs!=2400 || !a.valid()))throw new AssertionError("committed score");
            if(i==23 && !a.playing())throw new AssertionError("play did not begin");
        }
        System.out.println("PASS Android decoded all 24 actual FPGA TGAK replies, progress, commit and playback");
    }
}
