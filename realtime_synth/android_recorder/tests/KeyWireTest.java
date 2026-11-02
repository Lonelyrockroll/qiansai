package cn.tangsynth.recorder;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Pair real app-encoded requests with the reply bytes decoded from bt_console TX. */
public final class KeyWireTest {
    static final int[][] COMMANDS={{1,24,14},{2,25,14,15},{2,25,14,15},{3,24,14},{4,24,15},
            {5,25,0,31},{5,25,0,31},{6,26},{6,26},{7,24,14},{8,24,32},{9,25,14,32},{10,26,0},{11,25,7,8}};
    static final int[] STATUS={0,0,0,0,0,4,0,4,0,0,3,3,3,1};
    static byte[] request(int i){
        int[] command=COMMANDS[i];byte[] payload=new byte[command.length-2];
        for(int n=0;n<payload.length;n++)payload[n]=(byte)command[n+2];
        byte[] frame=GuideProtocol.frame(command[0],command[1],payload);
        if(i==COMMANDS.length-1)frame[26]^=1;
        return frame;
    }
    static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    public static void main(String[] args)throws Exception{
        if(args[0].equals("requests")){
            StringBuilder lines=new StringBuilder();
            for(int i=0;i<COMMANDS.length;i++)for(byte b:request(i))lines.append(String.format("%02x%n",b&255));
            Files.write(Paths.get(args[1]),lines.toString().getBytes("US-ASCII"));return;
        }
        String[] hex=new String(Files.readAllBytes(Paths.get(args[1])),"US-ASCII").trim().split("\\s+");
        byte[] wire=new byte[hex.length];for(int i=0;i<wire.length;i++)wire[i]=(byte)Integer.parseInt(hex[i],16);
        check(wire.length==(1+COMMANDS.length)*24,"reply length");
        StreamReader reader=new StreamReader();InputStream input=new ProtocolTest.Fragmented(wire);
        check(!reader.read(input) && reader.keyAcknowledgement!=null && reader.keyAcknowledgement.sequence==0 && reader.keyAcknowledgement.operation==24,"~J capability");
        int[] map=new int[32];for(int k=0;k<32;k++)map[k]=k;
        for(int i=0;i<COMMANDS.length;i++){
            check(!reader.read(input) && reader.keyAcknowledgement!=null,"expected TKAK "+i);
            KeyProtocol.Ack a=reader.keyAcknowledgement;int[] c=COMMANDS[i];
            check(a.sequence==c[0] && a.operation==c[1] && a.status==STATUS[i],"status/frame "+i);
            if(a.status!=0)continue;
            if(c[1]==25 && i!=2){int tmp=map[c[2]];map[c[2]]=map[c[3]];map[c[3]]=tmp;}
            if(c[1]==26)for(int k=0;k<32;k++)map[k]=k;
            int ka=c.length>=3?c[2]:0,kb=c.length>=4?c[3]:0;
            check(a.keyA==ka && a.noteA==map[ka] && a.keyB==kb && a.noteB==map[kb],"wrong physical pitch "+i);
        }
        System.out.println("PASS Java StreamReader decoded all 15 physical UART TKAKs: ~J, query, swap retries, BUSY, restore, invalid input and CRC");
    }
}
