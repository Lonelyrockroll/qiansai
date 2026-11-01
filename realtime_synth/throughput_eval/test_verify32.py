"""Offline only. No construction of a UART transport; all PCM below is synthetic."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import verify32 as t


class FakeBoard:
    def __init__(self):
        self.mode=2;self.hold=True;self.gain=1;self.notes={};self.count=0;self.raw=None
        self.fxconfig=dict(t.PRESETS['combined'], monitor_mute=0)
        self.writes=[];self.bad_crc=False;self.loop=False
    def fx(self, settings):
        self.writes.append('fx');self.fxconfig={k:settings[k] for k in t.FIELDS}
    def call(self, op, payload=b''):
        common={'firmware':26}
        def result(**kwargs):return dict(common,**kwargs)
        if op in (2,3,5,6,10,21):self.writes.append(op)
        if op==2:
            voice,gate,_,_,step,*_=struct.unpack('<BBBH I HHHH',payload)
            if gate:self.notes[voice]=step>>20
            else:self.notes.pop(voice,None)
        elif op==3:self.hold=False;self.notes.clear()
        elif op==5:self.gain=payload[0]
        elif op==6:self.hold=True
        elif op==10:
            if payload!=b'\x0b':raise AssertionError(payload)
            self.mode=2 if self.mode==0 else 0
        elif op==21:
            if not payload:self.raw=None
            else:
                assert payload==b'\x01\x00\x00\x10\x00\x00\x00\x00'
                self.count=(self.count+1)%65536
                idx=np.arange(t.N)
                values=sum(400*np.sin(2*np.pi*k*idx/t.N + .2*i) for i,k in self.notes.items())
                self.raw=np.rint(values).astype('<i2').tobytes()
        elif op==23:
            cid,offset,count=struct.unpack('<HHB',payload)
            assert cid==self.count
            return result(capture_id=cid,offset=offset,count=count,data=self.raw[2*offset:2*(offset+count)].hex())
        elif op==4:return result(sample_rate=t.FS, active=len(self.notes), gated=len(self.notes),
                                 amp_hold=self.hold,amp_ready=self.hold,amp_muted=not self.hold or self.fxconfig['monitor_mute'],
                                 watchdog=False,overrun=False,clipped=False)
        elif op==9:return result(mode=self.mode,calibrated=bool(self.mode),fault=False,pressed_mask=0)
        elif op==11:return result(mode=self.mode,focus=0,drum_mode=True,timbre=4,level=5244,press=256,release=128,sensitivity=64,pattern=False)
        elif op==13:return result(active_voices=0,overrun=False)
        elif op==14:return result(layers=int(self.loop),present=self.loop,playing=False,recording=False,pending_record=False,layer_counts=[0]*4)
        elif op==16:return result(timbre=4,key_mode=self.mode,drum_level=5244,keyboard_level=16384,length_set=self.loop)
        elif op==17:return result(held=len(self.notes),live_held=len(self.notes),loop_held=0)
        elif op==22:return result(capture_id=self.count,count=t.N if self.raw else 0,target=t.N,
                                  ready=self.raw is not None,armed=False,recording=False,error=False,
                                  crc32=(zlib.crc32(self.raw) ^ self.bad_crc) if self.raw else 0)
        elif op==25:return result(**self.fxconfig,pending=False,tail=False,clipped=False,overrun=False)
        elif op==27:return result(gain_mode=self.gain,limited_frames=0,limited=False,limiter_overrun=False,limiter_gain_q16=65536)
        else:return common
        return common
    def state(self):return {str(k):self.call(k) for k in (4,9,11,12,16,22,25,27,29)}


class ProofTests(unittest.TestCase):
    def args(self, out):
        return SimpleNamespace(run=True,out=out,retune=True,pause_held=True,android_idle=True)

    def test_synthetic_full_process_and_selective_muting(self):
        b=FakeBoard()
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'synthetic';t.run(b,self.args(dest))
            report=json.loads((dest/'summary.json').read_text())
            self.assertEqual(report['result'],'passed')
            self.assertEqual(report['component_samples_per_second'],1562500)
            self.assertEqual(len(report['cases']),3)
            self.assertEqual((dest/'off31.pcm').stat().st_size,8192)
        self.assertEqual((b.mode,b.hold,b.gain,b.fxconfig['mask'],b.fxconfig['monitor_mute']),(2,False,1,7,0))

    def test_wrong_spectrum_with_same_active_count(self):
        data=np.rint(400*np.sin(2*np.pi*t.BINS[0]*np.arange(t.N)/t.N)).astype('<i2').tobytes()
        with self.assertRaises(RuntimeError):t.spectrum(data,t.BINS)
        full=np.full(t.N//2+1,400.0);off=full.copy()
        with self.assertRaises(RuntimeError):t.compare(full,off)
        off[t.BINS[t.OFF]]=0;off[t.BINS[1]]=0
        with self.assertRaises(RuntimeError):t.compare(full,off)

    def test_refuse_without_touching_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case in ('android','hold','loop','capture','notes','single'):
                with self.subTest(case=case):
                    b=FakeBoard();args=self.args(Path(tmp)/case)
                    if case=='android':args.android_idle=False
                    if case=='hold':args.pause_held=False
                    if case=='loop':b.loop=True
                    if case=='capture':b.raw=b'xx'
                    if case=='notes':b.notes[0]=17
                    if case=='single':b.mode=1
                    with self.assertRaises(RuntimeError):t.run(b,args)
                    self.assertEqual(b.writes,[])

    def test_failed_capture_crc_still_restores(self):
        b=FakeBoard();b.bad_crc=True
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'bad'
            with self.assertRaisesRegex(RuntimeError,'CRC32'):t.run(b,self.args(dest))
            report=json.loads((dest/'summary.json').read_text())
            self.assertEqual(report['result'],'incomplete')
            self.assertIn('restored',report)
        self.assertIsNone(b.raw)
        self.assertEqual((b.mode,b.hold,b.gain,b.fxconfig['mask']),(2,False,1,7))


if __name__=='__main__':unittest.main()
