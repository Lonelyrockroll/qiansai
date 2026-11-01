package cn.tangsynth.recorder;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.CRC32;

/** Bounded SMF reader. Parsing and tempo conversion happen on the phone. */
final class MidiGuide {
    static final int MAX_BYTES=2*1024*1024, MAX_EVENTS=100000;
    private static final int[] WHITE={0,2,4,5,7,9,11};
    static final class Event {
        final long tick;final int track,order,kind,channel,key,value;
        Event(long t,int tr,int ord,int k,int ch,int n,int v){tick=t;track=tr;order=ord;kind=k;channel=ch;key=n;value=v;}
    }
    static final class Track {
        final int index;String name="";int notes;long endTick;
        Track(int i){index=i;}
        @Override public String toString(){return "音轨 "+(index+1)+(name.isEmpty()?"":" · "+name)+"（"+notes+" 个音符）";}
    }
    static final class Song {
        final int division;final List<Track> tracks;final List<Event> events;
        Song(int d,List<Track> t,List<Event> e){division=d;tracks=Collections.unmodifiableList(t);events=e;}
        List<Track> musicalTracks(){
            List<Track> out=new ArrayList<>();for(Track t:tracks)if(t.notes>0)out.add(t);return out;
        }
    }
    static final class Compiled {
        final int[] words;final int durationCs,trackIndex,notes,blackKeys,outside,percussion;
        final long crc32;
        Compiled(int[] w,int duration,int tr,int count,int black,int out,int drums){
            words=w;durationCs=duration;trackIndex=tr;notes=count;blackKeys=black;outside=out;percussion=drums;
            CRC32 crc=new CRC32();for(int word:w)for(int b=0;b<4;b++)crc.update(word>>(8*b));crc32=crc.getValue();
        }
        int skipped(){return blackKeys+outside+percussion;}
        String summary(){
            String s=notes+" 个可演奏音符 · "+words.length+" / 512 个事件 · "+String.format(Locale.US,"%.2f",durationCs/100.0)+" 秒";
            if(skipped()>0)s+="\n将略过 "+blackKeys+" 个半音、"+outside+" 个越界音、"+percussion+" 个打击乐音符";
            return s;
        }
    }
    private static final class Cursor {
        final byte[] data;final int end;int pos;
        Cursor(byte[] bytes,int start,int end){data=bytes;pos=start;this.end=end;}
        int u8()throws IOException{if(pos>=end)throw new IOException("MIDI 文件提前结束");return data[pos++]&255;}
        int u16()throws IOException{return (u8()<<8)|u8();}
        long u32()throws IOException{return ((long)u16()<<16)|u16();}
        long vlq()throws IOException{
            long n=0;
            for(int i=0;i<4;i++){int b=u8();n=(n<<7)|(b&127);if((b&128)==0)return n;}
            throw new IOException("MIDI 可变长数值超过 4 字节");
        }
        int size(long n)throws IOException{if(n<0 || n>end-pos)throw new IOException("MIDI 区块长度无效");return (int)n;}
        byte[] bytes(int n)throws IOException{size(n);byte[] out=Arrays.copyOfRange(data,pos,pos+n);pos+=n;return out;}
        void skip(long n)throws IOException{pos+=size(n);}
    }
    static Song read(InputStream in)throws IOException{
        ByteArrayOutputStream all=new ByteArrayOutputStream();byte[] chunk=new byte[8192];int n;
        while((n=in.read(chunk))!=-1){if(all.size()+n>MAX_BYTES)throw new IOException("MIDI 文件超过 2 MB，请选较短的曲目");all.write(chunk,0,n);}
        return parse(all.toByteArray());
    }
    static Song parse(byte[] bytes)throws IOException{
        if(bytes.length>MAX_BYTES)throw new IOException("MIDI 文件超过 2 MB");
        Cursor c=new Cursor(bytes,0,bytes.length);
        if(c.u32()!=0x4d546864L)throw new IOException("请选择标准 MIDI 文件（.mid 或 .midi）");
        int header=c.size(c.u32());if(header<6)throw new IOException("MIDI 文件头不完整");
        int format=c.u16(),count=c.u16(),division=c.u16();c.skip(header-6);
        if(format>1)throw new IOException("暂支持 MIDI 格式 0 和 1，请先导出为格式 1");
        if((division&0x8000)!=0)throw new IOException("暂不支持 SMPTE 时间制，请导出为节拍时间制 MIDI");
        if(division==0 || count<1 || count>128 || (format==0 && count!=1))throw new IOException("MIDI 音轨数或节拍分辨率无效");
        List<Track> tracks=new ArrayList<>();List<Event> events=new ArrayList<>();
        while(tracks.size()<count){
            long tag=c.u32();int length=c.size(c.u32());int stop=c.pos+length;
            if(tag!=0x4d54726bL){c.pos=stop;continue;}
            Track track=new Track(tracks.size());tracks.add(track);
            parseTrack(new Cursor(bytes,c.pos,stop),track,events);c.pos=stop;
        }
        Collections.sort(events,(a,b)->{
            int time=Long.compare(a.tick,b.tick);if(time!=0)return time;
            int track=Integer.compare(a.track,b.track);return track!=0?track:Integer.compare(a.order,b.order);
        });
        return new Song(division,tracks,events);
    }
    private static void parseTrack(Cursor c,Track track,List<Event> out)throws IOException{
        long tick=0;int running=0,order=0;
        while(c.pos<c.end){
            tick+=c.vlq();if(tick>0x7fffffffL)throw new IOException("MIDI 时间长度超出支持范围");
            int first=c.u8(),status=first;boolean hasData=first<128;
            if(hasData){if(running==0)throw new IOException("MIDI running status 缺少状态字");status=running;}
            if(status==0xff){
                running=0;int type=c.u8();int len=c.size(c.vlq());
                if(type==0x51){
                    if(len!=3)throw new IOException("MIDI 速度事件长度错误");
                    int us=(c.u8()<<16)|(c.u8()<<8)|c.u8();if(us==0)throw new IOException("MIDI 速度不能为零");
                    out.add(new Event(tick,track.index,order++,0,0,0,us));
                }else if(type==3){byte[] text=c.bytes(len);track.name=new String(text,StandardCharsets.UTF_8).replaceAll("[\\p{Cntrl}]"," ").trim();if(track.name.length()>60)track.name=track.name.substring(0,60);}
                else if(type==0x2f){if(len!=0)throw new IOException("MIDI 结束事件长度错误");c.pos=c.end;break;}
                else c.skip(len);
            }else if(status==0xf0 || status==0xf7){running=0;c.skip(c.vlq());}
            else if(status>=0x80 && status<=0xef){
                running=status;int kind=status>>4,a=hasData?first:c.u8(),b=(kind==12 || kind==13)?0:c.u8();
                if(a>=128 || b>=128)throw new IOException("MIDI 音符数据无效");
                if(kind==8 || kind==9){if(kind==9 && b>0)track.notes++;out.add(new Event(tick,track.index,order++,kind==9&&b>0?1:2,status&15,a,b));}
                else if(kind==11)out.add(new Event(tick,track.index,order++,3,status&15,a,b));
            }else throw new IOException("MIDI 包含不支持的系统事件");
            if(out.size()>MAX_EVENTS)throw new IOException("MIDI 事件过多，请选择较短的曲目");
        }
        track.endTick=tick;
    }
    private static final class Tempo {
        final List<Long> ticks=new ArrayList<>();final List<Double> micros=new ArrayList<>();final List<Integer> rates=new ArrayList<>();final int division;
        Tempo(Song s){
            division=s.division;long tick=0;double us=0;int rate=500000;
            ticks.add(0L);micros.add(0.0);rates.add(rate);
            for(Event e:s.events)if(e.kind==0){
                us+=(e.tick-tick)*(double)rate/division;tick=e.tick;rate=e.value;
                if(ticks.get(ticks.size()-1)==tick){micros.set(micros.size()-1,us);rates.set(rates.size()-1,rate);}
                else{ticks.add(tick);micros.add(us);rates.add(rate);}
            }
        }
        int cs(long tick)throws IOException{
            int lo=0,hi=ticks.size();
            while(lo+1<hi){int mid=(lo+hi)/2;if(ticks.get(mid)<=tick)lo=mid;else hi=mid;}
            double value=(micros.get(lo)+(tick-ticks.get(lo))*(double)rates.get(lo)/division)/10000.0;
            if(Double.isNaN(value) || Double.isInfinite(value) || value>65534.49)throw new IOException("所选音轨超过 655 秒，请先截取一段");
            return (int)Math.round(value);
        }
    }
    private static final class Held {
        final long start;final int channel,key;
        Held(Event e){start=e.tick;channel=e.channel;key=e.key;}
    }
    private static final class Span {
        final long start,end;final int key;
        Span(Held n,long e){start=n.start;end=Math.max(n.start,e);key=n.key;}
    }
    private static final class Change {
        final int time,key,delta;
        Change(int t,int k,int d){time=t;key=k;delta=d;}
    }
    static int whiteIndex(int midi){
        int delta=midi-36;if(delta<0)return -1;
        for(int i=0;i<WHITE.length;i++)if(delta%12==WHITE[i]){int key=delta/12*7+i;return key<32?key:-1;}
        return -1;
    }
    static Compiled compile(Song song,int selected)throws IOException{
        if(selected<0 || selected>=song.tracks.size())throw new IOException("请选择音轨");
        Tempo tempo=new Tempo(song);Track track=song.tracks.get(selected);
        Map<Integer,ArrayDeque<Held>> held=new HashMap<>();List<Held> sustained=new ArrayList<>();List<Span> spans=new ArrayList<>();
        boolean[] pedal=new boolean[16];int black=0,outside=0,drums=0,playable=0;
        for(Event e:song.events){
            if(e.kind==3){
                if(e.key==64){
                    boolean next=e.value>=64;
                    if(pedal[e.channel] && !next)releaseSustain(sustained,spans,e.channel,e.tick);
                    pedal[e.channel]=next;
                }else if(e.key==120 || e.key==123){
                    for(Iterator<Map.Entry<Integer,ArrayDeque<Held>>> it=held.entrySet().iterator();it.hasNext();){
                        Map.Entry<Integer,ArrayDeque<Held>> a=it.next();
                        if((a.getKey()>>8)==e.channel){for(Held n:a.getValue())spans.add(new Span(n,e.tick));it.remove();}
                    }
                    releaseSustain(sustained,spans,e.channel,e.tick);
                }else if(e.key==121){pedal[e.channel]=false;releaseSustain(sustained,spans,e.channel,e.tick);}
                continue;
            }
            if(e.track!=selected || (e.kind!=1 && e.kind!=2))continue;
            if(e.channel==9){if(e.kind==1)drums++;continue;}
            if(e.key<36 || e.key>89){if(e.kind==1)outside++;continue;}
            if(whiteIndex(e.key)<0){if(e.kind==1)black++;continue;}
            int id=(e.channel<<8)|e.key;
            ArrayDeque<Held> q=held.get(id);
            if(e.kind==1){if(q==null){q=new ArrayDeque<>();held.put(id,q);}q.addLast(new Held(e));playable++;}
            else if(q!=null && !q.isEmpty()){
                Held n=q.removeFirst();if(pedal[e.channel])sustained.add(n);else spans.add(new Span(n,e.tick));
                if(q.isEmpty())held.remove(id);
            }
        }
        long end=track.endTick;
        for(ArrayDeque<Held> q:held.values())for(Held n:q)spans.add(new Span(n,end));
        for(Held n:sustained)spans.add(new Span(n,end));
        if(spans.isEmpty())throw new IOException("所选音轨没有 C2～F6 白键音符（半音 "+black+"，越界 "+outside+"，打击乐 "+drums+"）");
        List<Change> changes=new ArrayList<>();
        for(Span n:spans){
            int start=tempo.cs(n.start),stop=Math.max(start+1,tempo.cs(n.end));
            if(stop>65534)throw new IOException("曲目结束超过 655 秒");
            changes.add(new Change(start,whiteIndex(n.key),1));changes.add(new Change(stop,whiteIndex(n.key),-1));
        }
        Collections.sort(changes,(a,b)->{int time=Integer.compare(a.time,b.time);return time!=0?time:Integer.compare(a.delta,b.delta);});
        int[] counts=new int[32];List<Integer> words=new ArrayList<>();int last=0;
        for(int pos=0;pos<changes.size();){
            int at=changes.get(pos).time;int[] starts=new int[32],ends=new int[32];
            while(pos<changes.size() && changes.get(pos).time==at){
                Change c=changes.get(pos++);if(c.delta>0)starts[c.key]++;else ends[c.key]++;
            }
            for(int key=0;key<32;key++){
                int before=counts[key],after=before-ends[key]+starts[key];
                if(after<0)throw new IOException("MIDI 音符结束顺序无效");
                if(before>0 && (after==0 || (ends[key]==before && starts[key]>0)))words.add(event(at,key,false,selected%4));
                if(starts[key]>0)words.add(event(at,key,true,selected%4));
                counts[key]=after;
            }
            last=at;
        }
        if(words.size()>GuideProtocol.CAPACITY)throw new IOException("所选音轨需要 "+words.size()+" 个事件，板卡上限 512。请选择较短曲目或另一条旋律音轨");
        int duration=Math.max(last+1,tempo.cs(track.endTick));
        int[] data=new int[words.size()];for(int i=0;i<data.length;i++)data[i]=words.get(i);
        return new Compiled(data,duration,selected,playable,black,outside,drums);
    }
    private static void releaseSustain(List<Held> held,List<Span> spans,int channel,long time){
        for(Iterator<Held> i=held.iterator();i.hasNext();){Held n=i.next();if(n.channel==channel){spans.add(new Span(n,time));i.remove();}}
    }
    static int event(int time,int key,boolean on,int palette){return time|(key<<16)|(on?1<<21:0)|(palette<<22);}
}
