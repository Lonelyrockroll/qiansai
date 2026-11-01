"""Inspect the physical v31 board via COM6; the PDF sender stays on Android."""
import argparse
import json
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'realtime_synth/control_meter_l8'))
from verify_board import Board
from protocol import Decoder
from transports import list_devices,open_device


def save(folder, name, value):
    p=folder/name
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')


def startup(b, folder):
    s=b.state(); page=b.call(32)
    assert s['4']['firmware']==31 and s['11']['locked'] and s['4']['amp_muted']
    assert s['9']['calibrated'] and not s['9']['fault'] and not s['9']['pressed_mask']
    assert not page['score_reserved'] and not page['score_visible']
    assert not any(s['22'][k] for k in ('armed','recording','ready'))
    # Verify the legacy engineering capture on the same physical RAM. No tone is generated.
    b.call(21,bytes([1,0])+struct.pack('<HI',128,0))
    try:
        deadline=time.monotonic()+.8
        while time.monotonic()<deadline:
            captured=b.call(22)
            if captured['ready']:break
        assert captured['ready'] and captured['count']==128 and not captured['error'],captured
        samples=bytearray()
        for address in range(0,128,6):
            length=min(6,128-address)
            result=b.call(23,struct.pack('<HHB',captured['capture_id'],address,length))
            assert result['offset']==address and result['count']==length
            samples+=bytes.fromhex(result['data'])
        assert zlib.crc32(samples)==captured['crc32']
    finally:
        b.call(21,b'\0')
    save(folder,'startup.json',dict(result='passed',initial=s,score=page,captured=captured,
        actual_pcm_crc32=zlib.crc32(samples),released=not b.call(22)['ready']))
    print('PASS v31: HDMI locked, keyboard calibrated, 128 captured/read words with matching CRC; score cache free.')


def watch(b,folder,timeout):
    seen=set(); timeline=[];started=time.monotonic();prev=None
    while time.monotonic()-started<timeout:
        s=b.call(32);key=(s['score_page'],s['score_pages'],s['score_valid'],s['score_visible'],s['score_loading'],s['score_received']//2048)
        if key!=prev:
            timeline.append(dict(seconds=round(time.monotonic()-started,3),**s));prev=key
            save(folder,'phone_pages.json',dict(seen=sorted(seen),states=timeline))
        if s['score_valid'] and s['score_visible'] and s['score_pages']==2 and s['score_decoded']==65536:
            seen.add(s['score_page'])
            if seen=={0,1}:break
        time.sleep(.18)
    save(folder,'phone_pages.json',dict(seen=sorted(seen),states=timeline))
    print('Observed shown page indices:',sorted(seen))


def read_page(b,folder,full):
    from PIL import Image, ImageOps
    page=b.call(32);assert page['score_valid'] and not page['score_loading'] and page['score_decoded']==65536,page
    idx=page['score_page']
    # The existing PCM acquisition must not overwrite an imported PDF.
    try:b.call(21,bytes([1,0])+struct.pack('<HI',128,0))
    except RuntimeError as e:assert e.args[0][1]['status']==4, e
    else:raise AssertionError('PCM acquisition unexpectedly accepted while the PDF owns RAM')
    sample_addresses=[0,32,1024,4896,12064,16000,25984,31168,32762]
    starts=range(0,32768,6) if full else sample_addresses
    raw=bytearray();samples=[];started=time.monotonic()
    for addr in starts:
        n=min(6,32768-addr)
        r=b.call(33,struct.pack('<HHB',idx,addr,n))
        assert (r['score_page'],r['offset'],r['count'])==(idx,addr,n),r
        # The PC words are little endian, while pixels within each word are MSB first.
        words=struct.unpack('<'+'H'*n,bytes.fromhex(r['data']))
        raw.extend(b''.join(w.to_bytes(2,'big') for w in words))
        if addr in sample_addresses:samples.append(dict(address=addr,words=words))
    after=b.call(32)
    assert after['score_valid'] and not after['score_loading'] and after['score_page']==idx
    result=dict(page=page,after=after,pcm_overwrite_rejected=True,seconds=round(time.monotonic()-started,3),sample_words=samples)
    if full:
        assert len(raw)==65536
        result.update(raw_bytes=len(raw),raw_crc32=f'{zlib.crc32(raw):08X}',black_pixels=sum(x.bit_count() for x in raw))
        prefix=f'phone-page-{idx+1:02d}'
        (folder/(prefix+'.bin')).write_bytes(raw)
        source=ImageOps.invert(Image.frombytes('1',(1024,512),bytes(raw)).convert('L'))
        # Match the actual FPGA line accumulator, rather than relying on a library's pixel-centre convention.
        displayed=Image.new('L',(1024,600))
        for y in range(600):
            sy=y*512//600;displayed.paste(source.crop((0,sy,1024,sy+1)),(0,y))
        displayed.save(folder/(prefix+'.png'))
        # Different Android PDF renderers can rasterize individual glyph edges differently.
        # Compare only as a diagnostic; the phone/board raw CRC check is authoritative on upload.
        reference=ROOT/f'output/pdf/score-demo/page-{idx+1:02d}.bin'
        if reference.is_file():
            ref=reference.read_bytes();result['reference_pixel_agreement']=1-sum((a^v).bit_count() for a,v in zip(raw,ref))/(65536*8)
            intersection=sum((a&v).bit_count() for a,v in zip(raw,ref));union=sum((a|v).bit_count() for a,v in zip(raw,ref))
            result['reference_ink_iou']=intersection/union if union else 1.0
    save(folder,f'page-{idx+1:02d}-readback.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('page','after','sample_words')},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('startup','watch','sample','dump','status'))
    ap.add_argument('folder',type=Path);ap.add_argument('--timeout',type=int,default=180)
    opt=ap.parse_args();opt.folder.mkdir(parents=True,exist_ok=True)
    if opt.action=='dump':
        candidates=[d for d in list_devices()[0] if d['id'].startswith('d2xx:') and d.get('preferred') and not d.get('opened')]
    else:candidates=[]
    if len(candidates)==1:
        # Channel B is the same FPGA UART; D2XX uses a shorter USB latency for bulk readback.
        b=Board.__new__(Board);b.device=open_device(candidates[0]['id']);b.seq=0;b.decoder=Decoder()
    else:b=Board()
    try:
        if opt.action=='startup':startup(b,opt.folder)
        elif opt.action=='watch':watch(b,opt.folder,opt.timeout)
        elif opt.action=='status':print(json.dumps(b.call(32),indent=2))
        else:read_page(b,opt.folder,opt.action=='dump')
    finally:b.device.close()
