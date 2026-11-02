"""Independent controller regression: trusted RX bytes, genuine TX-pin 8N1 decode."""
import hashlib,json,re,shutil,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RESULTS=HERE/'results'
CONTROLLED=set('clk rst capture_busy capture_ready capture_id capture_count capture_capacity capture_read_data score_ui_ready score_valid score_show_requested score_visible score_loading score_reserved score_page_index score_page_count score_received_compressed score_decoded_bytes ui_valid ui_action ui_value amp_ready amp_muted engine_cleared router_held active_voices fx_tail fx_pending loop_playing loop_recording loop_pending loop_layers loop_counts native_panic'.split())
OUTPUTS=set('uart_out capture_read_address capture_command_valid capture_command_arm score_ui_valid score_ui_action ui_ready amp_hold guide_ui_valid guide_ui_action panic loop_command_valid monitor_fade'.split())
CONSTANTS={'uart_in':1,'cfg_ready':1,'pc_pad_ready':1,'amp_muted':1,'amp_ready':1,'guide_valid':1,'guide_playing':1,'guide_demo':1,'guide_speed':2,'guide_count':84,'guide_index':12,'guide_time_cs':125,'guide_duration_cs':2400,'guide_current':0x4000}
def instance(text):
 ports=text.split(')(',1)[1].split(');',1)[0]
 fields=[];direction=None;width=1
 for field in ports.replace('\n',' ').split(','):
  field=field.strip()
  m=re.match(r'(input|output)\s+(?:wire|reg)\s+(?:signed\s+)?(?:\[(\d+):(\d+)\]\s*)?(\w+)$',field)
  if m:direction=m[1];width=int(m[2])-int(m[3])+1 if m[2] else 1;name=m[4]
  else:
   assert re.fullmatch(r'\w+',field),field
   name=field
  if name in CONTROLLED or name in OUTPUTS:fields.append(f'.{name}({name})')
  elif direction=='input':fields.append(f".{name}({width}'d{CONSTANTS.get(name,0)})")
 return 'uart_control_display #(.CLK_HZ(1000000),.BAUD(100000),.WATCHDOG_CYCLES(100000000)) dut(\n'+',\n'.join(fields)+'\n);\n'
def main():
 RESULTS.mkdir(exist_ok=True);iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe';vvp=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
 sources={name:(ROOT/'fpga'/name).read_bytes() for name in ('uart_control_display.v','uart_rx.v','uart_tx.v')}
 with tempfile.TemporaryDirectory(prefix='score-controller-') as folder:
  work=Path(folder)
  for name,data in sources.items():(work/name).write_bytes(data)
  (work/'controller_instance.vh').write_text(instance(sources['uart_control_display.v'].decode()),encoding='ascii')
  compile=subprocess.run([iv,'-g2012','-I',str(work),'-s','tb_score_controller','-o',str(work/'test.vvp'),str(HERE/'tb_score_controller.v'),*[str(work/name) for name in sources]],capture_output=True,text=True)
  if compile.returncode:raise RuntimeError(compile.stdout+compile.stderr)
  result=subprocess.run([vvp,str(work/'test.vvp')],capture_output=True,text=True,timeout=60)
  (RESULTS/'controller.log').write_text(result.stdout+result.stderr,encoding='utf8')
  report={'passed':result.returncode==0,'scope':'trusted RX byte injection; independent physical serial TX decoder, no production RTL edits','stdout':result.stdout,'source_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in sources.items()}}
  (RESULTS/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
  print(result.stdout)
  if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
