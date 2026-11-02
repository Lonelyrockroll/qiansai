"""Local PC audio page. This standalone server never enumerates or connects a Tang board."""
import argparse
import io
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import secrets
from urllib.parse import parse_qs,urlparse
import urllib.request
import webbrowser

import pcm_tools

ROOT=Path(__file__).resolve().parent


def send(handler,content,kind,status=200):
    handler.send_response(status);handler.send_header('Content-Type',kind);handler.send_header('Content-Length',str(len(content)))
    handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff');handler.end_headers();handler.wfile.write(content)


def serve(handler,token,origin,standalone=False):
    url=urlparse(handler.path)
    if url.path=='/audio-monitor' or standalone and url.path=='/':
        page=(ROOT/'audio-monitor.html').read_text(encoding='utf8').replace('__TOKEN__',token)
        if standalone:page=page.replace('<a href="/" target="_blank" rel="noopener">打开板卡控制台</a>','')
        send(handler,page.encode('utf8'),'text/html; charset=utf-8')
    elif url.path=='/audio-monitor.js':send(handler,(ROOT/'audio-monitor.js').read_bytes(),'text/javascript; charset=utf-8')
    elif url.path=='/api/audio-monitor/demo':
        if handler.headers.get('X-Synth-Token')!=token or handler.headers.get('Origin',origin)!=origin:
            send(handler,b'forbidden','text/plain',403);return True
        try:
            raw,rate,_=pcm_tools.reference_pcm(parse_qs(url.query).get('name',[''])[0]);file=io.BytesIO();pcm_tools.write_wav(file,raw,rate)
        except (OSError,ValueError,KeyError) as exc:send(handler,json.dumps({'error':str(exc)},ensure_ascii=False).encode(),'application/json',400)
        else:send(handler,file.getvalue(),'audio/wav')
    else:return False
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8768);p.add_argument('--no-browser',action='store_true');args=p.parse_args()
    host=f'127.0.0.1:{args.port}';origin='http://'+host;url=origin+'/audio-monitor';token=secrets.token_hex(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.headers.get('Host')!=host:send(self,b'invalid host','text/plain',403)
            elif not serve(self,token,origin,True):send(self,b'not found','text/plain',404)
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        try:
            with urllib.request.urlopen(url,timeout=2) as response:existing=response.read().decode('utf8')
            if '<title>Tang · 电脑音频观察</title>' not in existing:raise ValueError('different service')
        except (OSError,ValueError) as exc:raise SystemExit(f'端口 {args.port} 已被占用，请用 --port 指定其他端口') from exc
        print('复用已运行页面',url)
        if not args.no_browser:webbrowser.open(url)
        return
    print('电脑音频观察',url,'。关闭此窗口结束服务。',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
