'use strict';
(() => {
const $ = id => document.getElementById(id);
const SEGMENTS = {
  'hall-headphone': ['霍尔越阈', '耳机口起音'],
  'hall-speaker-leg': ['霍尔越阈', '喇叭功放单端起音'],
  'fixed-adc-speaker-leg': ['固定 H15 · U1 越阈', '功放单端起音'],
  'mark-headphone': ['FPGA MARK 起始边沿', '耳机口起音'],
  'hall-mark': ['霍尔越阈', 'FPGA MARK 起始边沿'],
};
const state = {
  catalog: {digital: [], scope: [], audio: []}, tab: 'digital', busy: false, loaded: false,
  selected: {digital: '', scope: '', audio: ''}, zoom: {digital: false, scope: false},
  csv: null, fileGeneration: 0, priorPairedThreshold: '',
};
const number = v => typeof v === 'number' && Number.isFinite(v);
const fmt = (v, digits=3) => number(v) ? new Intl.NumberFormat('zh-CN',{maximumFractionDigits:digits}).format(v) : '—';
const display = (v, empty='未注明') => v === 0 || v ? String(v) : empty;
const make = (tag, text, cl='') => {
  const node = document.createElement(tag);
  if (cl) node.className = cl;
  if (text !== undefined) node.textContent = text;
  return node;
};
function stable(value) {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}
function keyName(row) {
  const name = display(row.key);
  return (/^H\d+\b/i.exec(name) || [name])[0].toUpperCase();
}
const isMarker = row => row.segment === 'mark-i2s' || Array.isArray(row.trigger_v);
function identity(row, type) {
  if (!row) return '';
  if (row.raw_url || row.wav_url) return String(row.raw_url || row.wav_url);
  return stable([type,row.name,row.version,row.key,row.sequence,row.us,row.source,row.read_at,row.fs,row.duration_s]);
}
function selectRecord(type, rows) {
  let current=rows.find(row => identity(row,type) === state.selected[type]);
  if(!current && type==='digital'){
    current=rows.find(isMarker) || rows.filter(r=>r.read_at).sort((a,b)=>String(b.read_at).localeCompare(String(a.read_at)))[0];
  }
  if(!current && type==='audio')current=rows.find(r=>String(r.kind||'').startsWith('live'));
  current=current || rows[0];
  state.selected[type] = identity(current,type);
  return current;
}
function options(select, rows, type, label) {
  const chosen = selectRecord(type,rows);
  select.replaceChildren(...rows.map(row => new Option(label(row), identity(row,type))));
  select.disabled = !chosen;
  if (!chosen) select.add(new Option('暂无记录',''));
  select.value = state.selected[type];
  return chosen;
}
function unique(rows, id) {
  const keys = new Set();
  return rows.filter((row,i) => {
    const key = id(row,i);
    if (keys.has(key)) return false;
    keys.add(key);
    return true;
  });
}
function stats(values) {
  const sorted = values.filter(number).sort((a,b) => a-b);
  if (!sorted.length) return {n:0};
  const n=sorted.length, mid=n>>1;
  return {n,min:sorted[0],max:sorted[n-1],
    median: n%2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2,
    p95: sorted[Math.ceil(.95*n)-1], span:n>1?sorted[n-1]-sorted[0]:null};
}
function digitalPeers(row) {
  const rows = state.catalog.digital.filter(v => number(v.us) && v.us>=0 &&
    v.version===row.version && keyName(v)===keyName(row) && isMarker(v)===isMarker(row));
  if(!row.version || !row.key || /未标注|未核实/.test(row.version) || String(row.key).includes('未标注'))return [row];
  if (isMarker(row)) {
    if (!row.csv_sha256 || !number(row.threshold_v) || !row.version || !row.key ||
        String(row.version).includes('未标注') || String(row.key).includes('未标注')) return [row];
    return unique([row,...rows.filter(v=>v.threshold_v===row.threshold_v && v.csv_sha256 && v.condition===row.condition)],
      v=>v.csv_sha256);
  }
  // Each LAST I2S read describes one event. The sequence is an event tag, never a weight.
  return unique([row,...rows], eventIdentity);
}
function eventIdentity(row) {
  return !isMarker(row) && number(row.sequence) ?
    stable([row.version,keyName(row),row.session||'',row.sequence,row.us]) : identity(row,'digital');
}
function scopePeers(row) {
  if (!row.condition || !row.csv_sha256 || !row.settings) return [row];
  const settings = stable(row.settings);
  return unique([row,...state.catalog.scope.filter(v => number(v.delay_ms) && v.delay_ms>=0 && v.segment===row.segment &&
    v.condition===row.condition && v.csv_sha256 && stable(v.settings)===settings)], v=>v.csv_sha256);
}
function sameOriginURL(raw) {
  if (!raw) return null;
  try {
    const url = new URL(raw,location.origin);
    return url.origin===location.origin && (url.protocol==='http:' || url.protocol==='https:') ? url.href : null;
  } catch {return null;}
}
function showNotice(text, bad=false) {
  const node=$('notice');node.hidden=!text;node.textContent=text;node.classList.toggle('error',bad);
}
function summary(id, value, unit, caption) {
  const node=$(id+'-summary');node.replaceChildren(document.createTextNode(value));
  if (unit) node.append(make('small',unit));
  $(id+'-summary-detail').textContent=caption;
}
function runCard(id, value, unit, from, to, values=[]) {
  const root=$(id);root.replaceChildren();
  const parts=[['本次延迟',value,unit],['起点 T₀',from,values[0]],['终点 T₁',to,values[1]]];
  for (const [i,part] of parts.entries()) {
    const box=make('div'), title=make('span',part[0],'run-label'), strong=make('strong',part[1],i===0?'value':'');
    box.append(title,strong);
    if (part[2]) {
      if (i===0) strong.append(make('small',' '+part[2]));
      else box.append(make('small',part[2]));
    }
    root.append(box);
  }
}
function meta(id, pairs, raw) {
  const root=$(id);root.replaceChildren();
  for (const [label,value] of pairs) {
    if (value===null || value===undefined || value==='') continue;
    const dl=make('dl');dl.append(make('dt',label),make('dd',String(value)));root.append(dl);
  }
  const link=sameOriginURL(raw);
  if (link) {const a=make('a','下载原始 CSV');a.href=link;a.download='capture.csv';root.append(a);}
}
function metricPanel(id, rows, getValue, unit, note) {
  const root=$(id);root.replaceChildren();root.className='stats-area';
  const s=stats(rows.map(getValue));
  root.append(make('h3','同组统计 · '+s.n+' 次有效测量'),make('p',note));
  if (!s.n) return;
  if (s.n===1) {root.append(make('p','现有一条单次结果。增加同条件的独立动作后，才显示重复测量的分布。'));return;}
  const grid=make('div',undefined,'stat-grid');
  for (const [label,value] of [['最小',s.min],['中位数',s.median],['P95',s.p95],['最大',s.max],['极差',s.span]]) {
    const item=make('div',undefined,'stat-item'), strong=make('strong',fmt(value,5));
    strong.append(make('small',' '+unit));item.append(make('span',label,'metric-label'),strong);grid.append(item);
  }
  root.append(grid,make('p','P95 取排序后的第 ⌈0.95N⌉ 个值，极差为最大值减最小值。'));
}
function resultsTable(id,rows, getValue,unit) {
  if (!rows.length) return;
  const wrap=make('div',undefined,'table-wrap'),table=make('table'),head=make('thead'),tr=make('tr');
  table.append(make('caption','参与本组统计的单次记录'));
  ['记录','结果','来源'].forEach(v=>tr.append(make('th',v)));
  head.append(tr);table.append(head);const body=make('tbody');
  for (const row of rows) {
    const tr=make('tr');tr.append(make('td',display(row.name||row.key)),make('td',fmt(getValue(row),5)+' '+unit,'number'),make('td',display(row.source)));body.append(tr);
  }
  table.append(body);wrap.append(table);$(id).append(wrap);
}

// A shared horizontal scale and independent vertical scales keep a small audio onset legible.
const SVG='http://www.w3.org/2000/svg';
const colors=['#80e0be','#ffbb74'];
const plots=new WeakMap();
function svgElement(parent, tag, attrs, title) {
  const node=document.createElementNS(SVG,tag);
  for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value));
  if (title!==undefined) node.textContent=title;
  parent.append(node);return node;
}
function validSeries(times, tracks) {
  if (!Array.isArray(times) || times.length<2 || tracks.some(t=>!Array.isArray(t.y) || t.y.length!==times.length)) return false;
  let prev=-Infinity;
  for (let i=0;i<times.length;i++) {
    if (!number(times[i]) || times[i]<=prev || tracks.some(track=>!number(track.y[i]))) return false;
    prev=times[i];
  }
  return true;
}
function nearest(times,t) {
  let lo=0,hi=times.length-1;
  while (lo<hi) {const mid=(lo+hi)>>1;if(times[mid]<t) lo=mid+1;else hi=mid;}
  return lo && Math.abs(t-times[lo-1])<Math.abs(times[lo]-t)?lo-1:lo;
}
function sparseIndices(times, values, lo, hi, x) {
  const start=Math.max(0,nearest(times,lo)-1), end=Math.min(times.length-1,nearest(times,hi)+1);
  const result=[];let bucket=-Infinity,min=start,max=start,first=start;
  function finish(last) {
    const points=Array.from(new Set([first,min,max,last])).sort((a,b)=>a-b);
    result.push(...points);
  }
  for (let i=start;i<=end;i++) {
    const b=Math.floor(x(times[i]));
    if (b!==bucket) {if(bucket!==-Infinity)finish(i-1);bucket=b;first=min=max=i;}
    if(values[i]<values[min])min=i;if(values[i]>values[max])max=i;
  }
  finish(end);return result;
}
function draw(plotId,times,tracks,marks,zoom,xUnit) {
  const svg=$(plotId),readout=$(plotId.replace('-plot','-readout'));
  svg.replaceChildren();plots.delete(svg);
  const width=Math.max(270,Math.round(svg.clientWidth||720));
  const height=svg.closest('dialog[open]')?Math.max(240,Math.min(840,window.innerHeight-210)):52+tracks.length*112;
  const rowHeight=(height-52)/tracks.length;
  svg.setAttribute('viewBox','0 0 '+width+' '+height);svg.setAttribute('height',height);
  const left=width<480?50:66,right=width-16,top=26;
  if (!validSeries(times,tracks)) {
    svgElement(svg,'text',{x:18,y:52,fill:'#e2ece4'},'本条记录未提供可绘制的等长时间与波形数组。');
    readout.textContent='波形待采集';return;
  }
  let lo=times[0],hi=times[times.length-1];
  const markers=marks.filter(m=>number(m.t)&&m.t>=lo&&m.t<=hi);
  if (zoom && markers.length===2) {
    const a=Math.min(markers[0].t,markers[1].t),b=Math.max(markers[0].t,markers[1].t);
    const near=nearest(times,a), sample=Math.max(times[Math.min(near+1,times.length-1)]-times[Math.max(near-1,0)],Number.EPSILON);
    const pad=Math.max((b-a)*.45,3*sample,(hi-lo)/1500);
    lo=Math.max(lo,a-pad);hi=Math.min(hi,b+pad);
  }
  const x=t=>left+(t-lo)/(hi-lo)*(right-left);
  const steps=width<480?3:5;
  for(let i=0;i<=steps;i++){
    const px=left+i*(right-left)/steps,t=lo+i*(hi-lo)/steps;
    svgElement(svg,'line',{x1:px,y1:top,x2:px,y2:height-31,stroke:'#334d44','stroke-width':.75});
    svgElement(svg,'text',{x:px,y:height-13,fill:'#b7cdc0','text-anchor':i===0?'start':i===steps?'end':'middle'},fmt(t, xUnit==='ms'?5:3)+' '+xUnit);
  }
  tracks.forEach((track,i)=>{
    const base=top+i*rowHeight+18,end=base+rowHeight-35;
    const indices=sparseIndices(times,track.y,lo,hi,x);
    let min=Infinity,max=-Infinity;
    for(const k of indices){min=Math.min(min,track.y[k]);max=Math.max(max,track.y[k]);}
    const pad=Math.max((max-min)*.06,Math.abs(min)*.002,track.unit==='V'?.0001:.00001);
    min-=pad;max+=pad;
    const y=v=>end-(v-min)/(max-min)*(end-base);
    svgElement(svg,'text',{x:left,y:base-7,fill:colors[i]},track.name);
    for (let n=0;n<=2;n++){
      const value=min+(max-min)*n/2,py=y(value);
      svgElement(svg,'line',{x1:left,y1:py,x2:right,y2:py,stroke:'#344c43','stroke-width':.75});
      svgElement(svg,'text',{x:left-5,y:py+4,fill:'#b7cdc0','text-anchor':'end'},fmt(value,4));
    }
    for(const value of track.thresholds||[]){
      if(!number(value) || value<min || value>max)continue;
      const line=svgElement(svg,'line',{x1:left,x2:right,y1:y(value),y2:y(value),stroke:colors[i],opacity:.65,'stroke-dasharray':'2 5','data-threshold':value});
      svgElement(line,'title',{},'电压门限 '+fmt(value,5)+' '+track.unit);
    }
    const group=svgElement(svg,'svg',{x:left,y:base,width:right-left,height:end-base,viewBox:'0 0 '+(right-left)+' '+(end-base),overflow:'hidden'});
    const path=indices.map((k,n)=>(n?'L':'M')+(x(times[k])-left).toFixed(2)+' '+(y(track.y[k])-base).toFixed(2)).join(' ');
    svgElement(group,'path',{d:path,fill:'none',stroke:colors[i],'stroke-width':1.7,'data-series':track.name});
  });
  markers.forEach((m,i)=>{
    const px=x(m.t);const where=(px<left+22)?'start':(px>right-22)?'end':i?'start':'end';
    svgElement(svg,'line',{x1:px,x2:px,y1:top-2,y2:height-30,stroke:colors[i],'stroke-width':1.6,'stroke-dasharray':i?'3 3':'7 3','data-marker':m.tag});
    svgElement(svg,'text',{x:px,y:i?22:13,fill:colors[i],'text-anchor':where},m.tag);
  });
  plots.set(svg,{times,tracks,lo,hi,left,right,width,xUnit,readout});
  readout.textContent=markers.length?'T₀ 与 T₁ 对应上方列出的起止时间，移动指针可查看同一时刻的采样值。':'移动指针查看录音时间和数字幅度。';
}
function hover(event) {
  const svg=event.currentTarget,v=plots.get(svg);if(!v)return;
  const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)*v.width/rect.width;
  if(px<v.left || px>v.right)return;
  const index=nearest(v.times,v.lo+(px-v.left)/(v.right-v.left)*(v.hi-v.lo));
  v.readout.textContent='t = '+fmt(v.times[index],6)+' '+v.xUnit+'　'+v.tracks.map(t=>t.name+' '+fmt(t.y[index],5)+' '+t.unit).join('　');
}
let expanded=null;
function openPlot(button) {
  if(expanded || state.busy)return;
  const tab=button.dataset.target,box=button.closest('.plot-box'), dialog=$('plot-dialog');
  const record=state.catalog[tab].find(row=>identity(row,tab)===state.selected[tab]);
  if(!record || !box)return;
  const place=document.createComment('plot position');box.before(place);dialog.append(box);
  expanded={place,box,button};
  $('dialog-title').textContent=tab==='scope'?SEGMENTS[record.segment].join(' → '):tab==='digital'?'J8-10 MARK 高脉宽':'声卡耳机波形';
  const duration=tab==='scope'?fmt(record.delay_ms,6)+' ms':tab==='digital'?fmt(record.us,4)+' µs':fmt(record.duration_s,3)+' s';
  const gates=tab==='scope' && record.settings?.trigger_reference==='absolute' ? absoluteGateLabels(record.settings).map(([name,value])=>name+' '+value).join(' / ') : '';
  $('dialog-detail').textContent=display(record.name)+' · '+duration+(gates?'　'+gates:'')+(tab==='digital' && record.quality_note?'　波形说明　'+record.quality_note:'');
  dialog.showModal();render();$('close-plot').focus();
}
function restorePlot() {
  if(!expanded)return;
  const {place,box,button}=expanded;expanded=null;place.replaceWith(box);render();button.focus();
}
function bounds(values, unit) {
  return Array.isArray(values) && values.length===2 && values.every(number) ? fmt(values[0],5)+' 至 '+fmt(values[1],5)+' '+unit : null;
}
function renderDigital() {
  const rows=state.catalog.digital.filter(r=>number(r.us)&&r.us>=0);
  const record=options($('digital-select'),rows,'digital',r=>display(r.name||r.key)+' · '+fmt(r.us)+' µs · '+display(r.version));
  $('digital-data').hidden=!record;$('digital-empty').hidden=!!record;
  summary('digital',record?fmt(record.us):'待测',record?'µs':'',record?display(record.key)+' · '+display(record.version):'接受琴键事件 → I²S 输出');
  if(!record)return;
  const marker=isMarker(record);
  runCard('digital-run',fmt(record.us,4),'µs',marker?'MARK 上升沿':'接受孤立琴键事件',marker?'MARK 下降沿':'非零 I²S 左字完整移出',
    [number(record.t0_ms)?fmt(record.t0_ms,6)+' ms':null, number(record.t1_ms)?fmt(record.t1_ms,6)+' ms':null]);
  meta('digital-meta',[['来源',display(record.source)],['琴键',display(record.key)],['码流',display(record.version)],['换算',fmt(record.us/1000,6)+' ms'],
    ['板内事件序号',number(record.sequence)?record.sequence:null],['读取时间',record.read_at],['MARK 门限',number(record.threshold_v)?fmt(record.threshold_v,4)+' V':null],
    ['采样分辨区间',bounds(record.bounds_us,'µs')]],record.raw_url);
  if(marker && typeof record.quality_note==='string' && record.quality_note.trim()){
    const description=make('p',undefined,'quality-note notice');
    Object.assign(description.style,{flexBasis:'100%',margin:'0',borderColor:'#b77434',background:'#f6efde',color:'#61421f'});
    description.append(make('strong','波形说明'),document.createTextNode('　'+record.quality_note.trim()));
    $('digital-meta').append(description);
  }
  $('digital-plot-box').hidden=!marker;
  if(marker && state.tab==='digital') draw('digital-plot',record.time_ms,[{name:'CH1 · MARK（V）',y:record.trigger_v,unit:'V',thresholds:[record.threshold_v]}],
    [{tag:'T₀',t:record.t0_ms},{tag:'T₁',t:record.t1_ms}],state.zoom.digital,'ms');
  const peers=digitalPeers(record);
  metricPanel('digital-stats',peers,r=>r.us,'µs',marker?'同键位、码流和绝对门限的 MARK 记录按 CSV 指纹去重。':'同键位、同码流的板内读数按事件序号与读数去重。板内累计序号不计入样本数。');
  resultsTable('digital-stats',peers,r=>r.us,'µs');
}
function absoluteGateLabels(settings) {
  const edge={falling:'下降',rising:'上升',either:''}[settings.direction] || '';
  return [['CH1 绝对'+edge+'门限',fmt(settings.trigger_threshold,6)+' V'],['CH2 相对静音门限',fmt(settings.audio_threshold,6)+' V']];
}
function renderScope() {
  const seg=$('scope-segment').value;
  for(const option of $('scope-segment').options){
    const count=state.catalog.scope.filter(r=>r.segment===option.value).length;
    option.text=SEGMENTS[option.value].join(' → ')+'（'+count+' 条）';
  }
  const rows=state.catalog.scope.filter(r=>r.segment===seg && number(r.delay_ms)&&r.delay_ms>=0);
  const record=options($('scope-select'),rows,'scope',r=>display(r.name)+' · '+fmt(r.delay_ms,5)+' ms');
  $('scope-data').hidden=!record;$('scope-empty').hidden=!!record;
  const names=SEGMENTS[seg];summary('scope',record?fmt(record.delay_ms,5):'待测',record?'ms':'',names.join(' → '));
  $('scope-empty-title').textContent=names.join(' → ')+' · 待测';if(!record)return;
  runCard('scope-run',fmt(record.delay_ms,6),'ms',names[0],names[1],[fmt(record.t0_ms,6)+' ms',fmt(record.t1_ms,6)+' ms']);
  const settings=record.settings||{}, condition=display(record.condition,'未标注');
  const absolute=settings.trigger_reference==='absolute';
  const gates=absolute?absoluteGateLabels(settings):[['CH1 / CH2 相对基线门限',number(settings.trigger_threshold)&&number(settings.audio_threshold)?fmt(settings.trigger_threshold,5)+' / '+fmt(settings.audio_threshold,5)+' V':null]];
  meta('scope-meta',[['来源',display(record.source)],['条件',condition],['采样分辨区间',bounds(record.bounds_ms,'ms')],['原始采样点',record.measurement?.sample_count],...gates,
    ['CSV 指纹',record.csv_sha256?record.csv_sha256.slice(0,12):null]],record.raw_url);
  $('scope-settings').hidden=!record.settings;
  const direction={rising:'上升',falling:'下降',either:'任一方向'};
  meta('scope-parameters',[['时间列',settings.time_column],['CH1 列',settings.trigger_column],['CH2 列',settings.audio_column],
    ['静止基线',bounds(settings.baseline,settings.time_unit||'')],['CH1 方向',direction[settings.direction]],
    ['CH1 / CH2 连续确认点数',number(settings.trigger_points)&&number(settings.audio_points)?settings.trigger_points+' / '+settings.audio_points:null]]);
  const m=record.measurement||{};
  const thresholds=(zero,level,direction)=>!number(zero)||!number(level)?[]:direction==='rising'?[zero+level]:direction==='falling'?[zero-level]:[zero-level,zero+level];
  if(state.tab==='scope')draw('scope-plot',record.time_ms,[{name:'CH1 · '+names[0]+'（V）',y:record.trigger_v,unit:'V',thresholds:absolute?[settings.trigger_threshold]:thresholds(m.trigger_baseline_v,settings.trigger_threshold,settings.direction)},
    {name:'CH2 · '+names[1]+'（V）',y:record.audio_v,unit:'V',thresholds:thresholds(m.audio_baseline_v,settings.audio_threshold,'either')}],
    [{tag:'T₀',t:record.t0_ms},{tag:'T₁',t:record.t1_ms}],state.zoom.scope,'ms');
  const peers=scopePeers(record);
  metricPanel('scope-stats',peers,r=>r.delay_ms,'ms','仅合并同一测量段、同一条件和同一分析参数的记录。相同 CSV 只计一次，未标注条件的记录单独展示。');
  resultsTable('scope-stats',peers,r=>r.delay_ms,'ms');
}
function renderAudio() {
  const rows=state.catalog.audio.filter(r=>r && typeof r==='object');
  const record=options($('audio-select'),rows,'audio',r=>display(r.name)+' · '+fmt(r.fs,1)+' Hz');
  $('audio-data').hidden=!record;$('audio-empty').hidden=!!record;
  summary('audio',record?String(rows.length):'待测',record?'份':'',record?'可查看耳机输出录音':'等待耳机输出录音');
  const media=$('audio-media');
  if(!record){media.replaceChildren();delete media.dataset.url;return;}
  const kind=String(record.kind||'');
  meta('audio-meta',[['记录',display(record.name)],['来源',display(record.source)],
    ['采集类别',kind.startsWith('historical')?'历史实录':kind.startsWith('live')?'本次采集':kind||null],
    ['采样率',number(record.fs)?fmt(record.fs,1)+' Hz':null],['通道',record.channel],
    ['录音时长',number(record.duration_s)?fmt(record.duration_s,4)+' s':null],['峰值',number(record.peak_dbfs)?fmt(record.peak_dbfs,2)+' dBFS':null]]);
  if(state.tab==='audio')draw('audio-plot',record.time_s,[{name:'耳机输出（FS）',y:record.samples,unit:'FS'}],[],false,'s');
  const url=sameOriginURL(record.wav_url)||'';
  if(media.dataset.url!==url){
    media.replaceChildren();media.dataset.url=url;
    if(url){
      const player=make('audio');player.controls=true;player.preload='none';player.src=url;
      const a=make('a','下载 WAV');a.href=url;a.download='capture.wav';media.append(player,a);
    }
  }
}
function render() {
  for (const tab of ['digital','scope','audio']) {
    $('panel-'+tab).hidden=state.tab!==tab;
    $('tab-'+tab).setAttribute('aria-pressed',String(state.tab===tab));
  }
  if(!state.loaded){
    for(const [tab,caption] of [['digital','接受琴键事件 → I²S 输出'],['scope','霍尔越阈 → 耳机口起音'],['audio','耳机口录音']]){
      summary(tab,'—','',caption);$(tab+'-data').hidden=true;$(tab+'-empty').hidden=true;
      if($(tab+'-select'))$(tab+'-select').disabled=true;
    }
    return;
  }
  renderDigital();renderScope();renderAudio();
  document.querySelectorAll('.zoom').forEach(button=>button.textContent=state.zoom[button.dataset.target]?'查看全窗':'放大起音');
}
function showTab(tab) {
  if(state.tab==='audio' && tab!=='audio') $('audio-media').querySelector('audio')?.pause();
  state.tab=tab;render();
}
async function api(path,method='GET',body) {
  const headers={'X-Synth-Token':document.querySelector('meta[name=session-token]').content};
  const init={method,headers,cache:'no-store',credentials:'same-origin'};
  if(body!==undefined){headers['Content-Type']='application/json';init.body=JSON.stringify(body);}
  const response=await fetch(path,init);
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'读取失败（HTTP '+response.status+'）');
  return data;
}
async function loadCatalog() {
  const body=await api('/api/latency/results');
  if(!body || !['digital','scope','audio'].every(k=>Array.isArray(body[k])))throw Error('记录目录不完整，请刷新重试。');
  state.catalog=body;state.loaded=true;
  $('updated').textContent='已刷新 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});
}
async function operate(task) {
  if(state.busy)return;
  state.busy=true;$('refresh').disabled=$('read-board').disabled=$('submit-csv').disabled=true;
  try{await task();}
  catch(e){
    $('updated').textContent=state.loaded?'操作失败，保留已载入记录':'记录目录未载入';
    showNotice(e.message||String(e),true);
  }
  finally{
    state.busy=false;$('refresh').disabled=$('read-board').disabled=$('submit-csv').disabled=false;render();
  }
}
function setGroupVisible(id, enabled) {
  const node=$(id);node.hidden=!enabled;
  node.querySelectorAll('input,select').forEach(input=>input.disabled=!enabled);
}
function setImportMode() {
  const seg=$('import-segment').value,marker=seg==='mark-i2s';
  setGroupVisible('paired-fields',!marker);setGroupVisible('audio-column-wrap',!marker);setGroupVisible('marker-fields',marker);
  $('trigger-label').textContent=marker?'MARK 绝对逻辑门限（V）':'CH1 动作门限（相对基线，V）';
  const level=$('trigger-level');
  if(marker){
    if(level.dataset.mode==='paired')state.priorPairedThreshold=level.value;
    level.value='1.5'; level.dataset.mode='marker';
  }else if(level.dataset.mode!=='paired'){
    level.value=state.priorPairedThreshold;level.dataset.mode='paired';
  }
  $('csv-help').textContent=marker?'MARK 的时间列和 CH1 列即可。记录需覆盖上升前、下降后的低电平。':'基线使用 CSV 的原时间单位，至少覆盖 3 个静止采样点。两路阈值填相对各自基线的电压变化量。';
}
function csvLine(text) {
  const cells=[];let field='',quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(c==='"'){if(quoted && text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}
    else if(c===',' && !quoted){cells.push(field.trim());field='';}
    else field+=c;
  }
  cells.push(field.trim());return cells;
}
function detectColumns(text) {
  const rows=text.replace(/^\ufeff/,'').slice(0,131072).split(/\r?\n/);
  for(const line of rows){
    const names=csvLine(line);
    const time=names.find(n=>/^(time|timestamp|second|时间|时刻)(?:$|[\s_[(])/i.test(n));
    if(!time || names.length<2 || new Set(names.filter(Boolean)).size!==names.filter(Boolean).length)continue;
    const rest=names.filter(n=>n && n!==time);
    const ch1=rest.find(n=>/^(CH1|HALL|MARK|TRIGGER)(?:$|[\s_[(])/i.test(n)) || rest[0];
    const ch2=rest.filter(n=>n!==ch1).find(n=>/^(CH2|OUT|AUDIO|HEADPHONE)(?:$|[\s_[(])/i.test(n)) || rest.find(n=>n!==ch1);
    const tagged=time.toLowerCase().match(/(?:^|[\s_[(])(ns|[uµμ]s|ms|s)(?:$|[\s)\]])/);
    return {names:names.filter(Boolean),time,ch1,ch2,unit:tagged?tagged[1].replace(/[µμ]/,'u'):null};
  }
  return null;
}
async function pickFile() {
  const generation=++state.fileGeneration,file=$('csv-file').files[0];
  state.csv=null;$('headers').replaceChildren();
  if(!file){$('import-status').textContent='';return;}
  try{
    if(file.size>24*1024*1024)throw Error('CSV 超过 24 MiB，请缩短采集窗口后再导出。');
    let text;
    try{text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer());}
    catch{throw Error('CSV 需使用 UTF-8 编码，请另存为 UTF-8 后重新导入。');}
    if(generation!==state.fileGeneration)return;
    const found=detectColumns(text);
    state.csv=text;$('record-name').value=file.name.slice(0,100);
    if(found){
      $('headers').replaceChildren(...found.names.map(n=>new Option(n,n)));
      $('time-column').value=found.time;$('trigger-column').value=found.ch1;
      if(found.ch2)$('audio-column').value=found.ch2;
      if(found.unit)$('time-unit').value=found.unit;
    }
    unitLabels();formStatus(found?'已识别表头，请核对列名与单位。':'已读取文件，请按 CSV 表头填写列名。');
  }catch(e){
    if(generation===state.fileGeneration){$('csv-file').value='';formStatus(e.message||String(e),true);}
  }
}
function formStatus(text,bad=false){const node=$('import-status');node.textContent=text;node.classList.toggle('error',bad);}
function unitLabels(){
  document.querySelectorAll('.time-unit-label').forEach(node=>node.textContent=$('time-unit').value==='us'?'µs':$('time-unit').value);
}
function uploadFields() {
  if(!state.csv)throw Error('请先选择并读入 CSV 文件。');
  const values=Object.fromEntries(new FormData($('csv-form')).entries());
  values.csv=state.csv;
  const marker=values.segment==='mark-i2s';
  const columns=[values.time_column,values.trigger_column,...(marker?[]:[values.audio_column])].map(s=>String(s||'').trim());
  if(columns.some(s=>!s) || new Set(columns).size!==columns.length)throw Error('时间列与电压列须填写不同的列名。');
  for(const key of ['trigger_threshold',...(marker?[]:['audio_threshold','baseline_from','baseline_to'])]){
    if(!String(values[key]??'').trim() || !Number.isFinite(Number(values[key])))throw Error('请完整填写数值参数。');
    values[key]=Number(values[key]);
  }
  if(values.trigger_threshold<=0 || (marker && values.trigger_threshold>=3.3) || (!marker && values.audio_threshold<=0))throw Error('电压门限须为正数，MARK 逻辑门限须低于 3.3 V。');
  if(!marker && values.baseline_from>=values.baseline_to)throw Error('静止基线起点须小于终点。');
  return values;
}
function init() {
  const requested=new URLSearchParams(location.search).get('segment');
  if(Object.hasOwn(SEGMENTS,requested)){
    state.tab='scope';$('scope-segment').value=requested;$('import-segment').value=requested;
  }
  for(const tab of ['digital','scope','audio']){
    $('tab-'+tab).addEventListener('click',()=>showTab(tab));
    $(tab+'-select').addEventListener('change',e=>{state.selected[tab]=e.target.value;render();});
    $(tab+'-plot').addEventListener('pointermove',hover);
  }
  $('scope-segment').addEventListener('change',()=>{state.selected.scope='';render();});
  document.querySelectorAll('.zoom').forEach(button=>button.addEventListener('click',()=>{
    const key=button.dataset.target;state.zoom[key]=!state.zoom[key];render();
  }));
  document.querySelectorAll('.expand-plot').forEach(button=>button.addEventListener('click',()=>openPlot(button)));
  $('close-plot').addEventListener('click',()=>$('plot-dialog').close());
  $('plot-dialog').addEventListener('close',restorePlot);
  document.querySelectorAll('.open-import').forEach(button=>button.addEventListener('click',()=>{
    $('import').open=true;$('import-segment').value=button.dataset.segment || $('scope-segment').value;setImportMode();$('import-segment').focus();
  }));
  $('refresh').addEventListener('click',()=>operate(async()=>{
    const tabs=['digital','scope','audio'], previous=Object.fromEntries(tabs.map(k=>[k,new Set(state.catalog[k].map(r=>identity(r,k)))]));
    await loadCatalog();
    const fresh=Object.fromEntries(tabs.map(k=>[k,state.catalog[k].filter(r=>!previous[k].has(identity(r,k)))]));
    const incoming=fresh[state.tab].filter(r=>state.tab!=='scope' || r.segment===$('scope-segment').value);
    if(incoming.length)state.selected[state.tab]=identity(incoming[incoming.length-1],state.tab);
    const count=tabs.reduce((total,k)=>total+fresh[k].length,0);
    showNotice(count?'记录已刷新，新增 '+count+' 条。':'记录已刷新。');
  }));
  $('read-board').addEventListener('click',()=>operate(async()=>{
    $('updated').textContent='正在读取板内计时…';
    const existing=new Set(state.catalog.digital.map(eventIdentity));
    const result=await api('/api/latency/read-board','POST',{});
    await loadCatalog();state.selected.digital=identity(result,'digital');showTab('digital');
    showNotice(existing.has(eventIdentity(result))?'已读取最近计时，同一事件只计一次。':'已加入板内最近一次有效计时。');
  }));
  $('import-segment').addEventListener('change',setImportMode);$('time-unit').addEventListener('change',unitLabels);
  $('csv-file').addEventListener('change',pickFile);
  $('csv-form').addEventListener('submit',event=>{
    event.preventDefault();let fields;
    try{fields=uploadFields();}catch(e){formStatus(e.message,true);return;}
    operate(async()=>{
      formStatus('正在分析…');
      try{
        const result=await api('/api/latency/scope-csv','POST',fields);
        await loadCatalog();
        const tab=fields.segment==='mark-i2s'?'digital':'scope';
        if(tab==='scope')$('scope-segment').value=fields.segment;
        state.selected[tab]=identity(result,tab);state.zoom[tab]=false;
        formStatus('已保存。');$('import').open=false;showTab(tab);
        showNotice('CSV 已分析并保存，请核对起止位置。');$('tab-'+tab).focus();
      }catch(e){formStatus(e.message,true);throw e;}
    });
  });
  setImportMode();unitLabels();render();
  let frame=0;
  window.addEventListener('resize',()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(render);});
  operate(async()=>{await loadCatalog();showNotice('');});
}
if(typeof module==='object' && module.exports)module.exports={stats,detectColumns,stable,identity,scopePeers,digitalPeers,validSeries,nearest,state};
if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',init);
})();
