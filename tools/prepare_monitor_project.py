"""Create a portable Gowin project with the requested local analyzer in an empty folder."""
import argparse
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'fpga'))
from check_sources import inspect


def prepare(profile, target):
    target=target.resolve()
    if target.exists() and any(target.iterdir()):raise ValueError('Use an empty project folder')
    target.mkdir(parents=True,exist_ok=True)
    for name in inspect():
        src=Path(name);shutil.copyfile(src,target/src.name)
    for name in ('synth_display.gprj','build.tcl','check_sources.py'):
        shutil.copyfile(ROOT/'fpga'/name,target/name)
    if profile=='spectrum-only':
        shutil.copyfile(ROOT/'profiles/spectrum-only/fpga/audio_monitor.v',target/'audio_monitor.v')
        shutil.copyfile(ROOT/'profiles/spectrum-only/build.tcl',target/'build.tcl')
    print(target/'synth_display.gprj')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('profile',choices=('full','spectrum-only'));cli.add_argument('target',type=Path)
    args=cli.parse_args();prepare(args.profile,args.target)
