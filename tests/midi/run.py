"""Exercise the actual UART, FIFO, MIDI ownership and production voice router."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = ('uart_rx.v','midi_decoder.v','midi_input.v','note_rom.v','performance_router.v')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical-baud', action='store_true')
    args = parser.parse_args()
    bits = 1600 if args.physical_baud else 32
    with tempfile.TemporaryDirectory(prefix='tang-midi-') as directory:
        simulation = Path(directory) / 'midi.vvp'
        subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-s','tb_midi',
                        '-P',f'tb_midi.BIT_CYCLES={bits}','-o',str(simulation),str(HERE/'tb_midi.v'),
                        *[str(ROOT/'fpga'/name) for name in SOURCES]],check=True)
        run = subprocess.run(['E:/iverilog/bin/vvp.exe',str(simulation)],capture_output=True,text=True,errors='replace',timeout=300)
    folder = HERE/'results'
    folder.mkdir(exist_ok=True)
    label = 'serial_31250' if args.physical_baud else 'regression'
    (folder/(label+'.log')).write_text(run.stdout+run.stderr,encoding='utf8')
    (folder/(label+'.json')).write_text(json.dumps(dict(passed=run.returncode==0,bit_clocks=bits,
        source_sha256={name:hashlib.sha256((ROOT/'fpga'/name).read_bytes()).hexdigest() for name in SOURCES},
        output=run.stdout+run.stderr),indent=2)+'\n')
    print(run.stdout+run.stderr)
    if run.returncode:raise SystemExit(run.returncode)


if __name__=='__main__':main()
