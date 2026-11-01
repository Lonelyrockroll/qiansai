package cn.tangsynth.recorder;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Actual FPGA TPAK byte trace paired with Java-generated page upload requests. */
public final class ScoreAckTest {
    static byte[] hex(String file)throws IOException{
        String[] rows=new String(Files.readAllBytes(Paths.get(file)),"US-ASCII").trim().split("\\s+");
        byte[] a=new byte[rows.length];for(int i=0;i<a.length;i++)a[i]=(byte)Integer.parseInt(rows[i],16);return a;
    }
    public static void main(String[] args)throws Exception{
        byte[] wire=hex(args[0]),requests=hex(args[1]);
        if(requests.length%28!=0 || wire.length!=requests.length/28*24)throw new AssertionError("reply count");
        StreamReader stream=new StreamReader();InputStream fragmented=new ProtocolTest.Fragmented(wire);
        int expectedReceived=0,commits=0,shows=0;
        for(int i=0;i<requests.length/28;i++){
            byte[] req=Arrays.copyOfRange(requests,i*28,(i+1)*28);
            if(stream.read(fragmented) || stream.scoreAcknowledgement==null)throw new AssertionError("wrong protocol");
            ScoreProtocol.Ack a=stream.scoreAcknowledgement;
            if(a.sequence!=(req[3]&255) || a.operation!=(req[4]&255) || a.status!=0)throw new AssertionError("request/reply pair "+i);
            if(a.operation==ScoreProtocol.BEGIN)expectedReceived=0;
            if(a.operation==ScoreProtocol.DATA)expectedReceived+=req[9]&255;
            if(a.received!=expectedReceived)throw new AssertionError("progress "+i);
            if(a.index!=0 || a.count!=2)throw new AssertionError("page metadata "+i);
            if(a.operation==ScoreProtocol.COMMIT){if(!a.valid() || a.decoded!=65536)throw new AssertionError("commit");commits++;}
            if(a.operation==ScoreProtocol.CONTROL){if(!a.valid() || !a.showing())throw new AssertionError("show");shows++;}
        }
        if(commits!=1 || shows!=1)throw new AssertionError("missing completion");
        System.out.println("PASS Android actual decoder: "+wire.length/24+" FPGA TPAK replies, sequence wraps, receive progress, raw65536 commit and full-screen show");
    }
}
