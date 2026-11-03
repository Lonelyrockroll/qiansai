"""Run serial MIDI into the production top-level audio path and decode I2S."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('latency_sources',ROOT/'tests/contest_latency/run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
names=tuple(dict.fromkeys((*module.SOURCES,'midi_input','midi_decoder','uart_rx')))
with tempfile.TemporaryDirectory(prefix='midi-audio-') as directory:
    path=Path(directory)
    subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-i','-s','tb_midi_audio','-o',str(path/'audio.vvp'),
                    str(HERE/'tb_audio.v'),*[str(ROOT/'fpga'/(name+'.v')) for name in names]],check=True)
    run=subprocess.run(['E:/iverilog/bin/vvp.exe',str(path/'audio.vvp')],cwd=ROOT/'fpga',capture_output=True,text=True,errors='replace',timeout=300)
report=dict(passed=run.returncode==0,scope='Production MIDI, arbitration, Loop, voice router, synth, effects, limiter and independent I2S decoder. Peripheral controls tied idle.',
    source_sha256={name:hashlib.sha256((ROOT/'fpga'/(name+'.v')).read_bytes()).hexdigest() for name in names},output=run.stdout+run.stderr)
folder=HERE/'results';folder.mkdir(exist_ok=True)
(folder/'audio.json').write_text(json.dumps(report,indent=2)+'\n');print(report['output'])
if run.returncode:raise SystemExit(run.returncode)
