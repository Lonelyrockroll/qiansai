"""Verify capture ownership with a mock UART and analyze the archived physical board samples."""
import json
from pathlib import Path
import struct
import sys
import zlib

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/'tools'))
import pc_audio_analysis as pc


class FakeBoard:
    def __init__(self):
        self.raw=struct.pack('<32h',*range(32));self.writes=[];self.stall=False;self.page=False
        self.loop=dict(playing=False,recording=False,pending_record=False,layers=1)
        self.cap=dict(armed=False,recording=False,ready=False,error=False,aborted=False,capture_id=41,count=32,
                      first_frame=100,crc32=zlib.crc32(self.raw),sample_rate=pc.FS)
    def call(self,op,payload=b''):
        if op==4:return {'firmware':32}
        if op==14:return self.loop.copy()
        if op==32:return {k:self.page for k in ('score_valid','score_reserved','score_loading','score_visible')}
        if op==22:return self.cap.copy()
        if op==21:
            self.writes.append((op,bytes(payload)))
            if payload[0]:self.cap.update(capture_id=self.cap['capture_id']+1,armed=self.stall,ready=not self.stall,aborted=False)
            else:self.cap.update(armed=False,recording=False,ready=False,aborted=True)
            return {}
        if op==23:
            tag,address,n=struct.unpack('<HHB',payload)
            return dict(capture_id=tag,offset=address,count=n,data=self.raw[2*address:2*(address+n)].hex())
        raise AssertionError(f'unexpected control/setting mutation {op}')


def expect_error(fn,kind):
    try:fn()
    except kind:return
    raise AssertionError('expected refusal')


def guards():
    b=FakeBoard();b.page=True
    expect_error(lambda:pc.acquire(b,True,32,'immediate',1),ValueError);assert not b.writes
    b.page=False
    for flag in ('ready','armed','recording'):
        b.cap[flag]=True;expect_error(lambda:pc.acquire(b,True,32,'immediate',1),ValueError);assert not b.writes;b.cap[flag]=False
    for flag in ('recording','pending_record'):
        b.loop[flag]=True;expect_error(lambda:pc.acquire(b,True,32,'immediate',1),ValueError);assert not b.writes;b.loop[flag]=False
    b.loop['playing']=True
    data,meta,_=pc.acquire(b,True,32,'immediate',1);assert data==b.raw and b.loop['playing'] and b.loop['layers']==1
    assert b.writes==[(21,struct.pack('<BBHI',1,0,32,0))]
    data,_,_=pc.acquire(b,False,0,'',0);assert data==b.raw and len(b.writes)==1
    expect_error(lambda:pc.release(b,41),ValueError);assert len(b.writes)==1
    b.cap['crc32']^=1;expect_error(lambda:pc.acquire(b,False,0,'',0),RuntimeError);assert b.cap['ready'] and len(b.writes)==1
    pc.release(b,meta['capture_id']);assert not b.cap['ready']
    b.stall=True;expect_error(lambda:pc.acquire(b,True,32,'nonzero',.02),TimeoutError);assert b.writes[-1]==(21,b'\0') and not b.cap['armed']


def main():
    guards();base=HERE/'results';cases={}
    for name in ('all32','off16','off17'):
        raw,rate,source=pc.reference_pcm(name);folder=base/name;folder.mkdir(parents=True,exist_ok=True)
        m=pc.write_report(folder,raw,rate,40,4000,name,source)
        assert m['peak_bins']==source['reference_bins'] and m['peak_count']==source['reference_peak_count']
        assert abs(m['xy_delay_ms']-16_000/rate)<1e-10
        cases[name]=dict(source=source['path'],samples=m['samples'],rate=rate,crc32=m['crc32'],count=m['peak_count'],bins=m['peak_bins'])
    quiet=pc.analyze(bytes(128),pc.FS);assert not len(quiet[4])
    assert pc.analyze(struct.pack('<64h',*([800]*64)),pc.FS)[5]['peak_count']==0
    ny=pc.analyze(struct.pack('<64h',*([1000,-1000]*32)),pc.FS);assert abs(ny[2][-1]-1000)<.01 and ny[4].tolist()==[32]
    summary=dict(passed=True,scope='PC offline analysis of actual, previously captured board PCM; capture/ownership tests use a mock UART.',
                 bin_spacing_hz=rate/m['samples'],metadata_sha_crc_checked=True,cases=cases,
                 capture_guards=['PDF retained','ready/armed/recording retained','recording/pending Loop retained','playback not modified',
                                 'read-ready is read-only','wrong ID rejected','bad CRC preserves buffer','own trigger timeout canceled'])
    (base/'validation.json').write_text(json.dumps(summary,indent=2)+'\n');print('PASS archived PCM 32/31/31 exact bins, silence/DC/Nyquist normalization and capture ownership')


if __name__=='__main__':main()
