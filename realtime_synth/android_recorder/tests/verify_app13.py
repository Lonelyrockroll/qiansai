"""Reproduce Java/RTL fixture checks for Tang Android 1.3 with a desktop JDK."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import tempfile

TESTS=Path(__file__).resolve().parent
APP=TESTS.parent
REPO=APP.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='also fetch the two public Mutopia files over HTTPS')
    parser.add_argument('--pcm',type=Path,help='optional folder with record_wire.bin and record_ref.pcm')
    args=parser.parse_args()
    jdk=Path(os.environ.get('JAVA_HOME') or 'E:/PyCharm_2026.1/jbr')/'bin'
    source=APP/'src/main/java/cn/tangsynth/recorder'
    files=[p for p in source.glob('*.java') if p.name not in ('MainActivity.java','PdfScore.java')]
    files+=list((TESTS/'stubs').rglob('*.java'))+list(TESTS.glob('*.java'))
    online=('OnlineScoreTest','--live') if args.live else ('OnlineScoreTest',)
    cases=[online,('KeySessionTest',),('GuideTest',),
           ('GuideSessionTest',APP/'src/main/assets/guide-demo.mid'),('ScoreTest',),('ScoreSessionTest',),
           ('GuideAckTest',REPO/'tests/guide_fpga/results/demo-acks.hex'),
           ('MixedConsoleTest',REPO/'tests/guide_fpga/results/console-timeout-wire.hex','27'),
           ('ScoreAckTest',REPO/'tests/score_fpga/results/score-java-acks.hex',TESTS/'fixtures/score/score-upload.hex')]
    if args.pcm:cases.append(('ProtocolTest',args.pcm.resolve()))
    with tempfile.TemporaryDirectory(prefix='tang-app13-') as folder:
        subprocess.run([str(jdk/'javac'),'-encoding','UTF-8','-d',folder,*map(str,files)],check=True)
        def run(case):
            result=subprocess.run([str(jdk/'java'),'-Dfile.encoding=UTF-8','-cp',folder,'cn.tangsynth.recorder.'+case[0],*map(str,case[1:])],capture_output=True,timeout=100)
            if result.returncode:raise RuntimeError((result.stdout+result.stderr).decode('utf8',errors='replace'))
            return result.stdout.decode('utf8').strip()
        with ThreadPoolExecutor(max_workers=4) as pool:
            for output in pool.map(run,cases):print(output)


if __name__=='__main__':main()
