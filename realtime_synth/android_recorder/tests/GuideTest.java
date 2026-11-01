package cn.tangsynth.recorder;

import java.io.*;
import java.util.Arrays;

public final class GuideTest {
    static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    static byte[] bytes(int...values){byte[] a=new byte[values.length];for(int i=0;i<a.length;i++)a[i]=(byte)values[i];return a;}
    static byte[] midi(int format,int div,byte[]...tracks)throws IOException{
        ByteArrayOutputStream raw=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(raw);
        out.writeBytes("MThd");out.writeInt(6);out.writeShort(format);out.writeShort(tracks.length);out.writeShort(div);
        for(byte[] track:tracks){out.writeBytes("MTrk");out.writeInt(track.length);out.write(track);}
        return raw.toByteArray();
    }
    interface Bad {void run()throws Exception;}
    static void bad(Bad action)throws Exception{try{action.run();throw new AssertionError("accepted invalid input");}catch(IOException expected){}}
    static int time(int word){return word&65535;}
    static boolean on(int word){return (word&(1<<21))!=0;}
    static byte[] reply(int seq,int operation,int status){
        byte[] a=new byte[24];a[0]='T';a[1]='G';a[2]='A';a[3]='K';a[4]=1;a[5]=(byte)seq;a[6]=(byte)operation;a[7]=(byte)status;
        GuideProtocol.put16(a,8,4);GuideProtocol.put16(a,10,4);GuideProtocol.put16(a,12,20);GuideProtocol.put16(a,14,100);
        a[16]=3;a[17]=2;GuideProtocol.put16(a,22,GuideProtocol.crc16(a,4,22));return a;
    }
    static byte[] audioInfo(){
        byte[] a=new byte[16];a[0]='T';a[1]='R';a[2]='E';a[3]='C';a[4]=1;a[5]=3;
        GuideProtocol.put16(a,14,GuideProtocol.crc16(a,4,14));return a;
    }
    public static void main(String[] args)throws Exception{
        byte[] track=bytes(0,0x90,60,64,0x83,0x60,0x80,60,0,0,0xff,0x2f,0);
        MidiGuide.Song s=MidiGuide.parse(midi(0,480,track));MidiGuide.Compiled c=MidiGuide.compile(s,0);
        check(c.words.length==2 && time(c.words[0])==0 && time(c.words[1])==50 && c.durationCs==51,"default tempo");
        check((c.words[0]>>>16 &31)==14 && on(c.words[0]) && !on(c.words[1]),"C4 is white key 15");
        byte[] conductor=bytes(0,0xff,0x51,3,7,0xa1,0x20,0x83,0x60,0xff,0x51,3,0x0f,0x42,0x40,0,0xff,0x2f,0);
        byte[] longNote=bytes(0,0x90,60,64,0x87,0x40,0x90,60,0,0,0xff,0x2f,0);
        c=MidiGuide.compile(MidiGuide.parse(midi(1,480,conductor,longNote)),1);
        check(time(c.words[1])==150 && (c.words[0]>>>22 &3)==1,"tempo map, velocity-zero release and original track color");
        byte[] running=bytes(0,0x90,60,64,120,64,64,120,0x80,60,0,120,64,0,0,0xff,0x2f,0);
        c=MidiGuide.compile(MidiGuide.parse(midi(0,480,running)),0);
        check(c.words.length==4 && time(c.words[1])==13 && time(c.words[2])==25,"running status");
        byte[] overlap=bytes(0,0x90,60,64,120,60,64,120,0x80,60,0,0x81,0x70,60,0,0,0xff,0x2f,0);
        c=MidiGuide.compile(MidiGuide.parse(midi(0,480,overlap)),0);
        check(c.words.length==3 && on(c.words[1]) && time(c.words[2])==50,"overlapping same pitch stays held");
        byte[] pedal=bytes(0,0xb0,64,127,0,0x90,60,64,0x83,0x60,0x80,60,0,0x83,0x60,0xb0,64,0,0,0xff,0x2f,0);
        c=MidiGuide.compile(MidiGuide.parse(midi(0,480,pedal)),0);
        check(time(c.words[1])==100,"sustain holds until CC64 release");
        byte[] unsupported=bytes(0,0x90,61,64,0,35,64,0,60,64,0x83,0x60,0x80,61,0,0,35,0,0,60,0,0,0xff,0x2f,0);
        c=MidiGuide.compile(MidiGuide.parse(midi(0,480,unsupported)),0);
        check(c.blackKeys==1 && c.outside==1 && c.notes==1 && c.words.length==2,"unsupported notes are counted, not remapped");
        bad(()->MidiGuide.parse(midi(2,480,track)));
        bad(()->MidiGuide.parse(midi(0,0xe728,track)));
        bad(()->MidiGuide.parse(midi(0,480,bytes(0x81,0x81,0x81,0x81,0))));
        bad(()->MidiGuide.parse(midi(0,480,bytes(0,60,64))));
        bad(()->MidiGuide.parse(Arrays.copyOf(midi(0,480,track),25)));
        bad(()->MidiGuide.compile(MidiGuide.parse(midi(0,480,bytes(0,0x99,60,64,1,0x89,60,0))),0));
        ByteArrayOutputStream many=new ByteArrayOutputStream();
        for(int i=0;i<257;i++){many.write(bytes(1,0x90,60,64,12,0x80,60,0));}
        bad(()->MidiGuide.compile(MidiGuide.parse(midi(0,480,many.toByteArray())),0));
        byte[] packet=GuideProtocol.request(201,GuideProtocol.WRITE,bytes(0,0,1,0x7e,0x55,0x4d,0x54));
        check(packet.length==28 && packet[0]==(byte)0xa5 && GuideProtocol.u16(packet,26)==GuideProtocol.crc16(packet,2,26),"request bytes + CRC");
        GuideProtocol.Ack a=new GuideProtocol.Ack(reply(201,2,0));
        check(a.sequence==201 && a.playing() && a.valid() && a.durationCs==100,"ack data");
        byte[] damaged=reply(201,2,0);damaged[10]^=1;bad(()->new GuideProtocol.Ack(damaged));
        ByteArrayOutputStream mixed=new ByteArrayOutputStream();mixed.write("OK V02\r\n".getBytes("US-ASCII"));
        mixed.write(audioInfo());mixed.write(damaged);mixed.write(reply(201,2,0));mixed.write(audioInfo());
        StreamReader reader=new StreamReader();InputStream wire=new ProtocolTest.Fragmented(mixed.toByteArray());
        check(reader.read(wire) && reader.audio.type==AudioFrame.INFO,"TREC before guide");
        check(!reader.read(wire) && reader.acknowledgement.sequence==201,"bad ack skipped, fragmented TGAK accepted");
        check(reader.read(wire) && reader.audio.type==AudioFrame.INFO,"TREC after guide");
        System.out.println("PASS MIDI tempo/running status/overlap/pedal/white keys/limits and guide CRC/frame demux");
    }
}
