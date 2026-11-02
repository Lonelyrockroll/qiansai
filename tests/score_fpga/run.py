"""Score uploader/shared framebuffer regression, including unchanged guide benches."""
import hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RESULTS=HERE/'results'
SOURCES=['guide_transport.v','key_layout.v','guide_player.v','score_store.v','pcm_capture.v','score_capture_ram.v']
def run(args,work):
 p=subprocess.run(list(map(str,args)),cwd=work,text=True,capture_output=True,timeout=180)
 if p.returncode or 'FATAL:' in p.stdout:raise RuntimeError(p.stdout+'\n'+p.stderr)
 return p.stdout

def main():
 RESULTS.mkdir(exist_ok=True)
 iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
 vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
 reports={};source_hash={}
 with tempfile.TemporaryDirectory(prefix='tang-score-') as folder:
  work=Path(folder)
  # Compile snapshots: simultaneous integration edits cannot falsify hashes.
  for name in SOURCES:
   data=(ROOT/'fpga'/name).read_bytes();(work/name).write_bytes(data);source_hash[name]=hashlib.sha256(data).hexdigest()
  for name in ('score-upload.hex','score-raw.hex'):
   shutil.copyfile(ROOT/'realtime_synth/android_recorder/tests/fixtures/score'/name,work/name)
  for name in ('demo-upload.hex','demo-events.hex'):
   shutil.copyfile(ROOT/'realtime_synth/android_recorder/tests/fixtures'/name,work/name)
  benches={'tb_score':HERE/'tb_score.v','tb_guide':ROOT/'tests/guide_fpga/tb_guide.v','tb_java_upload':ROOT/'tests/guide_fpga/tb_java_upload.v'}
  for name,bench in benches.items():
   run([iv,'-g2012','-s',name,'-o',work/(name+'.vvp'),bench,*[work/n for n in SOURCES]],work)
   log=run([vvp,work/(name+'.vvp'),'+ACK='+(RESULTS/(name+'-acks.hex')).as_posix()],work)
   if 'PASS ' not in log:raise RuntimeError(log)
   (RESULTS/(name+'.log')).write_text(log,encoding='utf8');reports[name]=log.splitlines()[0]
 full=bytes(int(x,16) for x in (RESULTS/'tb_score-acks.hex').read_text().split())
 # The first 848 replies cover 845 original requests and 3 intentional retries.
 java=b''.join(full[i*24:(i+1)*24] for i in range(848) if i not in (1,152,846))
 fixture=bytes(int(x,16) for x in (ROOT/'realtime_synth/android_recorder/tests/fixtures/score/score-upload.hex').read_text().split())
 assert len(java)==845*24
 for i in range(845):
  ack=java[i*24:(i+1)*24];req=fixture[i*28:(i+1)*28]
  assert ack[:5]==b'TPAK\x01' and ack[5:7]==req[3:5] and ack[7]==0
 (RESULTS/'score-java-acks.hex').write_text(''.join(f'{b:02x}\n' for b in java),encoding='ascii')
 result={'result':'passed','scope':'Actual score_store, transport and shared capture RAM RTL; full Android page checked on both asynchronous pixel and sys ports. No phone/board claim.','tests':reports,'source_sha256':source_hash,'score_fixture_sha256':hashlib.sha256(fixture).hexdigest(),'java_reply_bytes':len(java)}
 (RESULTS/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
