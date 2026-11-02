"""Build the common listening phrase with the current HDL voice engine."""
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT.parent/'tmp/effects_enhance/sim'
WORK.mkdir(parents=True,exist_ok=True)
iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
sources=['synth_engine_shared.v','modal32.v','modal32_coeffs.v','piano_modal_tables_compact.v','waveform_rom.v']
subprocess.run([iv,'-g2012','-s','phrase','-o',str(WORK/'phrase.vvp'),str(Path(__file__).with_name('phrase.v')),
                *[str(ROOT/'fpga'/name) for name in sources]],check=True)
# ROM initializers retain their production paths.
subprocess.run([vvp,str(WORK/'phrase.vvp')],cwd=ROOT/'fpga',check=True,timeout=900)
(ROOT/'fpga/phrase.pcm').replace(WORK/'phrase.pcm')
