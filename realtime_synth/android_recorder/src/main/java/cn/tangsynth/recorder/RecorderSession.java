package cn.tangsynth.recorder;

import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.os.SystemClock;
import java.io.BufferedInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** One connection owns one reader, one ordered writer, and at most one active take. */
final class RecorderSession {
    enum Phase {CONNECTING, PROBING, READY, STARTING, RECORDING, STOPPING, CLOSED}
    interface Listener {
        void status(RecorderSession source, Phase phase, String detail, long samples, int peak);
        void saved(RecorderSession source, File file, boolean interrupted);
    }
    static final String ADDRESS="2F:92:2C:11:7B:B6";
    private static final UUID SPP=UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    private final File directory;
    private final BluetoothDevice device;
    private final Listener listener;
    private final ExecutorService writer=Executors.newSingleThreadExecutor();
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor();
    private volatile BluetoothSocket socket;
    private volatile Phase phase=Phase.CONNECTING;
    private volatile long deadline, samples;
    private volatile int peak;
    private volatile boolean leaveAfterStop;
    private volatile String exitDetail="连接已关闭";
    // Only the reader accesses take.
    private WavTake take;
    private long nextUi;
    private final AudioFrame frame=new AudioFrame();

    RecorderSession(BluetoothDevice device,File dir,Listener listener) {
        this.device=device;directory=dir;this.listener=listener;
    }
    Phase phase(){return phase;}
    private void report(String detail){listener.status(this,phase,detail,samples,peak);}
    private void transition(Phase next,String detail,long timeoutMs){
        deadline=timeoutMs==0?0:SystemClock.elapsedRealtime()+timeoutMs;
        phase=next;report(detail);
    }
    void connect() {
        transition(Phase.CONNECTING,"连接经典蓝牙模块…",12000);
        timer.scheduleAtFixedRate(this::watchdog,900,900,TimeUnit.MILLISECONDS);
        new Thread(this::readLoop,"Tang SPP reader").start();
    }
    private synchronized void watchdog(){
        long limit=deadline;
        if(phase==Phase.CLOSED)return;
        if(limit!=0 && SystemClock.elapsedRealtime()>limit){
            String why=phase==Phase.PROBING?"未检测到录音固件，请下载 v23 录音版":phase==Phase.CONNECTING?
                "连接超时，请关闭占用模块的串口 App":"未收到完整音频帧或结束帧";
            close(why);return;
        }
        if(phase==Phase.PROBING)write("UUUU~I");
        else if(phase==Phase.RECORDING || phase==Phase.STARTING)write("~K");
    }
    private void write(String text){
        try {writer.execute(()->{
            BluetoothSocket current=socket;
            if(phase==Phase.CLOSED || current==null)return;
            try {current.getOutputStream().write(text.getBytes(StandardCharsets.US_ASCII));}
            catch(IOException ex){close("蓝牙发送中断");}
        });} catch(RejectedExecutionException ignored){/* closing */}
    }
    synchronized void start() {
        if(phase!=Phase.READY)return;
        samples=0;peak=0;transition(Phase.STARTING,"等待第一帧…",4000);write("~R");
    }
    synchronized void stop(){
        if(phase!=Phase.STARTING && phase!=Phase.RECORDING)return;
        transition(Phase.STOPPING,"正在收取最后一帧…",3500);write("~S");
    }
    synchronized void leave() {
        if(phase==Phase.STARTING || phase==Phase.RECORDING || phase==Phase.STOPPING){
            leaveAfterStop=true;stop();
        } else close("已断开连接");
    }
    synchronized void close(String reason) {
        if(phase==Phase.CLOSED)return;
        exitDetail=reason;phase=Phase.CLOSED;deadline=0;
        BluetoothSocket current=socket;
        if(current!=null)try{current.close();}catch(IOException ignored){}
    }
    private void readLoop(){
        try {
            BluetoothSocket made=device.createRfcommSocketToServiceRecord(SPP);
            synchronized(this){
                if(phase==Phase.CLOSED){made.close();return;} socket=made;
            }
            made.connect();
            synchronized(this){
                if(phase==Phase.CLOSED)return;
                transition(Phase.PROBING,"验证 FPGA 录音协议…",5500);write("UUUU~I");
            }
            BufferedInputStream in=new BufferedInputStream(made.getInputStream(),4096);
            while(phase!=Phase.CLOSED){frame.read(in);handleFrame();}
        } catch(IOException|SecurityException ex) {
            if(phase!=Phase.CLOSED)close(ex.getMessage()==null?"蓝牙连接中断":ex.getMessage());
        } finally {
            close(exitDetail);timer.shutdownNow();writer.shutdownNow();
            if(take!=null){
                try {finish(true);}
                catch(IOException ex){exitDetail="录音暂未归档，重新打开 App 可尝试恢复";}
            }
            report(exitDetail);
        }
    }
    private synchronized void handleFrame() throws IOException {
        if(phase==Phase.CLOSED)return;
        if(frame.type==AudioFrame.INFO){
            if(phase==Phase.PROBING)transition(Phase.READY,"录音接口已就绪",0);
            return;
        }
        if(phase==Phase.PROBING || phase==Phase.READY)return; // Old session winding down.
        if(frame.type==AudioFrame.END){
            boolean interrupted=frame.field!=0 || frame.sequence!=(take==null?0:take.blocks);
            finish(interrupted);
            String detail=interrupted?(frame.field==3?"蓝牙串口速率不足":frame.field==1?"保活超时，录音已中断":
                "录音中断，已保留完整帧"):"录音已保存";
            transition(Phase.READY,detail,0);
            if(leaveAfterStop)close("已断开连接");
            return;
        }
        if(take==null){
            if(frame.sequence!=0)throw new IOException("缺少录音首帧");
            take=new WavTake(directory);
        }
        take.append(frame);
        samples=take.blocks*AudioFrame.SAMPLES;
        int loudness=0;
        for(int i=0;i<frame.pcm.length;i+=2){
            int value=(short)((frame.pcm[i]&255)|(frame.pcm[i+1]<<8));
            loudness=Math.max(loudness,Math.abs(value));
        }
        peak=loudness;
        if(phase!=Phase.STOPPING){
            deadline=SystemClock.elapsedRealtime()+3500;
            if(phase==Phase.STARTING)transition(Phase.RECORDING,"接收板卡音频",3500);
            if(samples>=WavTake.MAX_SAMPLES)stop();
        }
        long now=SystemClock.elapsedRealtime();
        if(now>=nextUi){nextUi=now+180;report(phase==Phase.STOPPING?"正在结束录音…":"接收板卡音频");}
    }
    private void finish(boolean partial) throws IOException {
        if(take==null)return;
        WavTake finished=take;take=null;
        File file=finished.finish(partial);
        if(file!=null)listener.saved(this,file,partial);
    }
}
