package cn.tangsynth.recorder;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

/** TREC/1. Each block independently seeds its IMA predictor and step index. */
final class AudioFrame {
    static final int DATA = 1, END = 2, INFO = 3, RATE = 16276, SAMPLES = 129;
    private static final int[] MAGIC = {'T','R','E','C'};
    private static final int[] STEP = {7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,
        34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,
        279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,
        1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,
        7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,
        27086,29794,32767};
    private static final int[] INDEX = {-1,-1,-1,-1,2,4,6,8};
    int type, field;
    long sequence;
    final byte[] pcm = new byte[SAMPLES * 2];
    private final byte[] body = new byte[74];

    private static int next(InputStream in) throws IOException {
        int ch = in.read();
        if (ch < 0) throw new EOFException("蓝牙连接已关闭");
        return ch;
    }
    private static int crc(byte[] bytes, int length) {
        int crc = 0xffff;
        for (int i=0;i<length;i++) {
            crc ^= (bytes[i] & 255) << 8;
            for (int j=0;j<8;j++) crc = ((crc << 1) ^ ((crc & 0x8000)==0 ? 0 : 0x1021)) & 0xffff;
        }
        return crc;
    }
    private void fill(InputStream in, int from, int end) throws IOException {
        while (from < end) {
            int n=in.read(body,from,end-from);
            if (n<0) throw new EOFException("蓝牙音频帧不完整");
            from+=n;
        }
    }
    void read(InputStream in) throws IOException {
        // Legacy console greetings can precede the first binary frame.
        for (int matched=0;matched<4;) {
            int b=next(in);
            matched=b==MAGIC[matched]? matched+1 : b==MAGIC[0]?1:0;
        }
        readBody(in);
    }
    void readBody(InputStream in) throws IOException {
        fill(in,0,10);
        type=body[1]&255;
        int count=body[6]&255;
        if (body[0]!=1 || type<DATA || type>INFO || count!=(type==DATA?SAMPLES:0))
            throw new IOException("不兼容的录音帧");
        int length=type==DATA?74:10;
        fill(in,10,length);
        int low=next(in),high=next(in);
        if ((low|(high<<8))!=crc(body,length)) throw new IOException("录音数据校验失败");
        sequence=(body[2]&255L)|((body[3]&255L)<<8)|((body[4]&255L)<<16)|((body[5]&255L)<<24);
        field=body[9]&255;
        if(type!=DATA)return;
        if(field>88)throw new IOException("ADPCM 索引无效");
        int predictor=(short)((body[7]&255)|((body[8]&255)<<8)),index=field;
        pcm[0]=(byte)predictor;pcm[1]=(byte)(predictor>>8);
        for (int i=0;i<SAMPLES-1;i++) {
            int nibble=((body[10+i/2]&255) >> ((i&1)*4))&15;
            int step=STEP[index],delta=step>>3;
            if((nibble&4)!=0)delta+=step;
            if((nibble&2)!=0)delta+=step>>1;
            if((nibble&1)!=0)delta+=step>>2;
            predictor=Math.max(-32768,Math.min(32767,predictor+((nibble&8)==0?delta:-delta)));
            index=Math.max(0,Math.min(88,index+INDEX[nibble&7]));
            pcm[2*i+2]=(byte)predictor;pcm[2*i+3]=(byte)(predictor>>8);
        }
    }
}
