package cn.tangsynth.recorder;

import java.io.*;

final class KeyProtocol {
    static final int QUERY=24,SWAP=25,RESET=26;
    static final String[] NAMES={"C","D","E","F","G","A","B"};
    static String key(int index){return "H"+(index+1);}
    static String note(int index){return NAMES[index%7]+(2+index/7);}
    static final class Ack {
        final int sequence,operation,status,keyA,noteA,keyB,noteB;
        Ack(byte[] frame)throws IOException {
            if(frame.length!=24 || frame[0]!='T' || frame[1]!='K' || frame[2]!='A' || frame[3]!='K' || frame[4]!=1 ||
               GuideProtocol.u16(frame,22)!=GuideProtocol.crc16(frame,4,22))throw new IOException("键位回包校验失败");
            sequence=frame[5]&255;operation=frame[6]&255;status=frame[7]&255;
            keyA=frame[8]&255;noteA=frame[9]&255;keyB=frame[10]&255;noteB=frame[11]&255;
            if(operation<QUERY || operation>RESET || (status==0 && (keyA>31 || noteA>31 || keyB>31 || noteB>31)))throw new IOException("键位回包数据无效");
        }
        String describe(){
            if(operation==RESET)return "32 个琴键已恢复默认音高";
            String text=key(keyA)+"  →  "+note(noteA);
            return operation==SWAP?text+"     "+key(keyB)+"  →  "+note(noteB):text;
        }
        String error(){return status==4?"请先静音并松开所有琴键，再重试":status==3?"琴键编号超出范围":"板卡拒绝了键位命令（"+status+"）";}
    }
    static Ack readReply(InputStream in)throws IOException{
        byte[] frame=new byte[24];frame[0]='T';frame[1]='K';frame[2]='A';frame[3]='K';
        new DataInputStream(in).readFully(frame,4,20);return new Ack(frame);
    }
}
