package cn.tangsynth.recorder;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Set;
import java.util.Locale;

/** One private temporary file. Only verified, consecutive frames are appended. */
final class WavTake {
    static final long MAX_SAMPLES=600L*AudioFrame.RATE;
    private static final Set<File> OPEN=new HashSet<>();
    private final File part;
    private final RandomAccessFile out;
    long blocks;
    WavTake(File directory) throws IOException {
        if(!directory.isDirectory() && !directory.mkdirs())throw new IOException("无法创建录音目录");
        if(directory.getUsableSpace()<1024*1024)throw new IOException("手机存储空间不足");
        String prefix=new SimpleDateFormat("yyyyMMdd-HHmmss-SSS",Locale.US).format(new Date());
        synchronized(OPEN){
            part=File.createTempFile("Tang-"+prefix+"-", ".part",directory);
            out=new RandomAccessFile(part,"rw");
            try{out.write(new byte[44]);OPEN.add(part);}
            catch(IOException ex){out.close();throw ex;}
        }
    }
    void append(AudioFrame frame) throws IOException {
        if(frame.sequence!=blocks)throw new IOException("录音序号不连续，预期 "+blocks+"，收到 "+frame.sequence);
        if((blocks&127)==0 && part.getParentFile().getUsableSpace()<1024*1024)throw new IOException("手机存储空间不足");
        out.write(frame.pcm);blocks++;
    }
    private static void le(RandomAccessFile f,int n,int bytes) throws IOException {
        for(int i=0;i<bytes;i++)f.write((n>>>(i*8))&255);
    }
    private static void header(RandomAccessFile f,int bytes) throws IOException {
        f.seek(0);f.writeBytes("RIFF");le(f,36+bytes,4);f.writeBytes("WAVEfmt ");
        le(f,16,4);le(f,1,2);le(f,1,2);le(f,AudioFrame.RATE,4);
        le(f,AudioFrame.RATE*2,4);le(f,2,2);le(f,16,2);f.writeBytes("data");le(f,bytes,4);
    }
    private static File publish(File part,boolean partial) throws IOException {
        String name=part.getName().replaceFirst("\\.part$",partial?"-中断.wav":".wav");
        File finalFile=new File(part.getParentFile(),name);
        if(!part.renameTo(finalFile))throw new IOException("录音尚未归档，可在下次启动时恢复");
        return finalFile;
    }
    File finish(boolean partial) throws IOException {
        int bytes=(int)(blocks*AudioFrame.SAMPLES*2);
        synchronized(OPEN){
            try {
                try {out.setLength(44L+bytes);header(out,bytes);} finally {out.close();}
                if(bytes==0){if(!part.delete())throw new IOException("无法清理空录音");return null;}
                return publish(part,partial);
            } finally {OPEN.remove(part);}
        }
    }
    static void recover(File dir) throws IOException {
        synchronized(OPEN){recoverClosed(dir);}
    }
    private static void recoverClosed(File dir) throws IOException {
        File[] parts=dir.listFiles((d,n)->n.endsWith(".part"));
        if(parts==null)return;
        for(File p:parts) {
            if(OPEN.contains(p))continue;
            long bytes=Math.max(0,p.length()-44);
            bytes-=bytes%(AudioFrame.SAMPLES*2);
            if(bytes==0){if(!p.delete())throw new IOException("无法清理未完成文件");continue;}
            if(bytes>Integer.MAX_VALUE-44)throw new IOException("未完成录音长度异常");
            try(RandomAccessFile f=new RandomAccessFile(p,"rw")){f.setLength(44+bytes);header(f,(int)bytes);}
            publish(p,true);
        }
    }
}
