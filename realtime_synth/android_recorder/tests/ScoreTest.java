package cn.tangsynth.recorder;
import java.io.*;
import java.util.*;

public final class ScoreTest {
    static void check(boolean v,String s){if(!v)throw new AssertionError(s);}
    static byte[] reply(int seq,int op,int status,int received,int index,int count,int flags,int decoded){
        byte[] a=new byte[24];a[0]='T';a[1]='P';a[2]='A';a[3]='K';a[4]=1;a[5]=(byte)seq;a[6]=(byte)op;a[7]=(byte)status;
        GuideProtocol.put32(a,8,received);GuideProtocol.put16(a,12,index);GuideProtocol.put16(a,14,count);a[16]=(byte)flags;
        GuideProtocol.put32(a,18,decoded);GuideProtocol.put16(a,22,GuideProtocol.crc16(a,4,22));return a;
    }
    static byte[] pattern(){
        byte[] raw=new byte[65536];
        for(int y=20;y<492;y++)for(int x=32;x<992;x++){
            boolean line=y%70>=20 && y%70<=24;
            boolean note=(x%120>=45 && x%120<60 && y%70>=10 && y%70<40);
            if(line || note)raw[y*128+(x>>3)]|=(byte)(128>>(x&7));
        }
        return raw;
    }
    public static void main(String[] args)throws Exception{
        byte[][] cases={new byte[65536],new byte[65536],new byte[65536],pattern()};
        Arrays.fill(cases[1],(byte)255);new Random(391).nextBytes(cases[2]);
        for(byte[] raw:cases){byte[] compressed=ScoreProtocol.encode(raw);check(Arrays.equals(raw,ScoreProtocol.decode(compressed)),"RLE roundtrip");check(compressed.length<=131072,"RLE bound");}
        check(ScoreProtocol.encode(cases[0]).length==516,"255 maximum runs");
        int[] pixels=new int[1024*512];Arrays.fill(pixels,0xffffffff);pixels[0]=0xff000000;pixels[7]=0xff000000;pixels[8]=0xff000000;pixels[9]=0x00000000;
        byte[] raw=ScoreProtocol.monochrome(pixels);check((raw[0]&255)==0x81 && (raw[1]&255)==0x80,"MSB, white and transparent pixels");
        for(byte[] invalid:new byte[][]{{0,0},{1,0},{1},{(byte)255,0,1}}){try{ScoreProtocol.decode(invalid);throw new AssertionError("accepted invalid RLE");}catch(IOException good){}}
        ScoreProtocol.Page page=new ScoreProtocol.Page(pattern(),1,2);byte[] begin=page.begin();
        check(ScoreProtocol.u32(begin,0)==page.compressed.length && GuideProtocol.u16(begin,12)==1024 && GuideProtocol.u16(begin,14)==512,"BEGIN fields");
        byte[] request=ScoreProtocol.request(255,17,begin);check(request.length==28 && GuideProtocol.u16(request,26)==GuideProtocol.crc16(request,2,26),"frame CRC");
        ScoreProtocol.Ack ack=new ScoreProtocol.Ack(reply(25,19,0,131072,1,2,3,65536));
        check(ack.valid() && ack.showing() && ack.received==131072 && ack.decoded==65536,"TPAK uint32 fields");
        ByteArrayOutputStream mixed=new ByteArrayOutputStream();mixed.write("OK hello\r\n".getBytes("US-ASCII"));
        mixed.write(GuideTest.reply(1,0,0));mixed.write(reply(2,16,0,0,0,0,0,0));mixed.write(GuideTest.reply(3,4,0));
        byte[] bad=reply(5,20,0,0,0,0,0,0);bad[22]^=1;mixed.write(bad);mixed.write(reply(4,20,0,0,0,0,0,0));
        StreamReader reader=new StreamReader();InputStream wire=new ProtocolTest.Fragmented(mixed.toByteArray());
        check(!reader.read(wire) && reader.acknowledgement.sequence==1 && reader.scoreAcknowledgement==null,"TGAK demux");
        check(!reader.read(wire) && reader.scoreAcknowledgement.sequence==2 && reader.acknowledgement==null,"TPAK demux");
        check(!reader.read(wire) && reader.acknowledgement.sequence==3 && reader.scoreAcknowledgement==null,"TGAK reset");
        check(!reader.read(wire) && reader.scoreAcknowledgement.sequence==4,"damaged ACK skipped");
        System.out.println("PASS score: raw RLE worst-case/zero/255/random, monochrome MSB/transparency, metadata/CRC, fragmented TPAK/TGAK demux");
    }
}
