package cn.tangsynth.recorder;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import static cn.tangsynth.recorder.GuideSessionTest.check;
import static cn.tangsynth.recorder.GuideSessionTest.await;

/** Run the app's real socket session, losing one post-swap reply and exercising v31 fallback. */
public final class KeySessionTest {
    static final class Feedback implements RecorderSession.Listener {
        volatile String detail="";volatile KeyProtocol.Ack ack;
        public void status(RecorderSession s,RecorderSession.Phase p,String d,long n,int peak){}
        public void saved(RecorderSession s,File f,boolean i){}
        public void guide(RecorderSession s,GuideProtocol.Ack a,String d,boolean busy){}
        public void keys(RecorderSession s,KeyProtocol.Ack a,String d,boolean busy){detail=d;ack=a;}
    }
    static final class Peer extends ScoreSessionTest.Peer {
        final boolean supported;final int[] map=new int[32];volatile boolean dropped,retry,busy;
        volatile int swaps,keyFrames;long lostAt;
        Peer(boolean supported)throws IOException{super(true,true,false);this.supported=supported;resetMap();}
        void resetMap(){for(int i=0;i<32;i++)map[i]=i;}
        byte[] reply(int seq,int op,int status,int a,int b){
            byte[] f=new byte[24];f[0]='T';f[1]='K';f[2]='A';f[3]='K';f[4]=1;f[5]=(byte)seq;f[6]=(byte)op;f[7]=(byte)status;
            f[8]=(byte)a;f[9]=(byte)map[a];f[10]=(byte)b;f[11]=(byte)map[b];GuideProtocol.put16(f,22,GuideProtocol.crc16(f,4,22));return f;
        }
        @Override void keyProbe()throws IOException{if(supported)send(reply(0,24,0,0,0));}
        @Override void packet(byte[] req)throws Exception{
            int seq=req[3]&255,op=req[4]&255;
            if(op<24){super.packet(req);return;}
            check(supported,"sent binary keys to unsupported v31");keyFrames++;binaryFrames++;
            check(GuideProtocol.u16(req,26)==GuideProtocol.crc16(req,2,26),"key request CRC");
            if(last!=null && (last[3]&255)==seq && (last[4]&255)==op){check(Arrays.equals(last,req),"changed retry");
                check(System.nanoTime()-lostAt>=1_400_000_000L,"wrong reply family prematurely completed wait");retry=true;send(lastAck);return;}
            int a=req[6]&255,b=req[7]&255;
            check(req[5]==(op==24?1:op==25?2:0) && a<32 && b<32,"payload");last=req.clone();
            int status=busy && op!=24?4:0;
            if(status==0 && op==25){int save=map[a];map[a]=map[b];map[b]=save;swaps++;}
            if(status==0 && op==26)resetMap();
            lastAck=reply(seq,op,status,a,b);
            if(op==25 && status==0 && !dropped){dropped=true;lostAt=System.nanoTime();send(GuideTest.reply(seq,op,0));return;}
            send(lastAck);
        }
    }
    static void run(boolean supported,Path dir)throws Exception{
        Feedback ui=new Feedback();
        try(Peer peer=new Peer(supported)){
            RecorderSession s=new RecorderSession(peer.device(),dir.toFile(),ui);s.connect();
            await(()->s.scoreAvailable() && s.guideAvailable(),5000);
            if(supported){
                await(s::keyAvailable,4500);
                s.keys(25,14,15);await(()->peer.dropped,1000);
                s.start();s.scoreControl(ScoreProtocol.SHOW);s.guideControl(GuideProtocol.TOGGLE);
                await(()->!s.guideBusy() && ui.ack!=null && ui.ack.operation==25,4000);
                check(peer.retry && peer.swaps==1 && peer.map[14]==15 && peer.map[15]==14,"duplicate swap");
                check(peer.starts==0 && peer.guideFrames==0 && peer.scoreFrames==0,"transfer overlapping key operation");
                check(ui.ack.noteA==15 && ui.ack.noteB==14 && ui.detail.contains("D4"),"physical labels");
                s.keys(24,14,15);await(()->!s.guideBusy() && ui.ack!=null && ui.ack.operation==24,2000);check(ui.ack.noteA==15,"query after swap");
                peer.busy=true;s.keys(26,0,1);await(()->!s.guideBusy() && ui.ack!=null && ui.ack.status==4,2000);check(peer.map[14]==15,"busy reset");
                peer.busy=false;s.keys(26,0,1);await(()->!s.guideBusy() && ui.ack!=null && ui.ack.status==0,2000);check(peer.map[14]==14,"restore identity");
                s.guideControl(GuideProtocol.NEXT);await(()->!s.guideBusy(),2000);check(peer.guideFrames==1,"MIDI after keys");
                s.scoreControl(ScoreProtocol.CLEAR);await(()->!s.guideBusy(),2000);check(peer.scoreFrames==1,"PDF after keys");
            }else{
                s.keys(25,0,1);Thread.sleep(60);check(peer.keyFrames==0 && !s.keyAvailable() && !s.guideBusy(),"v31 unsafe commands");
            }
            s.leave();await(()->s.phase()==RecorderSession.Phase.CLOSED,1000);
        }
    }
    public static void main(String[] argv)throws Exception{
        Path dir=Files.createTempDirectory("key-test-");
        try{run(true,dir);run(false,dir);}finally{Files.delete(dir);}
        System.out.println("PASS real session: ~J capability, dropped swap ACK identical retry, one mutation, query/reset/BUSY, transfer exclusion and v31 fallback");
    }
}
