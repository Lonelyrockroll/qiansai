"""Bundle the exact routed image, signed Android build, operator guide and evidence."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def package(build,lite_build=None):
    report=json.loads((build/'build_validation.json').read_text())
    bitstream=build/'impl/pnr/synth_display.fs'
    apk=ROOT/'realtime_synth/android_recorder/dist/TangRecorder-1.3.apk'
    app=json.loads((apk.parent.parent/'contest_validation.json').read_text())
    assert report['validated'] and report['firmware']==32
    assert hashlib.sha256(bitstream.read_bytes()).hexdigest()==report['sha256']
    assert hashlib.sha256(apk.read_bytes()).hexdigest()==app['sha256']
    assert report['monitor_profile']=='full'
    if lite_build:
        lite=json.loads((lite_build/'build_validation.json').read_text())
        lite_image=lite_build/'impl/pnr/synth_display.fs'
        assert lite['validated'] and lite['firmware']==32 and lite['monitor_profile']=='spectrum-only'
        assert hashlib.sha256(lite_image.read_bytes()).hexdigest()==lite['sha256']
        changed={name for name,value in report['source_sha256'].items() if lite['source_sha256'].get(name)!=value}
        assert changed=={'audio_monitor.v'} and report['source_sha256'].keys()==lite['source_sha256'].keys(),changed
    evidence=ROOT/'tests/contest_board'
    jtag=(evidence/'after_jtag.log').read_text(encoding='utf8')
    assert report['user_code'].lower() in jtag.lower(), 'Recorded board ID does not match the full image'
    spectrum=json.loads((evidence/'spectrum.json').read_text())
    assert spectrum['result']=='passed' and [spectrum['cases'][name]['monitor']['peak_count'] for name in ('all32','off16','off17')]==[32,31,31]
    onset=json.loads((evidence/'onset_board.json').read_text())
    assert onset['code'].lower()==report['user_code'].lower() and onset['result']=='passed', 'Physical key evidence does not match this image'
    report['board_evidence']='tests/contest_board/'
    report_path=ROOT/'firmware/contest32-build.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    if lite_build:
        lite_path=ROOT/'firmware/contest32-spectrum-build.json'
        lite_path.write_text(json.dumps(lite,indent=2)+'\n',encoding='utf8')
    path=ROOT/'output/Tang-脱机验收-v32.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        guide='Tang Mega 60K NEO · v32 脱机演示\n\nTang-v32-full.fs 是完整版，HDMI 直接显示波形、频谱、延时相图和数字起音时间。\n'
        if lite_build:
            guide+='Tang-v32-spectrum-only.fs 是仅谱峰版，保留 32/31 峰和起音时间。两者选一。\n'
        archive.writestr('先读我.txt',guide+'当前验收使用 Gowin Programmer 的 SRAM Program 操作，断电后需重新下载。\n'
                         '谱峰演示：J18 旋钮 B 选第 13 项「声谱观察」，短按 B 进 LIVE，再短按 B 看 32 峰、再短按看 31 峰。转 B 移缺口，点 A 静音退出。\n'
                         '实物起音：在琴键设置开启 32 键扫描，松开校准、开始演奏，再从 LIVE 按 H15 / C4。LAST I2S 是 FPGA 已收到事件到首个完整非零 I²S 左字的时间。\n'
                         '现场步骤及验收边界见「现场验收.md」。\n')
        archive.write(bitstream,'Tang-v32-full.fs')
        if lite_build:
            archive.write(lite_image,'Tang-v32-spectrum-only.fs')
            archive.write(lite_path,'验证/精简版整机布局.json')
        archive.write(apk,apk.name)
        for name in ('现场验收.md','赛题二问答与验收测量.md','资源与电脑分析.md','PC-AUDIO.md'):
            archive.write(ROOT/name,name)
        archive.write(report_path,'验证/完整版整机布局.json')
        archive.write(ROOT/'realtime_synth/android_recorder/contest_validation.json','验证/安卓验证.json')
        archive.write(ROOT/'tests/contest_keys/results/validation.json','验证/键位协议.json')
        archive.write(ROOT/'tools/analyze_onset_csv.py','tools/analyze_onset_csv.py')
        archive.write(ROOT/'tests/contest_latency/README.md','tests/contest_latency/README.md')
        for example in (ROOT/'tests/contest_latency/csv_examples').glob('*.csv'):
            archive.write(example,'tests/contest_latency/csv_examples/'+example.name)
        for name in ('after_jtag.log','spectrum.json','fft.csv','all32.pcm','off16.pcm','off17.pcm','heard.json','onset_board.json'):
            archive.write(evidence/name,'验证/'+name)
        for item,name in [('contest_latency/results/validation.json','延迟仿真.json'),('contest_latency/results/meter.json','起音标记对照.json'),('contest_latency/results/gate_hold/validation.json','长按键门级对照.json'),('contest_latency/results/recovery.json','松键恢复回归.json'),('monitor/results/test32.png','32峰RTL预览.png'),('monitor/results/test31.png','31峰RTL预览.png')]:
            archive.write(ROOT/'tests'/item,'验证/'+name)
        archive.write(ROOT/'profiles/spectrum-only/tests/monitor/results/test31.png','验证/精简版31峰RTL预览.png')
    print(path,hashlib.sha256(path.read_bytes()).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('lite_build',type=Path,nargs='?',help='Also include a validated spectrum-only build')
    args=parser.parse_args();package(args.build.resolve(),args.lite_build.resolve() if args.lite_build else None)
