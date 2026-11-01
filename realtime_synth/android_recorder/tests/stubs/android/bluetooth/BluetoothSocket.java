package android.bluetooth;
import java.io.*;
public class BluetoothSocket {
    private final InputStream in;private final OutputStream out;
    public BluetoothSocket(InputStream i,OutputStream o){in=i;out=o;}
    public void connect()throws IOException{}
    public InputStream getInputStream()throws IOException{return in;}
    public OutputStream getOutputStream()throws IOException{return out;}
    public void close()throws IOException{in.close();out.close();}
}
