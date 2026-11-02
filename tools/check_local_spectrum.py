"""Check local panel controls against a separate FFT of the board's final PCM."""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'realtime_synth/throughput_eval'))
from verify32 import Board, FS, grab, spectrum, wait_for, status
from fx_tools import PRESETS
from protocol import voice_payload


def measure_frames(board):
    def stamp():
        lo=time.perf_counter()
        frames=board.call(4)['frames']
        return lo,time.perf_counter(),frames
    a,b,f0=stamp();time.sleep(3);c,d,f1=stamp()
    frames=(f1-f0)&0xffffffff
    return dict(frames=frames,midpoint_hz=2*frames/(c+d-a-b),
                rate_bounds_hz=[frames/(d-a),frames/(c-b)],
                method='FPGA sample-tick counter over a host monotonic interval; UART uncertainty bounded, not an LRCLK pin measurement')


def check(folder):
    folder.mkdir(parents=True,exist_ok=True)
    board=Board()
    touched=False
    cases={}
    spectra={}
    def menu(action,arg=0): return board.call(10,bytes([action,arg]))
    try:
        before=status(board)
        assert before['4']['firmware']==32 and not before['4']['amp_hold'] and not before['4']['active']
        assert not before['16']['length_set'] and not before['14']['playing'] and not before['14']['recording']
        assert not board.call(32)['score_reserved'] and not board.call(34)['monitor']
        assert not any(before['22'][k] for k in ('armed','recording','ready'))
        touched=True
        board.fx(dict(PRESETS['off'],monitor_mute=1))
        board.call(5,b'\x01')
        board.call(10,bytes([7])+int(12288).to_bytes(2,'little'))
        # Recreate the previously failing entry: an un-released source-0
        # note exists when B is pressed, so the FPGA must fade and take over.
        if before['9']['mode']==2:menu(11)
        assert board.call(9)['mode']==0
        board.call(6)
        wait_for(lambda:board.call(4),lambda s:s['amp_ready'],'PA did not warm')
        board.call(2,voice_payload(7,1,261.6256,timbre=0,level=.08,attack_ms=2,decay_ms=10,sustain=1,release_ms=10))
        wait_for(lambda:board.call(17),lambda r:r['live_held']==1,'Held-note setup')
        menu(5,12)
        assert board.call(34)['monitor']
        occupied=dict(router=board.call(17),main=board.call(4))
        menu(2)
        limiter_start=board.call(27)['limited_frames']
        for title,missing in [('all32',None),('off16',15),('off17',16)]:
            if missing==15:menu(2)
            if missing==16:menu(1)
            count=32 if missing is None else 31
            wait_for(lambda:board.call(34),lambda v:v['active']==count and v['peak_count']==count and v['demo']==(1 if missing is None else 2),'Local test did not settle',4)
            time.sleep(.12)
            monitored=board.call(34)
            assert not monitored['analysis_overrun'] and monitored['peak_count']==count,monitored
            levels=sum((board.call(35,bytes([g]))['levels'] for g in range(4)),[])
            bins=[4*(2*i+1) for i in range(32) if i!=missing]
            for i in range(32):
                if i!=missing:assert levels[2*i]>max(0 if i==0 else levels[2*i-1],levels[2*i+1]),(i,levels)
            raw,info=grab(board,count,limiter_start)
            amplitudes,stats=spectrum(raw,bins)
            (folder/(title+'.pcm')).write_bytes(raw)
            spectra[title]=amplitudes
            cases[title]=dict(monitor=monitored,levels=levels,bins=bins,pcm=info,fft=stats)
            if missing is not None:
                offbin=4*(2*missing+1)
                reference=spectra['all32']
                assert amplitudes[offbin]<=reference[offbin]/32
                assert np.all(abs(amplitudes[bins]-reference[bins])<=np.maximum(2.,reference[bins]*.02))
        with (folder/'fft.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['bin','frequency_hz','all32','off16','off17'])
            for k in range(len(spectra['all32'])):
                writer.writerow([k,k*FS/4096,*(float(spectra[name][k]) for name in ('all32','off16','off17'))])
        report=dict(result='passed',source='Panel menu 13, on-board generators and normal note router. Amp muted for digital verification.', frame_rate_check=measure_frames(board),
                    fs_hz=FS,components_per_second=32*FS,occupied_before_local_takeover=occupied,cases=cases)
        (folder/'spectrum.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PASS local generators and independent PCM FFT: 32, 31, moved notch 31')
    finally:
        try:
            if touched:
                board.call(3)
                menu(3)
                board.call(21,b'\0')
                board.call(5,bytes([before['27']['gain_mode']]))
                board.call(10,bytes([7])+before['11']['level'].to_bytes(2,'little'))
                if before['9']['mode']==2 and board.call(9)['mode']==0:
                    menu(11)
                    wait_for(lambda:board.call(9),lambda k:k['calibrated'] and not k['fault'],'Restore 32-key scan')
                board.fx(before['25'])
                menu(6,12)
        finally:board.device.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    check(parser.parse_args().folder)
