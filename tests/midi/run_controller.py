"""Verify MIDI selection, diagnostic packets and offline lifetime in the real controller."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tests/score_controller'
spec=importlib.util.spec_from_file_location('controller_fixture',BASE/'run.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
fixture.CONSTANTS.update(midi_bytes=0x12345678,midi_messages=0x10203040,midi_framing=3,midi_overflows=2,
    midi_last_note=61,midi_last_velocity=100,midi_last_channel=2,midi_held=4,midi_queued=5,
    midi_sounding=6,midi_pedals=5,midi_ignored=7,midi_steals=8,midi_rx_high=1)
fixture.CONTROLLED.add('midi_fault')
prefix=(BASE/'tb_score_controller.v').read_text().split(' task enter_live;')[0]
prefix=prefix.replace(' integer failures=0;', ' integer failures=0;')
body='''
 reg midi_fault=0;
 initial begin
  force dut.rx_data=inject_data;force dut.rx_valid=inject_valid;force dut.rx_error=1'b0;
  score_valid=0;score_visible=0;score_show_requested=0;score_reserved=0;capture_ready=0;
  repeat(5)@(negedge clk);rst=0;repeat(5)@(negedge clk);
  clear_payload();transaction(37,0);
  check(reply[7]==0 && reply[9]==4 && reply[10]==5,"MIDI status counts and mode");
  check({reply[14],reply[13],reply[12],reply[11]}==32'h12345678,"received byte count is lossless");
  check({reply[18],reply[17],reply[16],reply[15]}==32'h10203040 && reply[23]==61,"message count and pitch");
  payload[1]=1;transaction(37,0);
  check(reply[7]==228 && reply[8]==2 && reply[9]==5 && reply[11]==7 && reply[13]==8 && reply[15]==6,"extended MIDI diagnostics");
  clear_payload();payload[0]=1;payload[1]=3;transaction(37,0);
  check(dut.key_mode==3 && !amp_hold,"mode selection leaves PA muted");
  clear_payload();transaction(6,0);repeat(25000)@(negedge clk);
  check(amp_hold && !dut.timed_out,"MIDI mode ignores PC heartbeat timeout");
  clear_payload();payload[0]=2;transaction(3,0);check(amp_hold,"atomic browser detach preserves MIDI session");
  clear_payload();payload[0]=3;transaction(37,0);check(!amp_hold,"explicit MIDI mute");
  clear_payload();transaction(6,0);@(negedge clk);midi_fault=1;@(negedge clk);midi_fault=0;repeat(12)@(negedge clk);
  check(!amp_hold && dut.ui_notice==5,"MIDI transport fault mutes explicitly");
  loop_recording=1;clear_payload();payload[0]=1;payload[1]=0;transaction(37,4);check(dut.key_mode==3,"input selection preserves recording");loop_recording=0;
  transaction(37,0);check(dut.key_mode==0,"return to PC mode");
  clear_payload();transaction(6,0);repeat(25000)@(negedge clk);
  check(!amp_hold && dut.timed_out,"PC mode retains its watchdog");
  clear_payload();payload[0]=1;payload[1]=4;transaction(37,3);
  if(failures!=0)$fatal(1,"MIDI controller failures %0d",failures);
  $display("PASS MIDI controller %0d checks, %0d UART replies",checks,seqno);$finish;
 end
 initial begin #100000000;$fatal(1,"controller timeout");end
endmodule
'''
source=(ROOT/'fpga/uart_control_display.v').read_text()
instance=fixture.instance(source).replace('.WATCHDOG_CYCLES(100000000)', '.WATCHDOG_CYCLES(10000)')
with tempfile.TemporaryDirectory(prefix='midi-controller-') as directory:
    path=Path(directory);(path/'controller_instance.vh').write_text(instance)
    (path/'tb.v').write_text(prefix+body)
    subprocess.run(['E:/iverilog/bin/iverilog.exe','-g2012','-I',str(path),'-s','tb_score_controller',
        '-o',str(path/'sim.vvp'),str(path/'tb.v'),*[str(ROOT/'fpga'/name) for name in ('uart_control_display.v','uart_rx.v','uart_tx.v')]],check=True)
    run=subprocess.run(['E:/iverilog/bin/vvp.exe',str(path/'sim.vvp')],text=True,errors='replace',capture_output=True,timeout=45)
result=dict(passed=run.returncode==0,output=run.stdout+run.stderr,
    source_sha256={name:hashlib.sha256((ROOT/'fpga'/name).read_bytes()).hexdigest()
                   for name in ('uart_control_display.v','uart_rx.v','uart_tx.v')})
folder=Path(__file__).resolve().parent/'results';folder.mkdir(exist_ok=True)
(folder/'controller.json').write_text(json.dumps(result,indent=2)+'\n')
print(result['output'])
if run.returncode:raise SystemExit(run.returncode)
