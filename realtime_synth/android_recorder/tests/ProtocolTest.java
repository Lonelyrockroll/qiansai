package cn.tangsynth.recorder;
import java.io.*;
import java.nio.file.*;
import java.util.Arrays;

/** Desktop JVM uses the same parser/writer as Android; input is the FPGA UART simulation. */
public final class ProtocolTest {
    static final class Fragmented extends ByteArrayInputStream {
        Fragmented(byte[] buf){super(buf);}
        @Override public synchronized int read(byte[] b,int off,int len){return super.read(b,off,Math.min(len,3));}
    }
    static void check(boolean ok){if(!ok)throw new AssertionError();}
    public static void main(String[] argv)throws Exception{
        Path sim=Paths.get(argv[0]);
        byte[] wire=Files.readAllBytes(sim.resolve("record_wire.bin")), golden=Files.readAllBytes(sim.resolve("record_ref.pcm"));
        Fragmented input=new Fragmented(wire);
        Path dir=Files.createTempDirectory("tang-wav-test");
        try{
            AudioFrame f=new AudioFrame();f.read(input);check(f.type==AudioFrame.INFO);
            int offset=0;
            for(int take=0;take<2;take++){
                WavTake w=new WavTake(dir.toFile());WavTake.recover(dir.toFile());
                int start=offset;f.read(input);
                while(f.type==AudioFrame.DATA){
                    check(Arrays.equals(f.pcm,Arrays.copyOfRange(golden,offset,offset+f.pcm.length)));
                    w.append(f);offset+=f.pcm.length;f.read(input);
                }
                check(f.type==AudioFrame.END && f.sequence==w.blocks && f.field==take);
                File wave=w.finish(take==1);byte[] data=Files.readAllBytes(wave.toPath());
                check(wave.getName().contains("中断")== (take==1));
                check(data.length==44+offset-start && Arrays.equals(Arrays.copyOfRange(data,44,data.length),Arrays.copyOfRange(golden,start,offset)));
                check(new String(data,0,4,"US-ASCII").equals("RIFF") && new String(data,8,4,"US-ASCII").equals("WAVE"));
                check((data[24]&255)+((data[25]&255)<<8)==AudioFrame.RATE && data[22]==1 && data[34]==16);
            }
            check(offset==golden.length);
            byte[] bad=Arrays.copyOfRange(wire,40,120);bad[38]^=1;
            try{f.read(new Fragmented(bad));throw new AssertionError("accepted bad CRC");}catch(IOException expected){}
            try{f.read(new Fragmented(Arrays.copyOf(bad,21)));throw new AssertionError("accepted cutoff");}catch(EOFException expected){}
            WavTake missing=new WavTake(dir.toFile());f.sequence=1;
            try{missing.append(f);throw new AssertionError("accepted missing block");}catch(IOException expected){}
            check(missing.finish(true)==null);
            Path orphan=dir.resolve("orphan.part");Files.write(orphan,new byte[44+258+10]);
            WavTake.recover(dir.toFile());check(Files.size(dir.resolve("orphan-中断.wav"))==44+258);
            System.out.println("PASS Android decoder: fragmented frames, CRC, sequence, both WAVs, interrupted/process-death recovery");
        }finally{try(java.util.stream.Stream<Path> files=Files.list(dir)){for(Path p:(Iterable<Path>)files::iterator)Files.delete(p);}Files.delete(dir);}
    }
}
