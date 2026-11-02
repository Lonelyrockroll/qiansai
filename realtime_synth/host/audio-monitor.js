'use strict';
(() => {
const N=4096, DELAY=16, $=id=>document.getElementById(id);
const block=new Float32Array(N), re=new Float64Array(N), im=new Float64Array(N);
const db=new Float64Array(N/2+1), magnitude=new Float64Array(N/2+1), win=Float64Array.from({length:N},(_,i)=>.5-.5*Math.cos(2*Math.PI*i/(N-1)));
const gain=win.reduce((a,b)=>a+b,0), Floor=-120;
const title=$('status'), detail=$('detail'), metrics=$('metrics');
let context=null, stream=null, source=null, analyser=null, raf=0, generation=0, lastDraw=0, active=false, pending=false;
function controls(){
  $('list').disabled=active||pending;$('device').disabled=active||pending;
  $('start').disabled=active||pending||!$('device').value;$('stop').disabled=!active&&!pending;
  $('demoStart').disabled=active||pending;$('file').disabled=active||pending;
}
function stop(message='已停止 · 保留最后一帧'){
  generation++;cancelAnimationFrame(raf);
  if(stream)for(const t of stream.getTracks())t.stop();
  if(source && typeof source.stop==='function'){try{source.stop()}catch{}}
  if(context && context.state!=='closed')context.close().catch(()=>{});
  context=null;stream=null;source=null;analyser=null;active=false;pending=false;
  title.textContent=message;controls();
}
function error(e){stop(e?.message||String(e));}
function begin(){stop('正在准备…');pending=true;controls();return generation;}
function liveAPI(){if(!navigator.mediaDevices?.getUserMedia)throw Error('请用新版浏览器打开 localhost 或 127.0.0.1 的上位机地址');}
async function listInputs(){
  const id=begin();let temporary=null;
  try{
    liveAPI();temporary=await navigator.mediaDevices.getUserMedia({audio:true});
    const devices=await navigator.mediaDevices.enumerateDevices();if(id!==generation)return;
    const select=$('device');select.replaceChildren(new Option('请选择输入设备',''));
    for(const d of devices.filter(d=>d.kind==='audioinput'))select.add(new Option(d.label||'未命名音频输入',d.deviceId));
    pending=false;title.textContent=select.length>1?'设备已列出 · 请选择声卡输入':'未发现可用的录音设备';controls();
  }catch(e){if(id===generation)error(e);}
  finally{if(temporary)for(const t of temporary.getTracks())t.stop();}
}
function openContext(){const AC=window.AudioContext||window.webkitAudioContext;if(!AC)throw Error('此浏览器不支持 Web Audio');return new AC({latencyHint:'interactive'});}
function connectGraph(node,kind,label,fileRate,decodedRate){
  source=node;const mono=context.createGain();mono.channelCount=1;mono.channelCountMode='explicit';
  analyser=context.createAnalyser();analyser.fftSize=N;analyser.smoothingTimeConstant=0;
  const silent=context.createGain();silent.gain.value=0;source.connect(mono);mono.connect(analyser);analyser.connect(silent);silent.connect(context.destination);
  pending=false;active=true;title.textContent=kind+' · '+label;
  detail.textContent=`浏览器分析 Fs ${context.sampleRate} Hz，窗长 ${(1000*N/context.sampleRate).toFixed(2)} ms，FFT 间隔 ${(context.sampleRate/N).toFixed(3)} Hz/bin。`;
  if(fileRate){detail.textContent+=` WAV 文件头 ${fileRate} Hz，浏览器解码后 ${decodedRate} Hz。`;detail.dataset.fileRate=String(fileRate);}else delete detail.dataset.fileRate;
  if(stream){const settings=stream.getAudioTracks()[0].getSettings();if(settings.sampleRate)detail.textContent+=` 驱动报告输入 ${settings.sampleRate} Hz。`;}
  controls();lastDraw=-Infinity;raf=requestAnimationFrame(draw);
}
function wavHeaderRate(bytes){
  const view=new DataView(bytes);
  if(view.byteLength<12 || view.getUint32(0)!==0x52494646 || view.getUint32(8)!==0x57415645)return null;
  for(let offset=12;offset+8<=view.byteLength;){
    const id=view.getUint32(offset),size=view.getUint32(offset+4,true),start=offset+8;
    if(size>view.byteLength-start)return null;
    if(id===0x666d7420 && size>=16)return view.getUint32(start+4,true);
    offset=start+size+(size%2);
  }
  return null;
}
async function startInput(){
  const selected=$('device').value;if(!selected)return;
  const id=begin();let acquired=null;
  try{
    liveAPI();context=openContext();await context.resume();if(id!==generation)return;
    acquired=await navigator.mediaDevices.getUserMedia({audio:{deviceId:{exact:selected},echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
    if(id!==generation){acquired.getTracks().forEach(t=>t.stop());return;}
    stream=acquired;const track=stream.getAudioTracks()[0];track.onended=()=>{if(id===generation)stop('输入设备已断开');};
    connectGraph(context.createMediaStreamSource(stream),'电脑音频输入',track.label||$('device').selectedOptions[0].text);
  }catch(e){if(id===generation)error(e);}
}
async function startFile(file){
  const id=begin();
  try{
    context=openContext();await context.resume();if(id!==generation)return;
    let bytes,label;
    if(file){if(file.size>20*1024*1024)throw Error('本地 WAV 请小于 20 MB');bytes=await file.arrayBuffer();label=file.name;}
    else{
      label=$('demo').value;const response=await fetch('/api/audio-monitor/demo?name='+encodeURIComponent(label),{headers:{'X-Synth-Token':MONITOR_TOKEN}});
      if(!response.ok)throw Error('实板归档不可用或校验失败');bytes=await response.arrayBuffer();
    }
    if(id!==generation)return;
    const fileRate=wavHeaderRate(bytes),buffer=await context.decodeAudioData(bytes);if(id!==generation)return;
    const node=context.createBufferSource();node.buffer=buffer;node.loop=true;
    connectGraph(node,'文件循环回放',label,fileRate,buffer.sampleRate);node.start();
  }catch(e){if(id===generation)error(e);}
  finally{$('file').value='';}
}
function fft(){
  let mean=0;for(const v of block)mean+=v;mean/=N;
  for(let i=0;i<N;i++){re[i]=(block[i]-mean)*win[i];im[i]=0;}
  for(let i=1,j=0;i<N;i++){let k=N>>1;for(;j&k;k>>=1)j^=k;j^=k;if(i<j){const v=re[i];re[i]=re[j];re[j]=v;}}
  for(let size=2;size<=N;size*=2){
    const angle=-2*Math.PI/size,cs=Math.cos(angle),sn=Math.sin(angle);
    for(let start=0;start<N;start+=size){let wr=1,wi=0;
      for(let j=0;j<size/2;j++){const a=start+j,b=a+size/2,br=wr*re[b]-wi*im[b],bi=wr*im[b]+wi*re[b];
        re[b]=re[a]-br;im[b]=im[a]-bi;re[a]+=br;im[a]+=bi;const next=wr*cs-wi*sn;wi=wr*sn+wi*cs;wr=next;}
    }
  }
  let max=-Infinity;
  for(let k=0;k<db.length;k++){const factor=(k===0||k===N/2)?1:2;magnitude[k]=Math.hypot(re[k],im[k]);db[k]=Math.max(Floor,20*Math.log10(factor*magnitude[k]/gain));if(k)max=Math.max(db[k],max);}
  const threshold=Math.max(max-Number($('threshold').value),20*Math.log10(1/32768)),peaks=[];
  for(let k=1;k<db.length;k++)if(db[k]>=threshold && magnitude[k]>magnitude[k-1] && (k===db.length-1 || magnitude[k]>=magnitude[k+1]))peaks.push(k);
  return peaks;
}
function axis(id,x0,x1,y0,y1,xUnit,yUnit){
  const c=$(id),d=Math.min(devicePixelRatio||1,2),w=Math.max(170,c.clientWidth),h=Math.max(120,c.clientHeight);
  if(c.width!==Math.round(w*d)||c.height!==Math.round(h*d)){c.width=Math.round(w*d);c.height=Math.round(h*d);}
  const g=c.getContext('2d');g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,w,h);
  const innerW=id==='xy'?Math.min(w-58,h-42):w-58, innerH=id==='xy'?innerW:h-42;
  const left=43+(w-58-innerW)/2;
  const x=v=>left+innerW*(v-x0)/(x1-x0),y=v=>h-28-innerH*(v-y0)/(y1-y0);
  const fmt=v=>Math.abs(v)>=20?v.toFixed(0):v.toFixed(Math.abs(x1-x0)<2?2:1);
  g.font='11px system-ui';g.lineWidth=.7;g.strokeStyle='#38505b';g.fillStyle='#adbec5';
  for(let i=0;i<=4;i++){const xv=x0+(x1-x0)*i/4,yv=y0+(y1-y0)*i/4;
    g.beginPath();g.moveTo(x(xv),y(y0));g.lineTo(x(xv),y(y1));g.moveTo(x(x0),y(yv));g.lineTo(x(x1),y(yv));g.stroke();
    g.textAlign='center';g.fillText(fmt(xv),x(xv),h-12);g.textAlign='right';g.fillText(Math.abs(y1-y0)<2?yv.toFixed(2):Math.round(yv),39,y(yv)+3);}
  g.textAlign='right';g.fillText(xUnit,w-1,h-1);g.textAlign='left';g.fillText(yUnit,2,10);
  return {g,x,y};
}
function line(panel,count,points,colour){const {g,x,y}=panel;g.beginPath();g.lineWidth=1.2;g.strokeStyle=colour;
  for(let i=0;i<count;i++){const [a,b]=points(i);if(i)g.lineTo(x(a),y(b));else g.moveTo(x(a),y(b));}g.stroke();}
function render(fs){
  analyser.getFloatTimeDomainData(block);const peaks=fft();let abs=0,energy=0;
  for(const v of block){abs=Math.max(abs,Math.abs(v));energy+=v*v;}const limit=Math.max(.004,abs*1.06);
  line(axis('wave',0,1000*(N-1)/fs,-limit,limit,'ms','幅度'),N,i=>[1000*i/fs,block[i]],'#7ce2c3');
  line(axis('xy',-limit,limit,-limit,limit,'x[n]','x[n−16]'),N-DELAY,i=>[block[i+DELAY],block[i]],'#ecac83');
  for(const [id,stopHz] of [['full',fs/2],['zoom',Math.min(4000,fs/2)]]){
    const p=axis(id,0,stopHz/1000,Floor,0,'kHz','dBFS');line(p,Math.min(db.length,Math.floor(stopHz*N/fs)+1),i=>[i*fs/N/1000,Math.min(0,db[i])],'#7db4ef');
    p.g.fillStyle='#ffc080';for(const k of peaks)if(k*fs/N<=stopHz){p.g.beginPath();p.g.arc(p.x(k*fs/N/1000),p.y(Math.min(0,db[k])),2.4,0,2*Math.PI);p.g.fill();}
  }
  const delayMs=1000*DELAY/fs;
  metrics.textContent=`峰值 ${abs.toFixed(4)} · RMS ${Math.sqrt(energy/N).toFixed(4)} · 本窗过阈值峰 ${peaks.length} · XY 延时 ${delayMs.toFixed(3)} ms · Hann 窗。谱峰达到最强非直流频点 −${$('threshold').value} dB 且大于等于 1/32768 满幅。`;
  metrics.dataset.peaks=String(peaks.length);metrics.dataset.bins=peaks.join(',');metrics.dataset.rate=String(fs);metrics.dataset.xyDelayMs=String(delayMs);
}
function draw(now){if(!active)return;if(now-lastDraw>=65){render(context.sampleRate);lastDraw=now;}raf=requestAnimationFrame(draw);}
$('list').onclick=listInputs;$('start').onclick=startInput;$('stop').onclick=()=>stop();$('device').onchange=controls;
$('demoStart').onclick=()=>startFile(null);$('file').onchange=()=>{if($('file').files[0])startFile($('file').files[0]);};
addEventListener('pagehide',()=>stop());controls();
})();
