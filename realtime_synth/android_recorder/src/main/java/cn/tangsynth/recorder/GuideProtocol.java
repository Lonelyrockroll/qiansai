package cn.tangsynth.recorder;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

/** TGAK/1 replies share the SPP byte stream with TREC recording frames. */
final class GuideProtocol {
    static final int STATUS=0, BEGIN=1, WRITE=2, COMMIT=3, CONTROL=4;
    static final int STOP=0, PLAY=1, PAUSE=2, RESTART=3, TOGGLE=4, NEXT=5, PREVIOUS=6, DEMO=7, SPEED=8;
    static final int CAPACITY=512;

    static int crc16(byte[] a,int start,int end) {
        int c=0xffff;
        for(int i=start;i<end;i++){
            c^=(a[i]&255)<<8;
            for(int b=0;b<8;b++)c=((c<<1)^((c&0x8000)!=0?0x1021:0))&0xffff;
        }
        return c;
    }
    static void put16(byte[] a,int pos,int value){a[pos]=(byte)value;a[pos+1]=(byte)(value>>8);}
    static void put32(byte[] a,int pos,long value){for(int i=0;i<4;i++)a[pos+i]=(byte)(value>>(8*i));}
    static int u16(byte[] a,int pos){return (a[pos]&255)|((a[pos+1]&255)<<8);}
    static byte[] request(int seq,int operation,byte[] payload){
        if(payload.length>20 || operation<0 || operation>4)throw new IllegalArgumentException("指引帧参数超限");
        byte[] frame=new byte[28];
        frame[0]=(byte)0xa5;frame[1]=0x47;frame[2]=1;frame[3]=(byte)seq;frame[4]=(byte)operation;frame[5]=(byte)payload.length;
        System.arraycopy(payload,0,frame,6,payload.length);
        put16(frame,26,crc16(frame,2,26));
        return frame;
    }
    static final class Ack {
        final int sequence,operation,status,received,count,timeCs,durationCs,flags,speed,index;
        Ack(byte[] f)throws IOException {
            if(f.length!=24 || f[0]!='T'||f[1]!='G'||f[2]!='A'||f[3]!='K'||f[4]!=1 ||
               u16(f,22)!=crc16(f,4,22))throw new IOException("指引回包校验失败");
            sequence=f[5]&255;operation=f[6]&255;status=f[7]&255;
            received=u16(f,8);count=u16(f,10);timeCs=u16(f,12);durationCs=u16(f,14);
            flags=f[16]&255;speed=f[17]&255;index=u16(f,18);
        }
        boolean valid(){return (flags&1)!=0;}
        boolean playing(){return (flags&2)!=0;}
        boolean demo(){return (flags&8)!=0;}
        String description(){
            String title=demo()?"板载示范曲":"已传入曲目";
            String state=playing()?"播放中":valid()?"已暂停 / 就绪":"尚无曲目";
            int rate=speed==0?50:speed==1?75:speed==3?125:100;
            return title+" · "+state+" · "+timeCs/100+" / "+durationCs/100+" 秒 · "+rate+"%";
        }
        String error(){
            switch(status){
                case 1:return "指引数据校验失败";
                case 2:return "板卡不支持这条指引命令";
                case 3:return "曲目数据或参数不符合要求";
                case 4:return "板卡忙，请先停止录音或等待当前操作完成";
                case 5:return "上传顺序或曲目状态不匹配，请重新发送";
                default:return "指引操作失败（"+status+"）";
            }
        }
    }
    /** Consume after the TGAK signature has already been read by StreamReader. */
    static Ack readReply(InputStream in)throws IOException{
        byte[] f=new byte[24];f[0]='T';f[1]='G';f[2]='A';f[3]='K';
        int pos=4;
        while(pos<f.length){
            int n=in.read(f,pos,f.length-pos);
            if(n<0)throw new EOFException("指引回包不完整");
            pos+=n;
        }
        return new Ack(f);
    }
}
