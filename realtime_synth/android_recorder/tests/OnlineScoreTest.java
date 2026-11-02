package cn.tangsynth.recorder;

import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.security.MessageDigest;

/** Exercise the same bounded download and validated importer used by the activity. */
public final class OnlineScoreTest {
    static final String LINK="https://scores.example/a.pdf";
    static final byte[] PDF="%PDF-1.4\nfixture".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    static class Reply extends HttpURLConnection {
        final byte[] data;final Map<String,String> headers=new HashMap<>();boolean closed;
        Reply(int code,byte[] data)throws Exception {super(new URL(LINK));responseCode=code;this.data=data;}
        public void connect(){} public boolean usingProxy(){return false;} public void disconnect(){closed=true;}
        public int getResponseCode(){return responseCode;}
        public InputStream getInputStream(){return new ByteArrayInputStream(data);}
        public String getHeaderField(String name){return headers.get(name);}
    }
    interface Operation{void run()throws Exception;}
    static void fail(Operation operation)throws Exception{
        try{operation.run();}catch(IOException expected){return;}throw new AssertionError("expected download rejection");
    }
    static void check(boolean value,String why){if(!value)throw new AssertionError(why);}
    static void offline(Path folder)throws Exception{
        File saved=folder.resolve("remembered.pdf").toFile();byte[] old="previous valid score".getBytes();Files.write(saved.toPath(),old);
        OnlineScore.Importer importer=(f,name)->Files.copy(f.toPath(),saved.toPath(),StandardCopyOption.REPLACE_EXISTING);
        OnlineScore.Kind kind=OnlineScore.Kind.PDF;
        for(String bad:new String[]{"http://scores.example/a.pdf","file:///a.pdf","https://a:p@scores.example/a.pdf","not a URL"})
            fail(()->OnlineScore.fetch(bad,kind,folder.toFile(),importer,url->{throw new AssertionError("invalid URL opened");}));
        Reply redirect=new Reply(302,null);redirect.headers.put("Location","http://scores.example/insecure");
        fail(()->OnlineScore.fetch(LINK,kind,folder.toFile(),importer,url->redirect));check(redirect.closed,"redirect closed");
        Reply cycle=new Reply(301,null);cycle.headers.put("Location","/a.pdf");int[] requests={0};
        fail(()->OnlineScore.fetch(LINK,kind,folder.toFile(),importer,url->{requests[0]++;return cycle;}));check(requests[0]==4,"redirect cap");
        Reply large=new Reply(200,PDF);large.headers.put("Content-Length","20971521");
        Reply truncated=new Reply(200,PDF);truncated.headers.put("Content-Length","80");
        for(Reply bad:new Reply[]{large,truncated,new Reply(404,new byte[0]),new Reply(200,"<html>".getBytes())}){
            fail(()->OnlineScore.fetch(LINK,kind,folder.toFile(),importer,url->bad));check(bad.closed,"failed connection leaked");
        }
        Reply tooMany=new Reply(200,new byte[MidiGuide.MAX_BYTES+1]);
        fail(()->OnlineScore.fetch(LINK,OnlineScore.Kind.MIDI,folder.toFile(),importer,url->tooMany));
        Reply invalidPdf=new Reply(200,PDF);
        fail(()->OnlineScore.fetch(LINK,kind,folder.toFile(),(f,n)->{throw new IOException("renderer rejected invalid file");},u->invalidPdf));
        check(Arrays.equals(old,Files.readAllBytes(saved.toPath())),"failed import replaced previous file");
        check(folder.toFile().list().length==1,"temporary files survived a failure");
        Reply moved=new Reply(307,null);moved.headers.put("Location","right/file.pdf");Reply success=new Reply(200,PDF);
        OnlineScore.fetch(LINK,kind,folder.toFile(),(f,n)->{check(n.equals("file.pdf"),"URL basename");importer.importFile(f,n);},
                u->u.getPath().equals("/right/file.pdf")?success:moved);
        check(success.closed && moved.closed && Arrays.equals(PDF,Files.readAllBytes(saved.toPath())),"successful redirect/import");
        System.out.println("PASS HTTPS-only, redirect bounds/downgrade, HTTP errors, capped/truncated/incorrect content, prior score preservation and cleanup");
    }
    static void live(Path dir)throws Exception{
        for(OnlineScore.Kind kind:OnlineScore.Kind.values())OnlineScore.fetch(OnlineScore.example(kind),kind,dir.toFile(),(f,title)->{
            byte[] bytes=Files.readAllBytes(f.toPath());String extra="";
            if(kind==OnlineScore.Kind.MIDI){MidiGuide.Song song=MidiGuide.parse(bytes);check(!song.musicalTracks().isEmpty(),"online MIDI contained no notes");
                MidiGuide.Compiled c=MidiGuide.compile(song,song.musicalTracks().get(0).index);extra=" guide_events="+c.words.length;}
            try{StringBuilder hash=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))hash.append(String.format("%02x",b&255));
                System.out.println("PASS live HTTPS "+title+" bytes="+bytes.length+" SHA256="+hash+extra);
            }catch(java.security.NoSuchAlgorithmException e){throw new AssertionError(e);}
        });
    }
    public static void main(String[] args)throws Exception{
        Path dir=Files.createTempDirectory("tang-online-");
        try{offline(dir);if(Arrays.asList(args).contains("--live"))live(dir);}
        finally{try(java.util.stream.Stream<Path> files=Files.list(dir)){for(Path p:(Iterable<Path>)files::iterator)Files.deleteIfExists(p);}Files.delete(dir);}
    }
}
