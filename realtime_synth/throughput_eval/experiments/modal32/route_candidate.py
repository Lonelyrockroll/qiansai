"""Build inputs or validate isolated full-system placement trials for the 32-partial patch."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from pack_font import pack

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[2]/'control_white_keys'
SCRATCH=HERE.parents[3]/'tmp/modal32_fit_20261101'


def trial_dir(option,compact,musical=False):
    root = SCRATCH/'musical' if musical else SCRATCH
    return root/(('font_' if compact else '')+f'place{option}')


def prepare(option,compact,musical=False):
    target=trial_dir(option,compact,musical)
    target.mkdir(parents=True,exist_ok=True)
    project=ET.parse(BASE/'synth_display.gprj')
    files=project.find('FileList')
    for node in files.findall('File'):
        src=(BASE/node.get('path')).resolve()
        if src.name=='piano_modal_mixed.v':
            src=target/'modal32.v'
            shutil.copyfile(HERE/src.name,src)
        elif compact and src.name=='panel_renderer.v':
            pack(BASE,target)
            src=target/'panel_renderer.v'
        elif src.suffix in ('.cst','.sdc'):
            shutil.copyfile(src,target/src.name)
            src=target/src.name
        node.set('path',src.as_posix())
    coefficients = (HERE/'musical' if musical else HERE)/'modal32_coeffs.v'
    shutil.copyfile(coefficients,target/'modal32_coeffs.v')
    ET.SubElement(files,'File',path='modal32_coeffs.v',type='file.verilog',enable='1')
    project.write(target/'synth_display.gprj',encoding='utf-8',xml_declaration=True)
    for src in [*BASE.glob('*.hex'),*BASE.glob('*.mem'),BASE/'check_sources.py',BASE/'validate_build.py']:
        shutil.copyfile(src,target/src.name)
    tcl=re.sub(r'set_option -place_option \d+',f'set_option -place_option {option}',(BASE/'build.tcl').read_text())
    (target/'build.tcl').write_text(tcl)
    print(target)


def validate(option,compact,musical=False):
    target=trial_dir(option,compact,musical)
    patch = HERE/'musical' if musical else HERE
    for src in (HERE/'modal32.v',patch/'modal32_coeffs.v'):
        if src.read_bytes()!=(target/src.name).read_bytes():
            raise RuntimeError(f'{src.name} changed since preparing this route')
    proc=subprocess.run([sys.executable,'-X','utf8','validate_build.py'],cwd=target,capture_output=True,text=True)
    (target/'validate.log').write_text(proc.stdout+proc.stderr,encoding='utf8')
    rpt=target/'impl/pnr/synth_display.rpt.txt'
    report=rpt.read_text(errors='replace') if rpt.exists() else ''
    resources={}
    for row in re.finditer(r'^\s*(Logic|Register|BSRAM|DSP)\s*\|\s*([\d.]+)/([\d]+)',report,re.M):
        resources[row[1]]=[float(row[2]),int(row[3])]
    record={'place_option':option,'compact_font':compact,'validated':proc.returncode==0,'resources':resources}
    if proc.returncode:
        errors=[line.strip() for line in (target/'build.log').read_text(errors='replace').splitlines() if 'ERROR  (' in line]
        record['reason']=errors or (proc.stdout+proc.stderr).strip().splitlines()[-1]
    else:
        v=json.loads((target/'build_validation.json').read_text())
        base=json.loads((BASE/'build_validation.json').read_text())
        if {(x['signal'],x['pin']) for x in v['pins']}!={(x['signal'],x['pin']) for x in base['pins']}:
            raise RuntimeError('Unexpected change to board pins')
        if hashlib.sha256((target/'impl/pnr/synth_display.fs').read_bytes()).hexdigest()!=v['sha256']:
            raise RuntimeError('Bitstream digest mismatch')
        record.update(user_code=v['user_code'],sha256=v['sha256'],frequency=v['frequency'],slack=v['slack'])
    (patch/(target.name+'_report.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(record)
    return proc.returncode


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','validate'))
    p.add_argument('place_option',type=int,choices=(1,2))
    p.add_argument('--compact-font',action='store_true',help='preserve every displayed pixel while packing the font more densely')
    p.add_argument('--musical',action='store_true',help='use the musical piano coefficients, with separate build directories and reports')
    args=p.parse_args()
    if args.action=='prepare':prepare(args.place_option,args.compact_font,args.musical)
    else:sys.exit(validate(args.place_option,args.compact_font,args.musical))
