package android.bluetooth;
import java.io.IOException;
import java.util.UUID;
public class BluetoothDevice {
    private final BluetoothSocket socket;
    public BluetoothDevice(BluetoothSocket s){socket=s;}
    public BluetoothSocket createRfcommSocketToServiceRecord(UUID u)throws IOException{return socket;}
}
