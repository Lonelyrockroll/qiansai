/* Browser regression with an isolated mock HTTP endpoint. No board or instruments are opened. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'../..'), HOST=path.join(ROOT,'realtime_synth/host');
const {stats,detectColumns}=require(path.join(HOST,'latency-monitor.js'));
const token='latency-browser-test', out=path.join(__dirname,'results');
const opts={time_column:'TIME_US',trigger_column:'HALL_V',audio_column:'OUT_V',time_unit:'us',baseline:[-30,-10],direction:'either',trigger_threshold:.3,audio_threshold:.08,trigger_points:1,audio_points:3};
const times=[-.03,-.02,-.01,0,.01,.02,.03,.04,.05,.06,.07,.08,.09,.1,.11,.12];
const ch1=times.map(t=>t>=0?2.1:1.6), ch2=times.map(t=>t>=.05?.18:0);
function analog(tag,delay,sha,setting=opts) {
  return {name:tag,segment:'hall-headphone',delay_ms:delay,t0_ms:0,t1_ms:delay,bounds_ms:[delay-.01,delay+.01],
    time_ms:times,trigger_v:ch1,audio_v:ch2,condition:'测试夹具 · H15 / 正弦 / 24%',settings:setting,
    csv_sha256:sha,source:'仅供浏览器回归的同步数据',raw_url:'/api/latency/csv/'+tag};
}
const first=analog('样例 A',.05,'a'.repeat(64));
const saved={digital:[{name:'固件计时夹具',key:'H15 / C4',version:'TEST-FW',count:1,sequence:73,us:88,source:'浏览器回归夹具 · 单次'}],
  scope:[first,analog('同一 CSV 重算',.05,'a'.repeat(64)),analog('样例 B',.07,'b'.repeat(64)),
    analog('另一组门限',.1,'c'.repeat(64),{...opts,trigger_threshold:.45})],
  audio:[{name:'声卡夹具',source:'回归夹具',channel:'Input 5',kind:'historical_ampero',
    fs:48000,samples:[0,.3,-.2,.2,0],time_s:[0,.001,.002,.003,.004],duration_s:.004,peak_dbfs:-10.46,wav_url:'/api/latency/wav/sample'}]};
let lastUpload,gets=0,boardReads=0;
function reply(res,code,type,content) {res.writeHead(code,{'Content-Type':type});res.end(content);}
const service=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname.startsWith('/api/latency/') && !/\/(wav|csv|mark)\//.test(url.pathname) && req.headers['x-synth-token']!==token) {
    reply(res,403,'application/json','{"error":"token missing"}');return;
  }
  if(url.pathname==='/api/latency/results'){gets++;reply(res,200,'application/json',JSON.stringify(saved));return;}
  if(url.pathname==='/api/latency/read-board'){
    const row={...saved.digital[0],key:'H15',name:'板内最近一次完整起音',source:'实板 UART 测试替身'};
    if(!boardReads++)saved.digital.push(row);
    reply(res,200,'application/json',JSON.stringify(row));return;
  }
  if(url.pathname==='/api/latency/scope-csv'){
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    const data=JSON.parse(Buffer.concat(chunks));lastUpload=data;
    if(data.name==='拒绝夹具'){reply(res,400,'application/json','{"error":"本条记录没有完整的 MARK 脉冲"}');return;}
    if(data.segment==='mark-i2s'){
      const row={name:data.name,version:'TEST-FW',key:'H15',segment:data.segment,count:1,sequence:null,
        us:80,t0_ms:0,t1_ms:.08,time_ms:[-.02,0,.02,.04,.06,.08,.1],trigger_v:[0,3.3,3.3,3.3,3.3,0,0],
        bounds_us:[60,100],source:'示波器标记测试替身',quality_note:'测试夹具：高平台可能削顶，按门限解读。',csv_sha256:'d'.repeat(64),
        raw_url:'/api/latency/mark/dd',threshold_v:data.trigger_threshold};
      saved.digital.push(row);reply(res,200,'application/json',JSON.stringify(row));return;
    }
    const row={...analog(data.name,.05,'e'.repeat(64)),segment:data.segment,condition:data.condition};
    saved.scope.push(row);reply(res,200,'application/json',JSON.stringify(row));return;
  }
  const route={'/latency-monitor':'latency-monitor.html','/latency-monitor.js':'latency-monitor.js','/latency-monitor.css':'latency-monitor.css'}[url.pathname];
  if(!route){reply(res,404,'text/plain','none');return;}
  const type=route.endsWith('.css')?'text/css':route.endsWith('.js')?'text/javascript':'text/html';
  reply(res,200,type+'; charset=utf-8',fs.readFileSync(path.join(HOST,route),'utf8').replaceAll('__TOKEN__',token));
});
async function main(){
  assert.equal(stats([2]).span,null);assert.equal(stats([.03,.04]).median,.035);
  assert.deepEqual(detectColumns('Tektronix,data\n"TIME_US","HALL_V","OUT_V"\n-1,1.6,0').names,['TIME_US','HALL_V','OUT_V']);
  assert.equal(detectColumns('TIME_US,HALL_V,OUT_V\n-1,1,0').unit,'us');
  await new Promise(resolve=>service.listen(0,'127.0.0.1',resolve));
  const errors=[], browser=await chromium.launch({headless:true,channel:process.env.LATENCY_BROWSER || (process.platform==='win32'?'msedge':undefined)});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:920},deviceScaleFactor:1});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:'+service.address().port+'/latency-monitor');
    await page.waitForFunction(()=>document.querySelector('#digital-summary').textContent.includes('88'));
    assert.match(await page.locator('#digital-stats').innerText(),/1 次有效测量/);
    await page.click('#read-board');await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('同一事件'));
    await page.click('#read-board');await page.waitForFunction(()=>!document.querySelector('#read-board').disabled);
    assert.equal(boardReads,2);assert.match(await page.locator('#digital-stats').innerText(),/1 次有效测量/);
    await page.click('#tab-scope');
    assert.equal(await page.locator('#scope-plot path[data-series]').count(),2);
    assert.equal(await page.locator('#scope-plot line[data-marker]').count(),2);
    assert.match(await page.locator('#scope-stats').innerText(),/2 次有效测量/);
    assert.match(await page.locator('#scope-stats').innerText(),/0\.06/);
    await page.click('.expand-plot[data-target=scope]');assert.equal(await page.locator('#plot-dialog').evaluate(n=>n.open),true);
    assert.equal(await page.locator('#plot-dialog #scope-plot path[data-series]').count(),2);
    await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#plot-dialog').open);
    assert.equal(await page.locator('#panel-scope #scope-plot').count(),1);
    await page.click('#panel-scope .zoom');assert.match(await page.locator('#panel-scope .zoom').innerText(),/查看全窗/);
    await page.locator('#scope-plot').hover({position:{x:240,y:75}});
    assert.match(await page.locator('#scope-readout').innerText(),/CH1.*CH2/);
    fs.mkdirSync(out,{recursive:true});
    await page.screenshot({path:path.join(out,'scope-fixture.png'),fullPage:true});
    await page.selectOption('#scope-segment','hall-mark');assert.equal(await page.locator('#scope-empty').isVisible(),true);
    await page.click('#tab-audio');assert.equal(await page.locator('#audio-plot [data-marker]').count(),0);
    assert.equal(await page.locator('#audio-plot path[data-series]').count(),1);
    assert.match(await page.locator('#audio-media audio').getAttribute('src'),/\/wav\/sample$/);
    await page.click('#tab-digital');await page.click('.open-import[data-segment]');
    assert.equal(await page.locator('#paired-fields').isVisible(),false);
    await page.setInputFiles('#csv-file',{name:'pulse.csv',mimeType:'text/csv',buffer:Buffer.from('\ufeffTIME_US,CH1\r\n-10,0\r\n0,3.3\r\n10,3.3\r\n80,0')});
    await page.waitForFunction(()=>document.querySelector('#record-name').value==='pulse.csv');
    assert.equal(await page.inputValue('#time-unit'),'us');
    await page.click('#submit-csv');await page.waitForFunction(()=>document.querySelector('#digital-summary').textContent.includes('80'));
    assert.equal(lastUpload.segment,'mark-i2s');assert.ok(!('audio_column' in lastUpload));
    assert.ok(lastUpload.csv.startsWith('\ufeffTIME_US,CH1\r\n')); // preserve original CSV bytes, including BOM and CRLF.
    assert.equal(await page.locator('#digital-plot path[data-series]').count(),1);
    assert.equal(await page.locator('#digital-plot line[data-marker]').count(),2);
    assert.match(await page.locator('#digital-meta a').getAttribute('href'),/\/mark\/dd$/);
    assert.match(await page.locator('#digital-meta .quality-note').innerText(),/波形说明.*削顶/);
    await page.click('#tab-scope');await page.click('#panel-scope .open-import');
    await page.setInputFiles('#csv-file',{name:'three.csv',mimeType:'text/csv',buffer:Buffer.from('TIME_US,HALL_V,OUT_V\n-30,1.6,0\n-10,1.6,0\n10,2.2,.2')});
    await page.waitForFunction(()=>document.querySelector('#time-column').value==='TIME_US' && document.querySelector('#audio-column').value==='OUT_V');
    await page.fill('#trigger-level','.3');await page.fill('#audio-level','.08');
    await page.fill('[name=baseline_from]','-30');await page.fill('[name=baseline_to]','-10');await page.fill('[name=condition]','夹具 B');
    await page.click('#submit-csv');await page.waitForFunction(()=>!document.querySelector('#import').open);
    assert.equal(lastUpload.segment,'hall-mark');assert.equal(lastUpload.baseline_from,-30);assert.equal(lastUpload.audio_threshold,.08);
    await page.click('#panel-scope .open-import');await page.fill('#record-name','拒绝夹具');await page.click('#submit-csv');
    await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('没有完整'));
    assert.equal(await page.locator('#import').evaluate(n=>n.open),true);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(out,'mobile-fixture.png'),fullPage:true});
    assert.equal(errors.length,0,errors.join('\n'));assert.ok(gets>=5);
    fs.writeFileSync(path.join(out,'browser-validation.json'),JSON.stringify({result:'passed',scope:'Isolated mock API in headless Chromium / Edge. No device connection.',tests:['token on GET and both POSTs','deduplicated board reads','same-segment/same-configuration CSV stats','single/dual waveform markers and zoom','existing WAV playback link','two-channel and MARK-only form dispatch','400 error retains form','390 px viewport'],browser:browser.version()},null,2)+'\n');
    console.log('PASS actual browser: token, readings, de-duplication, segmented stats, SVG traces, MARK/dual upload, error and mobile');
  }finally{await browser.close();service.close();}
}
main().catch(err=>{service.close();console.error(err);process.exitCode=1;});
