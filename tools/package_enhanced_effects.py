"""Package the verified FX2 image, exact FPGA inputs, listening files and results."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def package(build):
    report=json.loads((build/'build_validation.json').read_text())
    results=json.loads((ROOT/'tests/effects_enhanced/board/results.json').read_text())
    sound=ROOT/'output/effects-v32p2'
    listen=json.loads((sound/'audition.json').read_text())
    fs=build/'impl/pnr/synth_display.fs'
    assert report['validated'] and report['monitor_profile']=='spectrum-only' and results['passed']
    assert hashlib.sha256(fs.read_bytes()).hexdigest()==report['sha256']
    jtag=(ROOT/'tests/effects_enhanced/board/after_jtag.log').read_text()
    assert report['user_code'].lower() in jtag.lower()
    target=ROOT/'output/Tang-效果增强-v32FX2.zip'
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        draft=Path(tmp)/target.name
        with zipfile.ZipFile(draft,'w',zipfile.ZIP_DEFLATED) as out:
            out.write(fs,'Tang-v32-FX2.fs')
            out.write(ROOT/'EFFECTS-ENHANCED.md','使用说明.md')
            out.write(build/'build_validation.json','验证/整机布局.json')
            for name in report['source_sha256']:
                path=build/name
                assert hashlib.sha256(path.read_bytes()).hexdigest()==report['source_sha256'][name]
                out.write(path,'FPGA工程/'+name)
            for name in ('synth_display.gprj','build.tcl','check_sources.py'):
                out.write(build/name,'FPGA工程/'+name)
            for name,meta in listen['files'].items():
                path=sound/(name+'.wav')
                assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256']
                out.write(path,'统一乐句/'+path.name)
            out.write(sound/'audition.json','统一乐句/采样与增益.json')
            for directory in (ROOT/'tests/effects_enhanced/board',ROOT/'tests/effects_enhanced/results'):
                for path in directory.iterdir():
                    if path.is_file():out.write(path,'验证/'+directory.name+'/'+path.name)
            for name in ('fx_tools.py','protocol.py','index.html'):
                out.write(ROOT/'realtime_synth/host'/name,'上位机更新文件/'+name)
        with zipfile.ZipFile(draft) as check:assert check.testzip() is None
        draft.replace(target)
    print(target,hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('build',type=Path)
    package(parser.parse_args().build.resolve())
