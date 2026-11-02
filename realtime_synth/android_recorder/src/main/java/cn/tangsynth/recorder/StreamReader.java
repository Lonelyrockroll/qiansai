package cn.tangsynth.recorder;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

/** Recognizes frame signatures only between complete frames, never inside audio payloads. */
final class StreamReader {
    final AudioFrame audio=new AudioFrame();
    GuideProtocol.Ack acknowledgement;
    ScoreProtocol.Ack scoreAcknowledgement;
    KeyProtocol.Ack keyAcknowledgement;
    boolean read(InputStream in)throws IOException{
        acknowledgement=null;scoreAcknowledgement=null;keyAcknowledgement=null;
        int signature=0;
        while(true){
            int value=in.read();
            if(value<0)throw new EOFException("蓝牙连接已关闭");
            signature=(signature<<8)|value;
            if(signature==0x54524543){audio.readBody(in);return true;}
            if(signature==0x5447414b){
                try{acknowledgement=GuideProtocol.readReply(in);return false;}
                catch(IOException bad){
                    if(bad instanceof EOFException)throw bad;
                    signature=0; // A damaged ACK is retried by the sender.
                }
            }
            if(signature==0x5450414b){
                try{scoreAcknowledgement=ScoreProtocol.readReply(in);return false;}
                catch(IOException bad){if(bad instanceof EOFException)throw bad;signature=0;}
            }
            if(signature==0x544b414b){
                try{keyAcknowledgement=KeyProtocol.readReply(in);return false;}
                catch(IOException bad){if(bad instanceof EOFException)throw bad;signature=0;}
            }
        }
    }
}
