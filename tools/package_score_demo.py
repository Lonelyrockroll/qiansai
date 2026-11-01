"""Bundle the validated SRAM image, signed APK and the exact two-page demo PDF."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def package(build, evidence):
    report=json.loads((build/'build_validation.json').read_text())
    image=build/'impl/pnr/synth_display.fs'
    apk=ROOT/'realtime_synth/android_recorder/dist/TangRecorder-1.2.apk'
    pdf=ROOT/'output/pdf/score-demo.pdf'
    assert report['firmware']==31 and report['validated']
    assert hashlib.sha256(image.read_bytes()).hexdigest()==report['sha256']
    app=json.loads((ROOT/'realtime_synth/android_recorder/score_validation.json').read_text())
    assert hashlib.sha256(apk.read_bytes()).hexdigest()==app['sha256']
    assert pdf.read_bytes()==(ROOT/'realtime_synth/android_recorder/src/main/assets/score-demo.pdf').read_bytes()
    confirmed=json.loads((evidence/'acceptance.json').read_text(encoding='utf8')) if (evidence/'acceptance.json').is_file() else {}
    report['hardware']=confirmed
    summary=ROOT/'firmware/score31-build.json'
    summary.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    instructions=(
        'Tang 电子琴 · PDF 曲谱验收包\r\n\r\n'
        '1. 用 Gowin Programmer 选择 GW5AT-60B / SRAM Program，将 Tang-score-v31.fs 临时下载。\r\n'
        '2. 手机上安装 TangRecorder-1.2.apk，断开蓝牙调试宝，在演奏助手重新连接 =BTNU1。\r\n'
        '3. 等“曲谱显示已就绪”，进入“PDF 曲谱”→“示例 PDF”→“发送本页并显示”。\r\n'
        '   要演示选文件，可把小星星示范谱.pdf存入手机，再从“选择 PDF”打开。\r\n'
        '4. 第一页应显示 1/2，点“下一页并发送”显示 2/2，“上一页并发送”可返回。\r\n'
        '5. 曲谱全屏时短按旋钮 B 或 KEY.0 返回演奏界面。“显示已传页面”可重新打开。\r\n\r\n'
        '当前页可在手机断开后继续看；翻页需要蓝牙连接。固件和上传页面断电后需重新加载。\r\n'
        f'码流 User Code：{report["user_code"]}\r\n')
    path=ROOT/'output/Tang-曲谱演示-v31.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(image,'Tang-score-v31.fs');z.write(apk,apk.name);z.write(pdf,'小星星示范谱.pdf')
        z.writestr('演示步骤.txt',instructions.encode('utf-8-sig'))
        z.write(summary,'验证/build-report.json')
        for name in ('after_jtag.log','startup.json','acceptance.json','phone_pages.json','page-02-readback.json','phone-page-02.png'):
            if (evidence/name).is_file():z.write(evidence/name,'验证/'+name)
    print(path, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build',type=Path);ap.add_argument('evidence',type=Path)
    a=ap.parse_args();package(a.build.resolve(),a.evidence.resolve())
