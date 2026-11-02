package cn.tangsynth.recorder;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
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
import android.provider.OpenableColumns;
import android.database.Cursor;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.*;
import java.io.*;
import java.util.Arrays;
import java.util.Locale;

public final class MainActivity extends Activity implements RecorderSession.Listener {
    private static final int PERMISSION=101, EXPORT=102, IMPORT_MIDI=103,IMPORT_PDF=104;
    private static final int BG=0xff102226,PANEL=0xff1c3338,TEXT=0xffecf5f1,MUTED=0xffa7bfbe,MINT=0xff94ebca;
    private RecorderSession session;
    private MediaPlayer player;
    private File library,exporting;
    private File[] takes={};
    private TextView deviceState,clock,hint,libraryInfo;
    private ProgressBar meter;
    private Button link,record,play,export;
    private Spinner selection;
    private volatile boolean alive=true;
    private boolean documentPicker,midiImporting,onlineImporting;
    private Thread downloadThread;
    private MidiGuide.Song midi;
    private MidiGuide.Compiled compiled;
    private java.util.List<MidiGuide.Track> midiTracks=java.util.Collections.emptyList();
    private String midiName="";
    private TextView midiInfo,guideHint;
    private Spinner tracks;
    private Button chooseMidi,sampleMidi,sendMidi,guideToggle,guideRestart,guidePrevious,guideNext,guideDemo,guideSpeed;
    private int compileGeneration;
    private TextView scoreInfo,scoreHint;
    private Button choosePdf,samplePdf,sendScore,scorePrevious,scoreNext,scoreHide,scoreShow,scoreClear;
    private ImageView scorePreview;
    private android.graphics.Bitmap scoreBitmap;
    private ScoreProtocol.Page scorePage;
    private boolean scorePreparing;
    private String scoreName="";
    private Button onlinePdf,onlineMidi,keyQuery,keySwap,keyReset;
    private Spinner keyA,keyB;
    private TextView keyHint;

    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);
        library=new File(getFilesDir(),"recordings");
        if(saved!=null && saved.getString("exporting")!=null)exporting=new File(library,saved.getString("exporting"));
        layout();
        try {WavTake.recover(library);}catch(IOException ex){hint.setText(ex.getMessage());}
        reloadTakes(null);render(null,"等待连接",0,0);
        File remembered=new File(getFilesDir(),"last-guide.mid");
        if(remembered.isFile())loadMidi(remembered,getPreferences(0).getString("midiName","上次导入的 MIDI"));
        if(new File(getFilesDir(),"last-score.pdf").isFile()){
            scoreName=getPreferences(0).getString("scoreName","上次导入的 PDF");prepareScore(0,false);
        }
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
        add(root,label("TANG   /   PLAY",13,MINT,true),0);
        add(root,label("演奏助手",32,TEXT,true),5);
        add(root,label("MIDI 指引 · PDF 曲谱 · 演奏录音",15,MUTED,false),4);
        LinearLayout device=card(root);
        add(device,label("01    蓝牙设备",13,MINT,true),0);
        add(device,label("=BTNU1  ·  JDY-31",21,TEXT,true),8);
        deviceState=label("",14,MUTED,false);add(device,deviceState,4);
        link=button("连接板卡",0xff33545b);add(device,link,12);link.setOnClickListener(v->{if(session==null)connect();else session.leave();});
        TextView settings=label("打开系统蓝牙设置  ↗",14,MINT,false);
        settings.setPadding(0,dp(8),0,dp(8));add(device,settings,4);
        settings.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        LinearLayout guide=card(root);add(guide,label("02    MIDI 屏幕指引",13,MINT,true),0);
        add(guide,label("把旋律带到琴上",23,TEXT,true),7);
        add(guide,label("选择一条 MIDI 音轨。C2～F6 的 32 个白键可演示，屏幕按原音轨颜色显示新弹音与延音。",13,MUTED,false),5);
        LinearLayout files=new LinearLayout(this);add(guide,files,12);
        chooseMidi=button("选择 MIDI",0xff33545b);sampleMidi=button("示例 MIDI",0xff33545b);
        files.addView(chooseMidi,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(0,-2,1);sp.leftMargin=dp(8);files.addView(sampleMidi,sp);
        chooseMidi.setOnClickListener(v->chooseMidi());sampleMidi.setOnClickListener(v->loadSample());
        onlineMidi=button("从网址下载 MIDI",0xff33545b);add(guide,onlineMidi,8);
        onlineMidi.setOnClickListener(v->onlineDialog(OnlineScore.Kind.MIDI));
        midiInfo=label("尚未选择曲目",14,MUTED,false);add(guide,midiInfo,10);
        tracks=new Spinner(this);add(guide,tracks,5);
        tracks.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            @Override public void onItemSelected(AdapterView<?> p,View v,int pos,long id){compileTrack(pos);}
            @Override public void onNothingSelected(AdapterView<?> p){}
        });
        sendMidi=button("发送曲目到板卡",MINT);add(guide,sendMidi,9);sendMidi.setOnClickListener(v->sendMidi());
        guideHint=label("连接支持指引的板卡后，可传曲目并控制播放。",14,MUTED,false);add(guide,guideHint,10);
        LinearLayout row1=new LinearLayout(this);add(guide,row1,10);
        guideToggle=button("播放 / 暂停",0xff33545b);guideRestart=button("回到开头",0xff33545b);
        pair(row1,guideToggle,guideRestart);
        LinearLayout row2=new LinearLayout(this);add(guide,row2,8);
        guidePrevious=button("上一组音",0xff33545b);guideNext=button("下一组音",0xff33545b);
        pair(row2,guidePrevious,guideNext);
        LinearLayout row3=new LinearLayout(this);add(guide,row3,8);
        guideDemo=button("板载示范曲",0xff33545b);guideSpeed=button("切换速度",0xff33545b);
        pair(row3,guideDemo,guideSpeed);
        guideToggle.setOnClickListener(v->guideCommand(GuideProtocol.TOGGLE));
        guideRestart.setOnClickListener(v->guideCommand(GuideProtocol.RESTART));
        guidePrevious.setOnClickListener(v->guideCommand(GuideProtocol.PREVIOUS));
        guideNext.setOnClickListener(v->guideCommand(GuideProtocol.NEXT));
        guideDemo.setOnClickListener(v->guideCommand(GuideProtocol.DEMO));
        guideSpeed.setOnClickListener(v->guideCommand(GuideProtocol.SPEED));
        add(guide,label("传完后可断开手机，由 FPGA 自行计时。导入曲目保存在板内 SRAM，断电后需重传。指引显示与录音传输分时操作。",12,MUTED,false),10);
        LinearLayout score=card(root);add(score,label("03    PDF 曲谱",13,MINT,true),0);
        add(score,label("在琴上全屏看谱",23,TEXT,true),7);
        add(score,label("选择手机中的 PDF 或在线下载曲谱，再把当前页发送到板卡。翻页时请保持蓝牙连接。",13,MUTED,false),5);
        LinearLayout scoreFiles=new LinearLayout(this);add(score,scoreFiles,12);
        choosePdf=button("选择 PDF",0xff33545b);samplePdf=button("示例 PDF",0xff33545b);pair(scoreFiles,choosePdf,samplePdf);
        choosePdf.setOnClickListener(v->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/pdf");documentPicker=true;startActivityForResult(i,IMPORT_PDF);});
        samplePdf.setOnClickListener(v->loadPdf(null));
        onlinePdf=button("从网址下载 PDF",0xff33545b);add(score,onlinePdf,8);
        onlinePdf.setOnClickListener(v->onlineDialog(OnlineScore.Kind.PDF));
        scoreInfo=label("尚未选择曲谱",14,MUTED,false);add(score,scoreInfo,10);
        scorePreview=new ImageView(this);scorePreview.setAdjustViewBounds(true);scorePreview.setScaleType(ImageView.ScaleType.FIT_CENTER);add(score,scorePreview,8);
        sendScore=button("发送本页并显示",MINT);add(score,sendScore,9);
        sendScore.setOnClickListener(v->{if(session!=null && scorePage!=null)session.uploadScore(scorePage);});
        scoreHint=label("连接 v31 或更新的曲谱固件后可使用。",14,MUTED,false);add(score,scoreHint,10);
        LinearLayout pageRow=new LinearLayout(this);add(score,pageRow,10);
        scorePrevious=button("上一页并发送",0xff33545b);scoreNext=button("下一页并发送",0xff33545b);pair(pageRow,scorePrevious,scoreNext);
        scorePrevious.setOnClickListener(v->{if(scorePage!=null)prepareScore(scorePage.index-1,true);});
        scoreNext.setOnClickListener(v->{if(scorePage!=null)prepareScore(scorePage.index+1,true);});
        LinearLayout visibleRow=new LinearLayout(this);add(score,visibleRow,8);
        scoreHide=button("返回演奏界面",0xff33545b);scoreShow=button("显示已传页面",0xff33545b);pair(visibleRow,scoreHide,scoreShow);
        scoreHide.setOnClickListener(v->{if(session!=null)session.scoreControl(ScoreProtocol.HIDE);});
        scoreShow.setOnClickListener(v->{if(session!=null)session.scoreControl(ScoreProtocol.SHOW);});
        scoreClear=button("清除板上曲谱",0xff33545b);add(score,scoreClear,8);scoreClear.setOnClickListener(v->{if(session!=null)session.scoreControl(ScoreProtocol.CLEAR);});
        add(score,label("板卡保留一页；换页时会暂时退出全屏。短按旋钮 B 或板上 KEY.0 也可返回演奏界面。横向、大字号曲谱更易阅读；上限 20 MB / 200 页。",12,MUTED,false),10);
        addKeyCard(root);
        LinearLayout capture=card(root);
        add(capture,label("05    录音",13,MINT,true),0);
        clock=label("00:00.0",37,TEXT,true);clock.setTypeface(Typeface.MONOSPACE);add(capture,clock,6);
        meter=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);meter.setMax(32768);
        meter.setProgressTintList(android.content.res.ColorStateList.valueOf(MINT));add(capture,meter,4);
        hint=label("等待连接",14,MUTED,false);add(capture,hint,9);
        record=button("开始录音",MINT);add(capture,record,14);
        record.setOnClickListener(v->{if(session==null)return;stopPlayback();if(session.phase()==RecorderSession.Phase.READY)session.start();else session.stop();});
        add(capture,label("单声道 WAV · 16.28 kHz · 最长 10 分钟。请保持 App 在前台，先在板上开始演奏。",13,MUTED,false),10);
        LinearLayout clips=card(root);add(clips,label("06    手机录音",13,MINT,true),0);
        libraryInfo=label("",14,MUTED,false);add(clips,libraryInfo,8);
        selection=new Spinner(this);add(clips,selection,3);
        play=button("试听",0xff33545b);export=button("导出 WAV",0xff33545b);
        LinearLayout row=new LinearLayout(this);add(clips,row,10);
        row.addView(play,new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(0,-2,1);ep.leftMargin=dp(8);row.addView(export,ep);
        play.setOnClickListener(v->playSelected());export.setOnClickListener(v->chooseExport());
    }
    private void pair(LinearLayout row,Button a,Button b){
        row.addView(a,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams right=new LinearLayout.LayoutParams(0,-2,1);right.leftMargin=dp(8);row.addView(b,right);
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
        record.setEnabled((p==RecorderSession.Phase.READY && (session==null || !session.guideBusy())) || p==RecorderSession.Phase.STARTING || p==RecorderSession.Phase.RECORDING);
        record.setAlpha(record.isEnabled()?1f:.48f);record.setText(taking?(p==RecorderSession.Phase.STOPPING?"正在保存…":"停止并保存"):"开始录音");
        long tenth=samples*10/AudioFrame.RATE;clock.setText(String.format(Locale.US,"%02d:%02d.%d",tenth/600,(tenth/10)%60,tenth%10));
        meter.setProgress(peak);play.setEnabled(!taking && takes.length>0);export.setEnabled(!taking && takes.length>0);
        renderGuideButtons();
    }
    @Override public void guide(RecorderSession src,GuideProtocol.Ack state,String detail,boolean busy){
        runOnUiThread(()->{if(alive && src==session){guideHint.setText(detail);renderGuideButtons();}});
    }
    @Override public void score(RecorderSession src,ScoreProtocol.Ack state,String detail,boolean busy){
        runOnUiThread(()->{if(alive && src==session){scoreHint.setText(detail);renderGuideButtons();}});
    }
    @Override public void keys(RecorderSession src,KeyProtocol.Ack state,String detail,boolean busy){
        runOnUiThread(()->{if(alive && src==session){keyHint.setText(detail);renderGuideButtons();}});
    }
    private void addKeyCard(LinearLayout root){
        LinearLayout box=card(root);add(box,label("04    实体琴键",13,MINT,true),0);
        add(box,label("调整白键音高",23,TEXT,true),7);
        add(box,label("查询当前音高，或交换 A 与 B 两个琴键。交换和恢复前请先静音、松开所有琴键。板卡断电后恢复默认布局。",13,MUTED,false),6);
        String[] names=new String[32];
        for(int i=0;i<names.length;i++)names[i]=KeyProtocol.key(i)+" · 默认 "+KeyProtocol.note(i);
        ArrayAdapter<String> choices=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,names);
        choices.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        add(box,label("琴键 A",14,TEXT,false),10);keyA=new Spinner(this);keyA.setAdapter(choices);add(box,keyA,4);
        add(box,label("琴键 B",14,TEXT,false),8);keyB=new Spinner(this);keyB.setAdapter(choices);keyB.setSelection(1);add(box,keyB,4);
        LinearLayout row=new LinearLayout(this);add(box,row,8);keyQuery=button("查询 A",0xff33545b);
        keySwap=button("交换 A 与 B",0xff33545b);pair(row,keyQuery,keySwap);
        keyReset=button("恢复默认音高",0xff33545b);add(box,keyReset,8);
        keyHint=label("连接支持键位设置的固件后可调整。",14,MUTED,false);add(box,keyHint,8);
        keyQuery.setOnClickListener(v->keyCommand(KeyProtocol.QUERY));keySwap.setOnClickListener(v->keyCommand(KeyProtocol.SWAP));
        keyReset.setOnClickListener(v->keyCommand(KeyProtocol.RESET));
    }
    private void keyCommand(int operation){
        if(session!=null)session.keys(operation,keyA.getSelectedItemPosition(),keyB.getSelectedItemPosition());
    }
    private void renderGuideButtons(){
        boolean ready=session!=null && session.phase()==RecorderSession.Phase.READY;
        boolean busy=scorePreparing || onlineImporting || (session!=null && session.guideBusy());
        boolean available=ready && !busy && session.guideAvailable();
        if(ready && session.guideAvailable())deviceState.setText("已连接 · 录音与 MIDI 屏幕指引");
        if(ready && session.scoreAvailable())deviceState.setText("已连接 · 录音 / MIDI / PDF");
        if(ready && session.keyAvailable())deviceState.setText("已连接 · 录音 / MIDI / PDF / 键位");
        for(Button b:new Button[]{guideToggle,guideRestart,guidePrevious,guideNext,guideDemo,guideSpeed}){
            if(b!=null){b.setEnabled(available);b.setAlpha(available?1f:.45f);}
        }
        if(sendMidi!=null){sendMidi.setEnabled(available && compiled!=null);sendMidi.setAlpha(sendMidi.isEnabled()?1f:.45f);}
        boolean editable=!midiImporting && !busy && (session==null || ready);
        if(chooseMidi!=null)chooseMidi.setEnabled(editable);
        if(sampleMidi!=null)sampleMidi.setEnabled(editable);
        if(onlineMidi!=null)onlineMidi.setEnabled(editable);
        if(tracks!=null)tracks.setEnabled(editable && !midiTracks.isEmpty());
        if(record!=null && ready){record.setEnabled(!busy);record.setAlpha(!busy?1f:.48f);}
        if(ready){play.setEnabled(!busy && takes.length>0);export.setEnabled(!busy && takes.length>0);}
        boolean scoreReady=ready && !busy && session.scoreAvailable();
        boolean scoreEditable=!busy && !midiImporting && (session==null || ready);
        if(choosePdf!=null)choosePdf.setEnabled(scoreEditable);
        if(samplePdf!=null)samplePdf.setEnabled(scoreEditable);
        if(onlinePdf!=null)onlinePdf.setEnabled(scoreEditable);
        if(sendScore!=null)sendScore.setEnabled(scoreReady && scorePage!=null);
        if(scorePrevious!=null)scorePrevious.setEnabled(scoreReady && scorePage!=null && scorePage.index>0);
        if(scoreNext!=null)scoreNext.setEnabled(scoreReady && scorePage!=null && scorePage.index+1<scorePage.count);
        boolean cached=scoreReady && session.scoreState()!=null && session.scoreState().valid();
        if(scoreShow!=null)scoreShow.setEnabled(cached);
        if(scoreHide!=null)scoreHide.setEnabled(cached);
        if(scoreClear!=null)scoreClear.setEnabled(cached);
        boolean keys=ready && !busy && session.keyAvailable();
        if(keyQuery!=null){keyQuery.setEnabled(keys);keySwap.setEnabled(keys);keyReset.setEnabled(keys);}
        if(busy)getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else if(ready || session==null)getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
    private void guideCommand(int action){if(session!=null)session.guideControl(action);}
    private void onlineDialog(OnlineScore.Kind kind){
        EditText link=new EditText(this);
        link.setSingleLine();link.setHint("https://…");link.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);
        LinearLayout content=column();content.setPadding(dp(24),dp(8),dp(24),0);add(content,link,0);
        new AlertDialog.Builder(this).setTitle("在线 "+kind.label)
            .setMessage("粘贴文件直链，或下载 Mutopia 提供的公版曲谱《比利牛斯旋律》。")
            .setView(content).setPositiveButton("下载链接",(d,w)->downloadScore(link.getText().toString(),kind))
            .setNeutralButton("下载在线示范",(d,w)->downloadScore(OnlineScore.example(kind),kind)).setNegativeButton("取消",null).show();
    }
    private void downloadScore(String url,OnlineScore.Kind kind){
        if(onlineImporting || scorePreparing || midiImporting)return;
        onlineImporting=true;TextView status=kind==OnlineScore.Kind.PDF?scoreHint:guideHint;
        status.setText("正在下载 "+kind.label+"…");renderGuideButtons();
        downloadThread=new Thread(()->{
            String message;
            try{
                OnlineScore.fetch(url,kind,getFilesDir(),(file,title)->{
                    if(!alive)throw new InterruptedIOException("下载已取消");
                    if(kind==OnlineScore.Kind.PDF)acceptPdf(file,title);
                    else try(InputStream in=new FileInputStream(file)){importMidi(in,title);}
                });
                message="下载完成，可预览并发送到板卡。";
            }catch(IOException|RuntimeException ex){message="下载未完成 · "+(ex.getMessage()==null?"请检查网络或文件链接":ex.getMessage());}
            final String detail=message;
            runOnUiThread(()->{if(alive){onlineImporting=false;downloadThread=null;status.setText(detail);renderGuideButtons();}});
        },"Online score download");downloadThread.start();
    }
    private String documentName(Uri uri,String fallback){
        try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){
            if(c!=null && c.moveToFirst()){String value=c.getString(0);if(value!=null)return value.length()>120?value.substring(0,120):value;}
        }catch(RuntimeException ignored){}
        return fallback;
    }
    private void loadPdf(Uri uri){
        scorePreparing=true;scoreInfo.setText("正在读取 PDF…");renderGuideButtons();
        new Thread(()->{
            File temporary=null;
            try{
                String title=uri==null?"示例 · 小星星.pdf":documentName(uri,"导入的 PDF");
                temporary=File.createTempFile("score-",".pdf",getFilesDir());
                try(InputStream in=uri==null?getAssets().open("score-demo.pdf"):getContentResolver().openInputStream(uri)){
                    if(in==null)throw new IOException("无法打开 PDF 文件");PdfScore.copy(in,temporary);
                }
                acceptPdf(temporary,title);
            }catch(IOException|RuntimeException ex){scoreError(ex);}
            finally{if(temporary!=null)temporary.delete();}
        },"PDF import").start();
    }
    private void acceptPdf(File candidate,String title)throws IOException{
        PdfScore.Rendered rendered=PdfScore.render(candidate,0);
        try{
            if(!alive)throw new InterruptedIOException("导入已取消");
            if(!candidate.renameTo(new File(getFilesDir(),"last-score.pdf")))throw new IOException("曲谱无法保存到手机，请重试");
            getPreferences(0).edit().putString("scoreName",title).apply();publishScore(rendered,title,null);
        }catch(IOException|RuntimeException e){rendered.preview.recycle();throw e;}
    }
    private void prepareScore(int index,boolean send){
        if(scorePreparing)return;
        scorePreparing=true;scoreInfo.setText("正在整理第 "+(index+1)+" 页…");renderGuideButtons();
        final String name=scoreName;final RecorderSession target=send?session:null;
        new Thread(()->{
            try{publishScore(PdfScore.render(new File(getFilesDir(),"last-score.pdf"),index),name,target);}
            catch(IOException|RuntimeException ex){scoreError(ex);}
        },"PDF page").start();
    }
    private void publishScore(PdfScore.Rendered rendered,String name,RecorderSession target){
        runOnUiThread(()->{
            if(!alive){rendered.preview.recycle();return;}
            scorePreparing=false;scorePage=rendered.page;scoreName=name;
            scorePreview.setImageBitmap(rendered.preview);if(scoreBitmap!=null)scoreBitmap.recycle();scoreBitmap=rendered.preview;
            scoreInfo.setText(name+"\n第 "+(scorePage.index+1)+" / "+scorePage.count+" 页 · 黑白预览 · "+String.format(Locale.CHINA,"%.1f",scorePage.compressed.length/1024.0)+" KB 待发送");
            renderGuideButtons();
            if(target!=null && target==session)target.uploadScore(scorePage);
        });
    }
    private void scoreError(Exception ex){
        final String why=ex.getMessage();runOnUiThread(()->{if(alive){scorePreparing=false;scoreHint.setText(why==null?"PDF 处理失败，请重新选择":why);renderGuideButtons();}});
    }
    private void chooseMidi(){
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");
        documentPicker=true;startActivityForResult(i,IMPORT_MIDI);
    }
    private void loadSample(){
        midiImporting=true;compiled=null;compileGeneration++;midiInfo.setText("正在读取示例 MIDI…");renderGuideButtons();
        new Thread(()->{
            try(InputStream in=getAssets().open("guide-demo.mid")){importMidi(in,"示例 · 小星星.mid");}
            catch(IOException ex){runOnUiThread(()->{if(alive){midiImporting=false;midiInfo.setText("示例 MIDI 读取失败");renderGuideButtons();}});}
        },"MIDI sample").start();
    }
    private void loadMidi(File file,String name){
        midiImporting=true;renderGuideButtons();
        new Thread(()->{
            try(InputStream in=new FileInputStream(file)){MidiGuide.Song song=MidiGuide.read(in);showMidi(song,name);}
            catch(IOException ex){runOnUiThread(()->{if(alive){midiImporting=false;midiInfo.setText("上次曲目无法加载，请重新选择 MIDI");renderGuideButtons();}});}
        },"MIDI restore").start();
    }
    private void importMidi(InputStream in,String name)throws IOException{
        ByteArrayOutputStream buffer=new ByteArrayOutputStream();byte[] bytes=new byte[8192];int n;
        while((n=in.read(bytes))!=-1){if(buffer.size()+n>MidiGuide.MAX_BYTES)throw new IOException("MIDI 文件超过 2 MB");buffer.write(bytes,0,n);}
        byte[] data=buffer.toByteArray();MidiGuide.Song song=MidiGuide.parse(data);
        if(song.musicalTracks().isEmpty())throw new IOException("这份 MIDI 没有音符音轨");
        File saved=new File(getFilesDir(),"last-guide.mid"),temporary=File.createTempFile("midi-",".tmp",getFilesDir());
        try{
            try(OutputStream out=new FileOutputStream(temporary)){out.write(data);}
            if(!temporary.renameTo(saved))throw new IOException("MIDI 无法保存到应用目录");
        }finally{temporary.delete();}
        getPreferences(0).edit().putString("midiName",name).apply();showMidi(song,name);
    }
    private void showMidi(MidiGuide.Song song,String name){
        runOnUiThread(()->{
            if(!alive)return;
            midiImporting=false;midi=song;midiName=name;compiled=null;midiTracks=song.musicalTracks();compileGeneration++;
            ArrayAdapter<MidiGuide.Track> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,midiTracks);
            adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);tracks.setAdapter(adapter);
            midiInfo.setText(name);renderGuideButtons();
        });
    }
    private void compileTrack(int position){
        if(midi==null || position<0 || position>=midiTracks.size())return;
        final MidiGuide.Song selectedSong=midi;final int track=midiTracks.get(position).index;final int generation=++compileGeneration;
        compiled=null;midiInfo.setText(midiName+"\n正在整理音符…");renderGuideButtons();
        new Thread(()->{
            MidiGuide.Compiled result=null;String error=null;
            try{result=MidiGuide.compile(selectedSong,track);}catch(IOException|RuntimeException ex){error=ex.getMessage();}
            final MidiGuide.Compiled done=result;final String why=error;
            runOnUiThread(()->{if(alive && generation==compileGeneration){
                compiled=done;midiInfo.setText(midiName+"\n"+(done==null?why:done.summary()));renderGuideButtons();
            }});
        },"MIDI compile").start();
    }
    private void sendMidi(){
        MidiGuide.Compiled selected=compiled;RecorderSession target=session;
        if(selected==null || target==null)return;
        String body="发送 "+midiName+" 的音轨 "+(selected.trackIndex+1)+"。\n"+selected.summary()+"\n传入成功后，屏幕可播放、暂停及逐组指引。";
        if(selected.skipped()>0){
            new AlertDialog.Builder(this).setTitle("确认可演奏的白键")
                .setMessage(body).setNegativeButton("取消",null)
                .setPositiveButton("按此发送",(d,w)->{if(session==target && compiled==selected)target.uploadGuide(selected);}).show();
        }else target.uploadGuide(selected);
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
        i.putExtra(Intent.EXTRA_TITLE,exporting.getName());documentPicker=true;startActivityForResult(i,EXPORT);
    }
    @Override protected void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);
        documentPicker=false;
        if(code==IMPORT_PDF){if(result==RESULT_OK && data!=null && data.getData()!=null)loadPdf(data.getData());return;}
        if(code==IMPORT_MIDI){
            if(result!=RESULT_OK || data==null || data.getData()==null)return;
            Uri uri=data.getData();midiImporting=true;compiled=null;compileGeneration++;midiInfo.setText("正在读取 MIDI…");renderGuideButtons();
            new Thread(()->{
                try{
                    String title="导入的 MIDI";
                    try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){
                        if(c!=null && c.moveToFirst()){String value=c.getString(0);if(value!=null)title=value.length()>120?value.substring(0,120):value;}
                    }
                    try(InputStream in=getContentResolver().openInputStream(uri)){
                        if(in==null)throw new IOException("无法打开 MIDI 文件");importMidi(in,title);
                    }
                }catch(IOException|RuntimeException ex){
                    final String why=ex.getMessage();runOnUiThread(()->{if(alive){midiImporting=false;midiInfo.setText(why==null?"MIDI 导入失败":why);renderGuideButtons();}});
                }
            },"MIDI import").start();
            return;
        }
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
    @Override protected void onStop(){super.onStop();stopPlayback();if(session!=null && !documentPicker)session.leave();}
    @Override protected void onDestroy(){alive=false;if(downloadThread!=null)downloadThread.interrupt();if(session!=null && session.phase()!=RecorderSession.Phase.STOPPING)session.close("页面已关闭");if(scoreBitmap!=null)scoreBitmap.recycle();super.onDestroy();}
}
