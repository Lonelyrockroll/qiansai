package cn.tangsynth.recorder;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothDevice;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.*;
import java.io.*;
import java.util.Arrays;
import java.util.Locale;

public final class MainActivity extends Activity implements RecorderSession.Listener {
    private static final int PERMISSION=101, EXPORT=102;
    private static final int BG=0xff102226,PANEL=0xff1c3338,TEXT=0xffecf5f1,MUTED=0xffa7bfbe,MINT=0xff94ebca;
    private RecorderSession session;
    private MediaPlayer player;
    private File library,exporting;
    private File[] takes={};
    private TextView deviceState,clock,hint,libraryInfo;
    private ProgressBar meter;
    private Button link,record,play,export;
    private Spinner selection;
    private boolean alive=true;

    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);
        library=new File(getFilesDir(),"recordings");
        if(saved!=null && saved.getString("exporting")!=null)exporting=new File(library,saved.getString("exporting"));
        layout();
        try {WavTake.recover(library);}catch(IOException ex){hint.setText(ex.getMessage());}
        reloadTakes(null);render(null,"等待连接",0,0);
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private GradientDrawable panel(int color,int radius){
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));return d;
    }
    private LinearLayout column(){LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private void add(LinearLayout parent,View child,int top){
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(top);parent.addView(child,lp);
    }
    private TextView label(String s,int size,int color,boolean bold){
        TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setTextColor(color);
        if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        return v;
    }
    private Button button(String title,int color){
        Button b=new Button(this);b.setAllCaps(false);b.setText(title);b.setTextColor(color==MINT?BG:TEXT);
        b.setBackground(panel(color,12));b.setMinHeight(dp(48));b.setPadding(dp(12),dp(8),dp(12),dp(8));return b;
    }
    private LinearLayout card(LinearLayout parent){
        LinearLayout c=column();c.setPadding(dp(17),dp(16),dp(17),dp(16));c.setBackground(panel(PANEL,18));add(parent,c,14);return c;
    }
    private void layout(){
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(BG);
        if(Build.VERSION.SDK_INT>=30){
            getWindow().setDecorFitsSystemWindows(false);
            scroll.setOnApplyWindowInsetsListener((v,i)->{android.graphics.Insets b=i.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                v.setPadding(b.left,b.top,b.right,b.bottom);return i;});
        }
        LinearLayout root=column();root.setPadding(dp(20),dp(24),dp(20),dp(24));scroll.addView(root);setContentView(scroll);
        add(root,label("TANG   /   AUDIO",13,MINT,true),0);
        add(root,label("演奏录音",32,TEXT,true),5);
        add(root,label("从开发板收取效果器后的声音",15,MUTED,false),4);
        LinearLayout device=card(root);
        add(device,label("01    蓝牙设备",13,MINT,true),0);
        add(device,label("=BTNU1  ·  JDY-31",21,TEXT,true),8);
        deviceState=label("",14,MUTED,false);add(device,deviceState,4);
        link=button("连接板卡",0xff33545b);add(device,link,12);link.setOnClickListener(v->{if(session==null)connect();else session.leave();});
        TextView settings=label("打开系统蓝牙设置  ↗",14,MINT,false);
        settings.setPadding(0,dp(8),0,dp(8));add(device,settings,4);
        settings.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        LinearLayout capture=card(root);
        add(capture,label("02    录音",13,MINT,true),0);
        clock=label("00:00.0",37,TEXT,true);clock.setTypeface(Typeface.MONOSPACE);add(capture,clock,6);
        meter=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);meter.setMax(32768);
        meter.setProgressTintList(android.content.res.ColorStateList.valueOf(MINT));add(capture,meter,4);
        hint=label("等待连接",14,MUTED,false);add(capture,hint,9);
        record=button("开始录音",MINT);add(capture,record,14);
        record.setOnClickListener(v->{if(session==null)return;stopPlayback();if(session.phase()==RecorderSession.Phase.READY)session.start();else session.stop();});
        add(capture,label("单声道 WAV · 16.28 kHz · 最长 10 分钟。请保持 App 在前台，先在板上开始演奏。",13,MUTED,false),10);
        LinearLayout clips=card(root);add(clips,label("03    手机录音",13,MINT,true),0);
        libraryInfo=label("",14,MUTED,false);add(clips,libraryInfo,8);
        selection=new Spinner(this);add(clips,selection,3);
        play=button("试听",0xff33545b);export=button("导出 WAV",0xff33545b);
        LinearLayout row=new LinearLayout(this);add(clips,row,10);
        row.addView(play,new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(0,-2,1);ep.leftMargin=dp(8);row.addView(export,ep);
        play.setOnClickListener(v->playSelected());export.setOnClickListener(v->chooseExport());
    }
    private void connect(){
        if(Build.VERSION.SDK_INT>=31 && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED){
            requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},PERMISSION);return;
        }
        try{
            BluetoothManager manager=(BluetoothManager)getSystemService(BLUETOOTH_SERVICE);
            BluetoothAdapter adapter=manager==null?null:manager.getAdapter();
            if(adapter==null || !adapter.isEnabled()){hint.setText("请在系统设置中打开蓝牙");return;}
            BluetoothDevice target=null;
            for(BluetoothDevice d:adapter.getBondedDevices())if(RecorderSession.ADDRESS.equalsIgnoreCase(d.getAddress())){target=d;break;}
            if(target==null){hint.setText("请先在系统蓝牙中配对 =BTNU1（地址尾号 7BB6），再返回连接");return;}
            session=new RecorderSession(target,library,this);session.connect();
        }catch(SecurityException e){hint.setText("需要允许“附近设备”权限");}
    }
    @Override public void onRequestPermissionsResult(int code,String[] perms,int[] results){
        super.onRequestPermissionsResult(code,perms,results);
        if(code==PERMISSION){if(results.length>0 && results[0]==PackageManager.PERMISSION_GRANTED)connect();else hint.setText("请允许附近设备权限后重试");}
    }
    @Override public void status(RecorderSession source,RecorderSession.Phase p,String message,long samples,int peak){
        runOnUiThread(()->{if(alive && source==session){if(p==RecorderSession.Phase.CLOSED)session=null;render(p,message,samples,peak);}});
    }
    private void render(RecorderSession.Phase p,String message,long samples,int peak){
        boolean offline=p==null || p==RecorderSession.Phase.CLOSED;
        boolean taking=p==RecorderSession.Phase.STARTING || p==RecorderSession.Phase.RECORDING || p==RecorderSession.Phase.STOPPING;
        if(taking)getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        deviceState.setText(offline?"未连接 · 经典蓝牙 SPP":p==RecorderSession.Phase.CONNECTING || p==RecorderSession.Phase.PROBING?"正在握手…":"已连接 · 音频协议 v1");
        link.setText(offline?"连接板卡":"断开连接");hint.setText(message);
        record.setEnabled(p==RecorderSession.Phase.READY || p==RecorderSession.Phase.STARTING || p==RecorderSession.Phase.RECORDING);
        record.setAlpha(record.isEnabled()?1f:.48f);record.setText(taking?(p==RecorderSession.Phase.STOPPING?"正在保存…":"停止并保存"):"开始录音");
        long tenth=samples*10/AudioFrame.RATE;clock.setText(String.format(Locale.US,"%02d:%02d.%d",tenth/600,(tenth/10)%60,tenth%10));
        meter.setProgress(peak);play.setEnabled(!taking && takes.length>0);export.setEnabled(!taking && takes.length>0);
    }
    @Override public void saved(RecorderSession src,File file,boolean partial){
        runOnUiThread(()->{if(alive)reloadTakes(file);});
    }
    private void reloadTakes(File selected){
        File[] list=library.listFiles((d,n)->n.endsWith(".wav"));takes=list==null?new File[0]:list;
        Arrays.sort(takes,(a,b)->Long.compare(b.lastModified(),a.lastModified()));
        String[] names=new String[takes.length];int ix=0;
        for(int i=0;i<takes.length;i++){
            names[i]=takes[i].getName().replaceFirst("-[0-9]+(?=(-中断)?\\.wav$)","").replace(".wav","");
            if(takes[i].equals(selected))ix=i;
        }
        ArrayAdapter<String> a=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,names);
        a.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);selection.setAdapter(a);if(takes.length>0)selection.setSelection(ix);
        libraryInfo.setText(takes.length==0?"暂无录音":"已保存 "+takes.length+" 段 · 可选择试听或导出");
        play.setEnabled(takes.length>0);export.setEnabled(takes.length>0);
    }
    private File selected(){int i=selection.getSelectedItemPosition();return i>=0 && i<takes.length?takes[i]:null;}
    private void stopPlayback(){if(player!=null){player.release();player=null;}play.setText("试听");}
    private void playSelected(){
        if(player!=null){stopPlayback();return;}
        File f=selected();if(f==null)return;
        try{player=new MediaPlayer();player.setDataSource(f.getAbsolutePath());player.prepare();
            player.setOnCompletionListener(p->stopPlayback());player.setOnErrorListener((p,w,e)->{stopPlayback();hint.setText("WAV 播放失败");return true;});
            player.start();play.setText("停止试听");
        }catch(IOException|RuntimeException e){stopPlayback();hint.setText("无法播放这段录音");}
    }
    private void chooseExport(){
        exporting=selected();if(exporting==null)return;stopPlayback();
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("audio/wav");i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_TITLE,exporting.getName());startActivityForResult(i,EXPORT);
    }
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);
        if(code!=EXPORT)return;
        File src=exporting;exporting=null;
        if(result!=RESULT_OK || data==null || data.getData()==null || src==null)return;
        Uri dest=data.getData();
        new Thread(()->{String msg;
            try(InputStream in=new FileInputStream(src);OutputStream out=getContentResolver().openOutputStream(dest,"wt")){
                if(out==null)throw new IOException();
                byte[] buf=new byte[32768];int n;while((n=in.read(buf))!=-1)out.write(buf,0,n);
                msg="WAV 已导出";
            }catch(IOException|RuntimeException e){msg="导出失败，原录音仍在手机内";}
            final String feedback=msg;runOnUiThread(()->{if(alive)hint.setText(feedback);});
        },"WAV export").start();
    }
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);if(exporting!=null)state.putString("exporting",exporting.getName());}
    @Override protected void onStop(){super.onStop();stopPlayback();if(session!=null)session.leave();}
    @Override protected void onDestroy(){alive=false;if(session!=null && session.phase()!=RecorderSession.Phase.STOPPING)session.close("页面已关闭");super.onDestroy();}
}
