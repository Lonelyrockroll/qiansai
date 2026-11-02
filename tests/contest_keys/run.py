"""Send Android-produced request frames through the actual Bluetooth UART pins."""
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1];FPGA=ROOT/'fpga';APP=ROOT/'realtime_synth/android_recorder'
SOURCES=('bt_console.v','bt_link.v','bt_uart_rx.v','bt_uart_tx.v','guide_transport.v','guide_player.v',
         'key_layout.v','score_store.v','record_stream.v','record_filter.v','ima_encoder.v')

def execute(args,cwd):
    p=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,timeout=150)
    log=(p.stdout+p.stderr).decode('utf8',errors='replace');
    if p.returncode:raise RuntimeError(log)
    return log

def main():
    jdk=Path(os.environ.get('JAVA_HOME') or 'E:/PyCharm_2026.1/jbr')/'bin'
    iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe';vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    results=HERE/'results';results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tang-key-rtl-') as folder:
        work=Path(folder);source=APP/'src/main/java/cn/tangsynth/recorder'
        classes=['AudioFrame','GuideProtocol','ScoreProtocol','KeyProtocol','StreamReader','WavTake']
        execute([jdk/'javac','-encoding','UTF-8','-d',work,*[source/(c+'.java') for c in classes],
                 APP/'tests/ProtocolTest.java',APP/'tests/KeyWireTest.java'],work)
        jcmd=[jdk/'java','-cp',work,'cn.tangsynth.recorder.KeyWireTest']
        execute([*jcmd,'requests','key-requests.hex'],work)
        execute([iv,'-g2012','-s','tb_layout','-o',work/'test.vvp',HERE/'tb_layout.v',*[FPGA/n for n in SOURCES]],work)
        rtl=execute([vvp,work/'test.vvp'],work);java=execute([*jcmd,'verify','key-wire.hex'],work)
        if 'PASS ' not in rtl or 'PASS ' not in java:raise RuntimeError(rtl+java)
        for name in ('key-requests.hex','key-wire.hex'):shutil.copyfile(work/name,results/name)
    result=dict(passed=True,scope='Real serialized RTL UART, FPGA mapping scan and actual Android frame encoder/decoder; no board claim.',
                rtl=rtl.splitlines()[0],android=java.strip(),source_sha256={s:hashlib.sha256((FPGA/s).read_bytes()).hexdigest() for s in SOURCES})
    (results/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(rtl+java)

if __name__=='__main__':main()
