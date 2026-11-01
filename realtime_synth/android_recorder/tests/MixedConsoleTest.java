package cn.tangsynth.recorder;
import java.io.*;
import java.nio.file.*;

/** Read the byte stream decoded from the integrated FPGA Bluetooth TX pin. */
public final class MixedConsoleTest {
    public static void main(String[] args)throws Exception{
        String[] rows=new String(Files.readAllBytes(Paths.get(args[0])),"US-ASCII").trim().split("\\s+");
        byte[] raw=new byte[rows.length];for(int i=0;i<rows.length;i++)raw[i]=(byte)Integer.parseInt(rows[i],16);
        ProtocolTest.Fragmented wire=new ProtocolTest.Fragmented(raw);StreamReader reader=new StreamReader();
        int info=0,data=0,end=0,acks=0;
        while(wire.available()>0){
            if(reader.read(wire)){
                AudioFrame f=reader.audio;
                if(f.type==AudioFrame.INFO)info++;
                else if(f.type==AudioFrame.DATA){if(f.sequence!=data)throw new AssertionError("audio sequence");data++;}
                else {if(f.sequence!=data || f.field!=0)throw new AssertionError("record end");end++;}
            }else{
                if(reader.acknowledgement.status!=0)throw new AssertionError("guide failed");acks++;
            }
        }
        int expectedAcks=args.length>1?Integer.parseInt(args[1]):26;
        if(info!=1 || data!=4 || end!=1 || acks!=expectedAcks)throw new AssertionError("unexpected complete-frame counts");
        System.out.println("PASS integrated FPGA TX pin stream: "+acks+" TGAK + TREC INFO, four DATA and FINISH, all CRCs verified");
    }
}
