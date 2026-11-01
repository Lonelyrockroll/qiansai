package cn.tangsynth.recorder;
import java.io.*;
import java.nio.file.*;

/** Java encoder used by the app produces complete FPGA cross-test requests. */
public final class ScoreFixture {
    static void hex(Path path,byte[] bytes)throws Exception{
        StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format("%02x\n",b&255));Files.write(path,s.toString().getBytes("US-ASCII"));
    }
    public static void main(String[] args)throws Exception{
        Path dir=Paths.get(args[0]);Files.createDirectories(dir);
        byte[] raw=args.length>1?Files.readAllBytes(Paths.get(args[1])):ScoreTest.pattern();
        ScoreProtocol.Page page=new ScoreProtocol.Page(raw,0,2);
        ByteArrayOutputStream requests=new ByteArrayOutputStream();int seq=1,frames=0;
        requests.write(ScoreProtocol.request(seq,ScoreProtocol.BEGIN,page.begin()));frames++;
        for(int offset=0;offset<page.compressed.length;){
            byte[] chunk=page.chunk(offset);seq=seq%255+1;requests.write(ScoreProtocol.request(seq,ScoreProtocol.DATA,chunk));frames++;offset+=chunk.length-4;
        }
        seq=seq%255+1;requests.write(ScoreProtocol.request(seq,ScoreProtocol.COMMIT,new byte[0]));frames++;
        seq=seq%255+1;requests.write(ScoreProtocol.request(seq,ScoreProtocol.CONTROL,new byte[]{1}));frames++;
        hex(dir.resolve("score-raw.hex"),raw);hex(dir.resolve("score-rle.hex"),page.compressed);hex(dir.resolve("score-upload.hex"),requests.toByteArray());
        String meta="{\"raw_bytes\":65536,\"compressed_bytes\":"+page.compressed.length+",\"crc32\":"+page.crc32+",\"frames\":"+frames+",\"final_sequence\":"+seq+"}\n";
        Files.write(dir.resolve("score.json"),meta.getBytes("US-ASCII"));System.out.print(meta);
    }
}
