package cn.tangsynth.recorder;

import java.io.*;
import java.util.zip.CRC32;

/** One monochrome page, black=1 and leftmost pixel=MSB, with byte-run compression. */
final class ScoreProtocol {
    static final int STATUS=16,BEGIN=17,DATA=18,COMMIT=19,CONTROL=20;
    static final int HIDE=0,SHOW=1,CLEAR=2,WIDTH=1024,HEIGHT=512,RAW_BYTES=65536;
    static long u32(byte[] a,int p){return (a[p]&255L)|((a[p+1]&255L)<<8)|((a[p+2]&255L)<<16)|((a[p+3]&255L)<<24);}
    static byte[] request(int sequence,int operation,byte[] payload){
        if(operation<STATUS || operation>CONTROL)throw new IllegalArgumentException("曲谱命令无效");
        return GuideProtocol.frame(sequence,operation,payload);
    }
    static final class Page {
        final byte[] compressed;
        final long crc32;
        final int index,count;
        Page(byte[] raw,int index,int count){
            if(raw.length!=RAW_BYTES || count<1 || count>65535 || index<0 || index>=count)throw new IllegalArgumentException("曲谱页面无效");
            this.index=index;this.count=count;
            CRC32 crc=new CRC32();crc.update(raw);crc32=crc.getValue();
            compressed=encode(raw);
        }
        byte[] begin(){
            byte[] p=new byte[16];GuideProtocol.put32(p,0,compressed.length);GuideProtocol.put32(p,4,crc32);
            GuideProtocol.put16(p,8,index);GuideProtocol.put16(p,10,count);
            GuideProtocol.put16(p,12,WIDTH);GuideProtocol.put16(p,14,HEIGHT);return p;
        }
        byte[] chunk(int offset){
            if(offset<0 || offset>=compressed.length)throw new IllegalArgumentException("页面分包位置无效");
            int n=Math.min(16,compressed.length-offset);byte[] p=new byte[4+n];
            p[0]=(byte)offset;p[1]=(byte)(offset>>8);p[2]=(byte)(offset>>16);p[3]=(byte)n;
            System.arraycopy(compressed,offset,p,4,n);return p;
        }
    }
    static byte[] encode(byte[] raw){
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        for(int i=0;i<raw.length;){int n=1;while(n<255 && i+n<raw.length && raw[i+n]==raw[i])n++;
            out.write(n);out.write(raw[i]);i+=n;}
        return out.toByteArray();
    }
    static byte[] decode(byte[] data)throws IOException{
        if(data.length<2 || (data.length&1)!=0)throw new IOException("曲谱压缩数据不完整");
        byte[] raw=new byte[RAW_BYTES];int offset=0;
        for(int i=0;i<data.length;i+=2){int n=data[i]&255;
            if(n==0 || offset+n>raw.length)throw new IOException("曲谱压缩长度无效");
            java.util.Arrays.fill(raw,offset,offset+n,data[i+1]);offset+=n;}
        if(offset!=raw.length)throw new IOException("曲谱页面不完整");return raw;
    }
    static byte[] monochrome(int[] argb){
        if(argb.length!=WIDTH*HEIGHT)throw new IllegalArgumentException("曲谱尺寸无效");
        byte[] raw=new byte[RAW_BYTES];
        for(int i=0;i<argb.length;i++){
            int p=argb[i],alpha=p>>>24;
            int luminance=(((p>>16)&255)*77+((p>>8)&255)*150+(p&255)*29)>>8;
            luminance=(luminance*alpha+255*(255-alpha))/255;
            if(luminance<180)raw[i>>3]|=(byte)(128>>(i&7));
        }
        return raw;
    }
    static final class Ack {
        final int sequence,operation,status,index,count,flags;
        final long received,decoded;
        Ack(byte[] f)throws IOException{
            if(f.length!=24 || f[0]!='T'||f[1]!='P'||f[2]!='A'||f[3]!='K'||f[4]!=1 ||
               GuideProtocol.u16(f,22)!=GuideProtocol.crc16(f,4,22))throw new IOException("曲谱回包校验失败");
            sequence=f[5]&255;operation=f[6]&255;status=f[7]&255;received=u32(f,8);
            index=GuideProtocol.u16(f,12);count=GuideProtocol.u16(f,14);flags=f[16]&255;decoded=u32(f,18);
        }
        boolean valid(){return (flags&1)!=0;}
        boolean showing(){return (flags&2)!=0;}
        String description(){return !valid()?"尚未传入曲谱":(showing()?"屏幕正在显示":"曲谱已隐藏")+" · 第 "+(index+1)+" / "+count+" 页";}
        String error(){switch(status){
            case 1:return "曲谱校验失败，请重新发送这一页";
            case 2:return "当前板卡不支持这条曲谱操作";
            case 3:return "曲谱页面或格式不符合要求";
            case 4:return "板卡正在采集，请结束采集后重试";
            case 5:return "页面传输中断，请重新发送这一页";
            default:return "曲谱操作失败（"+status+"）";
        }}
    }
    static Ack readReply(InputStream in)throws IOException{
        byte[] f=new byte[24];f[0]='T';f[1]='P';f[2]='A';f[3]='K';int pos=4;
        while(pos<f.length){int n=in.read(f,pos,f.length-pos);if(n<0)throw new EOFException("曲谱回包不完整");pos+=n;}
        return new Ack(f);
    }
}
