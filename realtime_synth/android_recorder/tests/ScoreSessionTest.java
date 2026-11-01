package cn.tangsynth.recorder;

import android.bluetooth.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.zip.CRC32;
import static cn.tangsynth.recorder.GuideSessionTest.check;
import static cn.tangsynth.recorder.GuideSessionTest.await;

/** Actual RecorderSession with dropped ACKs, interleaved protocol types and legacy peers. */
public final class ScoreSessionTest {
    static final class Feedback implements RecorderSession.Listener {
        volatile File saved;volatile String score="";
        public void status(RecorderSession s,RecorderSession.Phase p,String d,long n,int peak){}
        public void saved(RecorderSession s,File f,boolean interrupted){saved=f;}
        public void guide(RecorderSession s,GuideProtocol.Ack a,String d,boolean busy){}
        public void score(RecorderSession s,ScoreProtocol.Ack a,String d,boolean busy){score=d;}
    }
    static final class Peer implements AutoCloseable {
        final PipedInputStream fromApp=new PipedInputStream(32768),toApp=new PipedInputStream(32768);
        final PipedOutputStream appWrites,peerWrites;final Thread worker;
        final AtomicReference<Throwable> error=new AtomicReference<>();
        final boolean score,guide;final boolean drop;
        volatile int starts,binaryFrames,guideFrames,scoreFrames,received,decoded,commits,begins,shows;
        volatile boolean valid,showing,droppedData;int index,count,declared;long crc;
        byte[] last,lastAck;Set<Integer> dropped=new HashSet<>();ByteArrayOutputStream content=new ByteArrayOutputStream();
        Peer(boolean score,boolean guide,boolean drop)throws IOException{
            this.score=score;this.guide=guide;this.drop=drop;
            appWrites=new PipedOutputStream(fromApp);peerWrites=new PipedOutputStream(toApp);
            worker=new Thread(this::serve,"mock score SPP");worker.start();
        }
        BluetoothDevice device(){return new BluetoothDevice(new BluetoothSocket(toApp,appWrites));}
        synchronized void send(byte[] a)throws IOException{peerWrites.write(a);peerWrites.flush();}
        void audio(int type,long sequence)throws IOException{
            int body=type==1?74:10;byte[] a=new byte[body+6];
            a[0]='T';a[1]='R';a[2]='E';a[3]='C';a[4]=1;a[5]=(byte)type;GuideProtocol.put32(a,6,sequence);
            a[10]=(byte)(type==1?129:0);GuideProtocol.put16(a,a.length-2,GuideProtocol.crc16(a,4,a.length-2));send(a);
        }
        byte[] scoreAck(int seq,int op){return ScoreTest.reply(seq,op,0,received,index,count,(valid?1:0)|(showing?2:0),decoded);}
        void packet(byte[] request)throws Exception{
            binaryFrames++;int seq=request[3]&255,op=request[4]&255;
            check(GuideProtocol.u16(request,26)==GuideProtocol.crc16(request,2,26),"request CRC");
            if(last!=null && seq==(last[3]&255) && op==(last[4]&255)){
                check(Arrays.equals(last,request),"retry bytes changed");send(lastAck);return;
            }
            last=request.clone();
            if(op<16){check(guide,"legacy guide binary");guideFrames++;lastAck=GuideTest.reply(seq,op,0);send(lastAck);return;}
            check(score,"score binary sent to legacy board");scoreFrames++;
            if(op==17){
                begins++;declared=(int)ScoreProtocol.u32(request,6);crc=ScoreProtocol.u32(request,10);
                index=GuideProtocol.u16(request,14);count=GuideProtocol.u16(request,16);received=0;decoded=0;valid=false;showing=false;content.reset();
            }else if(op==18){
                int offset=(request[6]&255)|((request[7]&255)<<8)|((request[8]&255)<<16),n=request[9]&255;
                check(offset==received && n>0 && n<=16,"chunk ordering");content.write(request,10,n);received+=n;
            }else if(op==19){
                commits++;check(received==declared,"compressed length");byte[] raw=ScoreProtocol.decode(content.toByteArray());
                CRC32 actual=new CRC32();actual.update(raw);check(actual.getValue()==crc,"raw CRC32");decoded=raw.length;valid=true;
            }else if(op==20){
                int action=request[6]&255;
                if(action==1){shows++;showing=true;}else showing=false;
                if(action==2){valid=false;decoded=0;}
            }
            lastAck=scoreAck(seq,op);
            if(drop && (op==17 || op==18 || op==19 || op==20) && dropped.add(op)){
                if(op==18)droppedData=true;return;
            }
            send(lastAck);
        }
        void serve(){
            boolean prefix=false;
            try{while(true){int b=fromApp.read();if(b<0)break;
                if(b==0xa5){byte[] request=new byte[28];request[0]=(byte)b;new DataInputStream(fromApp).readFully(request,1,27);packet(request);prefix=false;}
                else if(prefix){prefix=false;
                    if(b=='I')audio(3,0);
                    if(b=='G' && guide)send(GuideTest.reply(0,0,0));
                    if(b=='P' && score)send(scoreAck(0,16));
                    if(b=='R'){starts++;audio(1,0);}
                    if(b=='S')audio(2,1);
                }else prefix=b=='~';
            }}catch(IOException ended){}catch(Throwable t){error.set(t);}
        }
        public void close()throws Exception{
            try{appWrites.close();peerWrites.close();fromApp.close();toApp.close();}finally{worker.join(1000);}
            if(error.get()!=null)throw new AssertionError(error.get());
        }
    }
    static void test(boolean score,boolean guide,Path dir)throws Exception{
        Feedback listener=new Feedback();ScoreProtocol.Page page=new ScoreProtocol.Page(ScoreTest.pattern(),0,2);
        try(Peer peer=new Peer(score,guide,score)){
            RecorderSession session=new RecorderSession(peer.device(),dir.toFile(),listener);session.connect();
            await(()->session.phase()==RecorderSession.Phase.READY,3000);
            if(guide)await(session::guideAvailable,3000);
            if(score){
                await(session::scoreAvailable,4000);session.uploadScore(page);await(()->peer.droppedData,6000);
                session.start();session.guideControl(GuideProtocol.NEXT);
                check(peer.starts==0 && peer.guideFrames==0,"record/guide interleaved with score upload");
                await(()->!session.guideBusy(),14000);
                check(peer.begins==1 && peer.commits==1 && peer.shows==1 && peer.valid && peer.showing,"retry repeated operation or did not commit");
                check(session.scoreState().index==0 && session.scoreState().count==2,"page metadata");
                session.scoreControl(ScoreProtocol.HIDE);await(()->!session.guideBusy(),2000);check(!peer.showing && peer.valid,"hide lost cache");
                session.scoreControl(ScoreProtocol.SHOW);await(()->!session.guideBusy(),2000);check(peer.showing,"show cache");
                session.guideControl(GuideProtocol.NEXT);await(()->!session.guideBusy(),2000);check(peer.guideFrames==1,"guide not restored after score");
            }else{
                session.uploadScore(page);Thread.sleep(80);check(peer.binaryFrames==0 && !session.scoreAvailable(),"unsafe legacy upload");
            }
            session.start();await(()->session.phase()==RecorderSession.Phase.RECORDING,2500);
            int frames=peer.binaryFrames;session.uploadScore(page);session.scoreControl(ScoreProtocol.SHOW);session.guideControl(GuideProtocol.NEXT);
            check(!session.guideBusy() && peer.binaryFrames==frames,"binary request during recording");
            session.stop();await(()->session.phase()==RecorderSession.Phase.READY,2500);
            check(listener.saved!=null && listener.saved.length()==302,"recording WAV changed");
            if(score){session.scoreControl(ScoreProtocol.CLEAR);await(()->!session.guideBusy(),2000);check(!peer.valid && !peer.showing,"clear");}
            session.leave();await(()->session.phase()==RecorderSession.Phase.CLOSED,1000);
        }
    }
    public static void main(String[] args)throws Exception{
        Path dir=Files.createTempDirectory("tang-score-session");
        try{test(true,true,dir);test(false,true,dir);test(false,false,dir);}
        finally{try(java.util.stream.Stream<Path> f=Files.list(dir)){for(Path p:(Iterable<Path>)f::iterator)Files.delete(p);}Files.delete(dir);}
        System.out.println("PASS actual score session: safe probe, identical BEGIN/DATA/COMMIT/SHOW retries, one commit, mutual exclusion, guide recovery, legacy WAV");
    }
}
