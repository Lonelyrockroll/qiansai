package cn.tangsynth.recorder;

import android.bluetooth.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import java.util.zip.CRC32;

/** Exercises the actual session using in-process SPP streams and small Android API stand-ins. */
public final class GuideSessionTest {
    static void check(boolean value,String detail){if(!value)throw new AssertionError(detail);}
    static void await(BooleanSupplier ready,long ms)throws Exception{
        long end=System.nanoTime()+ms*1_000_000;
        while(!ready.getAsBoolean()){if(System.nanoTime()>end)throw new AssertionError("session timeout");Thread.sleep(8);}
    }
    static final class Feedback implements RecorderSession.Listener {
        volatile String guide="";volatile File saved;
        public void status(RecorderSession s,RecorderSession.Phase p,String d,long n,int peak){}
        public void saved(RecorderSession s,File f,boolean p){saved=f;}
        public void guide(RecorderSession s,GuideProtocol.Ack a,String d,boolean b){guide=d;}
    }
    static final class Peer implements AutoCloseable {
        final PipedInputStream fromApp=new PipedInputStream(32768),toApp=new PipedInputStream(32768);
        final PipedOutputStream appWrites,peerWrites;
        final AtomicReference<Throwable> error=new AtomicReference<>();
        final Thread worker;final boolean guide;
        volatile int received,declared,active=84,toggles,starts,binaryFrames;
        volatile boolean droppedWrite,droppedToggle;
        long expectedCrc;ByteArrayOutputStream content=new ByteArrayOutputStream();byte[] last;
        Peer(boolean capability)throws IOException{
            guide=capability;appWrites=new PipedOutputStream(fromApp);peerWrites=new PipedOutputStream(toApp);
            worker=new Thread(this::serve,"mock FPGA SPP");worker.start();
        }
        BluetoothDevice device(){return new BluetoothDevice(new BluetoothSocket(toApp,appWrites));}
        synchronized void send(byte[] b)throws IOException{peerWrites.write(b);peerWrites.flush();}
        void audio(int type,long sequence)throws IOException{
            int body=type==1?74:10;byte[] a=new byte[body+6];
            a[0]='T';a[1]='R';a[2]='E';a[3]='C';a[4]=1;a[5]=(byte)type;GuideProtocol.put32(a,6,sequence);
            a[10]=(byte)(type==1?129:0);GuideProtocol.put16(a,a.length-2,GuideProtocol.crc16(a,4,a.length-2));send(a);
        }
        void ack(int seq,int operation)throws IOException{
            byte[] a=GuideTest.reply(seq,operation,0);
            GuideProtocol.put16(a,8,received);GuideProtocol.put16(a,10,active);
            GuideProtocol.put16(a,22,GuideProtocol.crc16(a,4,22));send(a);
        }
        void packet(byte[] request)throws Exception{
            binaryFrames++;check(guide,"binary guide data was sent to old firmware");
            check(GuideProtocol.u16(request,26)==GuideProtocol.crc16(request,2,26),"invalid request CRC");
            int seq=request[3]&255,op=request[4]&255;
            if(last!=null && seq==(last[3]&255) && op==(last[4]&255)){
                check(Arrays.equals(last,request),"retry changed bytes");
                ack(seq,op);return;
            }
            last=request.clone();
            if(op==1){
                declared=GuideProtocol.u16(request,6);received=0;content.reset();
                expectedCrc=((long)GuideProtocol.u16(request,12)<<16)|GuideProtocol.u16(request,10);
            }else if(op==2){
                int offset=GuideProtocol.u16(request,6),n=request[8]&255;
                check(offset==received && n>0 && n<=4,"wrong chunk");
                content.write(request,9,n*4);received+=n;
                if(!droppedWrite){droppedWrite=true;return;}
            }else if(op==3){
                CRC32 crc=new CRC32();crc.update(content.toByteArray());
                check(received==declared && crc.getValue()==expectedCrc,"bad committed score");
                active=received;
            }else if(op==4 && request[6]==4){
                toggles++;if(!droppedToggle){droppedToggle=true;return;}
            }
            ack(seq,op);
        }
        void serve(){
            boolean prefix=false;
            try{
                while(true){
                    int b=fromApp.read();if(b<0)break;
                    if(b==0xa5){
                        byte[] request=new byte[28];request[0]=(byte)b;
                        new DataInputStream(fromApp).readFully(request,1,27);packet(request);prefix=false;
                    }else if(prefix){
                        prefix=false;
                        if(b=='I')audio(3,0);
                        if(b=='G' && guide)ack(0,0);
                        if(b=='R'){starts++;audio(1,0);}
                        if(b=='S')audio(2,1);
                    }else prefix=b=='~';
                }
            }catch(IOException expected){}
            catch(Throwable t){error.set(t);}
        }
        public void close()throws Exception{
            try{appWrites.close();peerWrites.close();fromApp.close();toApp.close();}finally{worker.join(1000);}
            if(error.get()!=null)throw new AssertionError(error.get());
        }
    }
    static void test(boolean modern,Path dir,MidiGuide.Compiled song)throws Exception{
        Feedback listener=new Feedback();
        try(Peer peer=new Peer(modern)){
            RecorderSession session=new RecorderSession(peer.device(),dir.toFile(),listener);
            session.connect();await(()->session.phase()==RecorderSession.Phase.READY,3000);
            if(modern){
                await(session::guideAvailable,3000);
                session.uploadGuide(song);await(()->peer.droppedWrite,3000);
                session.start();check(peer.starts==0 && session.phase()==RecorderSession.Phase.READY,"recording started during guide transfer");
                await(()->!session.guideBusy(),7000);
                check(peer.received==song.words.length && peer.active==song.words.length,"song did not commit");
                session.guideControl(GuideProtocol.TOGGLE);await(()->!session.guideBusy(),6000);
                check(peer.toggles==1,"retry toggled playback twice");
            }else{
                session.uploadGuide(song);Thread.sleep(80);
                check(peer.binaryFrames==0 && !session.guideAvailable(),"unsafe legacy upload");
            }
            session.start();await(()->session.phase()==RecorderSession.Phase.RECORDING,2500);
            session.guideControl(GuideProtocol.NEXT);check(!session.guideBusy(),"guide command entered recording stream");
            session.stop();await(()->session.phase()==RecorderSession.Phase.READY,2500);
            check(listener.saved!=null && listener.saved.length()==44+258,"old recording path damaged");
            session.leave();await(()->session.phase()==RecorderSession.Phase.CLOSED,1000);
        }
    }
    public static void main(String[] args)throws Exception{
        Path dir=Files.createTempDirectory("tang-guide-session");
        MidiGuide.Compiled song=MidiGuide.compile(MidiGuide.parse(Files.readAllBytes(Paths.get(args[0]))),0);
        try{test(true,dir,song);test(false,dir,song);}
        finally{try(java.util.stream.Stream<Path> f=Files.list(dir)){for(Path p:(Iterable<Path>)f::iterator)Files.delete(p);}Files.delete(dir);}
        System.out.println("PASS actual session: safe capability probe, identical retries, single commit/toggle, recording exclusion and legacy WAV");
    }
}
