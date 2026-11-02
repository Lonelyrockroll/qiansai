"""Exercise live UI with Chromium's synthetic audio device. No physical input or board is opened."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
import zipfile

import numpy as np
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def fixture(path):
    n=4096;index=np.arange(n);bins=list(range(4,253,8))
    block=sum(.011*np.sin(2*np.pi*k*index/n+k*.21) for k in bins)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(np.tile(np.rint(block*32768).astype('<i2'),64).tobytes())
    return bins


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--browser',type=Path,default=Path('C:/Program Files/Google/Chrome/Application/chrome.exe'))
    ap.add_argument('--kit',type=Path,help='test a freshly extracted standalone kit instead of the full host')
    args=ap.parse_args();out=HERE/'results';out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tang-live-audio-') as d:
        audio=Path(d)/'synthetic32.wav';bins=fixture(audio)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}/audio-monitor'
        server_name=ROOT/'realtime_synth/host/server.py'
        if args.kit:
            isolated=Path(d)/'isolated';
            with zipfile.ZipFile(args.kit) as z:z.extractall(isolated)
            server_name=isolated/'realtime_synth/host/audio_web.py'
        server=subprocess.Popen([sys.executable,'-S','-B','-u',server_name,'--port',str(port),'--no-browser'],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(60):
                try:
                    with urllib.request.urlopen(url,timeout=.5) as response:assert response.status==200
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('local test server unavailable')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=str(args.browser),headless=True,args=['--use-fake-device-for-media-stream',
                    '--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required',f'--use-file-for-fake-audio-capture={audio}'])
                page=browser.new_page(viewport={'width':1350,'height':970},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.add_init_script('''const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                    window.testStreams=[];navigator.mediaDevices.getUserMedia=async function(c){const s=await gum(c);testStreams.push({constraints:c,stream:s});return s;};''')
                page.goto(url);assert page.evaluate('testStreams.length')==0
                page.click('#list');page.wait_for_function("document.querySelector('#device').options.length>1")
                assert page.evaluate("testStreams.length===1 && testStreams[0].stream.getTracks().every(t=>t.readyState==='ended')")
                assert page.locator('#start').is_disabled()
                options=page.locator('#device option').evaluate_all('(o)=>o.map(a=>[a.value,a.text])')
                device=next(item[0] for item in options if item[0] and item[0] not in ('default','communications'))
                page.select_option('#device',value=device);page.click('#start')
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('电脑音频输入') && Number(document.querySelector('#metrics').dataset.peaks)===32",timeout=12000)
                page.wait_for_timeout(350)  # capture a full steady-state window after device startup
                live=page.locator('#metrics').evaluate('(el)=>({...el.dataset})');observed=list(map(int,live['bins'].split(',')));rate=float(live['rate'])
                expected=[round(k*48000/rate) for k in bins];assert len(observed)==32 and max(abs(i-j) for i,j in zip(observed,expected))<=1
                assert abs(float(live['xyDelayMs'])-16_000/rate)<1e-10
                assert page.evaluate('testStreams[1].constraints.audio.deviceId.exact')==device
                page.screenshot(path=str(out/'browser-synthetic-input.png'),full_page=True)
                page.click('#stop');assert page.evaluate('testStreams.every(s=>s.stream.getTracks().every(t=>t.readyState==="ended"))')
                page.locator('summary').click();archive={}
                for example,missing in [('all32',None),('off16',124),('off17',132)]:
                    page.select_option('#demo',value=example);page.click('#demoStart')
                    page.wait_for_function("document.querySelector('#status').textContent.includes('文件循环回放')")
                    page.wait_for_timeout(500)
                    data=page.locator('#metrics').evaluate('(el)=>({...el.dataset})');archive[example]=data
                    assert int(page.locator('#detail').get_attribute('data-file-rate'))==48828
                    assert abs(float(data['xyDelayMs'])-16_000/float(data['rate']))<1e-10
                    expected=[round(k*48828.125/float(data['rate'])) for k in bins if k!=missing]
                    observed=list(map(int,data['bins'].split(',')))
                    assert len(observed)==len(expected) and max(abs(a-b) for a,b in zip(observed,expected))<=1,(example,observed,expected)
                    assert page.evaluate('testStreams.length')==2
                    assert all(page.locator('#'+name).evaluate('(c)=>c.width>0 && c.height>0 && c.getContext("2d").getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===3 && v>0)') for name in ('wave','xy','full','zoom'))
                    if example=='all32':page.screenshot(path=str(out/'browser-board-file.png'),full_page=True)
                    page.click('#stop')
                browser.close();assert not errors,errors
                result=dict(passed=True,scope='Headless Chromium, known 32-tone synthetic input through a fake OS recording device and real Web Audio/Canvas. No external sound card was measured.',
                    default_streams=0,selected_input_label=next(q[1] for q in options if q[0]==device),all_tracks_ended_after_stop=True,
                    served_from='extracted stand-alone kit' if args.kit else 'full host',
                    synthetic_input=live,archived_board_browser_replays=archive,canvas_views=['wave','xy','full','zoom'])
                if args.kit:result['kit_sha256']=hashlib.sha256(args.kit.read_bytes()).hexdigest()
                (out/'browser-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
        finally:
            server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
