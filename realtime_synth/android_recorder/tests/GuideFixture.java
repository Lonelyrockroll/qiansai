package cn.tangsynth.recorder;

import java.nio.file.*;
import java.io.*;
import java.util.*;

/** Replays the shipped example into the same wire encoder used by the Android UI. */
public final class GuideFixture {
    public static void main(String[] args)throws Exception{
        Path base=Paths.get(args[0]),out=Paths.get(args[1]);Files.createDirectories(out);
        MidiGuide.Compiled song=MidiGuide.compile(MidiGuide.parse(Files.readAllBytes(base)),0);
        List<byte[]> packets=new ArrayList<>();int seq=1;
        byte[] header=new byte[8];GuideProtocol.put16(header,0,song.words.length);GuideProtocol.put16(header,2,song.durationCs);GuideProtocol.put32(header,4,song.crc32);
        packets.add(GuideProtocol.request(seq++,1,header));
        for(int offset=0;offset<song.words.length;offset+=4){
            int n=Math.min(4,song.words.length-offset);byte[] body=new byte[3+4*n];GuideProtocol.put16(body,0,offset);body[2]=(byte)n;
            for(int i=0;i<n;i++)GuideProtocol.put32(body,3+4*i,song.words[offset+i]);
            packets.add(GuideProtocol.request(seq++,2,body));
        }
        packets.add(GuideProtocol.request(seq++,3,new byte[0]));
        packets.add(GuideProtocol.request(seq,4,new byte[]{1}));
        StringBuilder words=new StringBuilder(),wire=new StringBuilder();
        for(int w:song.words)words.append(String.format(Locale.US,"%08x%n",w));
        for(byte[] packet:packets)for(byte b:packet)wire.append(String.format(Locale.US,"%02x%n",b&255));
        Files.write(out.resolve("demo-events.hex"),words.toString().getBytes("US-ASCII"));
        Files.write(out.resolve("demo-upload.hex"),wire.toString().getBytes("US-ASCII"));
        String meta="{\n  \"events\": "+song.words.length+",\n  \"duration_cs\": "+song.durationCs+",\n  \"crc32\": "+song.crc32+",\n  \"packets\": "+packets.size()+",\n  \"wire_bytes\": "+packets.size()*28+"\n}\n";
        Files.write(out.resolve("demo.json"),meta.getBytes("UTF-8"));
        System.out.println(meta);
    }
}
