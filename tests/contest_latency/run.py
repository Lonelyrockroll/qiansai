"""Exercise the production keyboard, mixer and audio pins. No hardware access."""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FPGA = HERE.parents[1] / 'fpga'
SOURCES = (
    'synth_display_top', 'keyboard_input', 'white_key_map', 'note_rom',
    'performance_looper', 'performance_router', 'synth_engine_shared', 'midi_input', 'midi_decoder', 'uart_rx',
    'modal32', 'modal32_coeffs', 'waveform_rom', 'piano_modal_tables_compact',
    'audio_output_limited', 'pcm_peak_limiter', 'audio_effects', 'chorus_lfo', 'audio_tx',
    'bt_console', 'guide_transport', 'key_layout', 'onset_meter', 'key_release_guard',
)
COLUMNS = ('case', 'key', 'timbre', 'max_level', 'scan_phase_clocks', 'ramp_codes_per_scan',
           'motion_to_threshold_ns', 'kept_aperture_ns', 'scanner_handshake_ns',
           'engine_handshake_ns', 'pcm_ns', 'pt_word_ns', 'i2s_word_ns',
           'i2s_abs16_ns', 'velocity_code', 'event_level', 'serial_peak')
COLD_COLUMNS = ('amplifier_ready_ns','kept_aperture_ns','scanner_handshake_ns',
                'engine_handshake_ns','pcm_ns','pt_word_ns','i2s_word_ns','i2s_abs16_ns')
METER_COLUMNS = ('case','accepted_to_external_i2s_ns','marker_width_ns','display_us','display_error_ns')


def save_meter(lines, directory, hashes, expected_cases):
    selected = [line for line in lines if line.startswith('METER ')]
    cases = [dict(zip(METER_COLUMNS,map(int,line.split()[1:]),strict=True)) for line in selected]
    assert len(cases) == expected_cases
    assert all(row['marker_width_ns']-row['accepted_to_external_i2s_ns']==20 and
               abs(row['display_error_ns'])<=1000 for row in cases)
    (directory/'meter.json').write_text(json.dumps({'cases':cases,'source_sha256':hashes},indent=2)+'\n')
    (directory/'meter.log').write_text(''.join(selected),encoding='utf8')


def summarize(rows):
    assert len(rows) == 18
    replay_keys = COLUMNS[1:]
    assert all(rows[0][key] == rows[17][key] for key in replay_keys), 'same-phase replay differs'
    phase_sweep = rows[0:9]
    soft_mid_hard = [rows[11:14], rows[14:17]]
    for group in soft_mid_hard:
        for field in ('velocity_code','event_level','serial_peak'):
            assert group[0][field] < group[1][field] < group[2][field], (field,group)
    for small,large in zip(*soft_mid_hard):
        assert abs(small['event_level']/small['max_level'] - large['event_level']/large['max_level']) < .012
    return {
        'scope': '50 MHz RTL simulation, 32-channel scan, modeled SOC/EOC sampling, warm performance session, idle Loop/drums, neutral pitch and bypassed FX.',
        'case_count':len(rows),'same_phase_repeat_exact':True,
        'largest_tested_threshold_to_i2s_word_ms':max(row['i2s_word_ns'] for row in rows)/1e6,
        'largest_tested_threshold_to_i2s_abs16_ms':max(row['i2s_abs16_ns'] for row in rows)/1e6,
        'largest_tested_threshold_to_pt_word_ms':max(row['pt_word_ns'] for row in rows)/1e6,
        'largest_tested_motion_start_to_i2s_abs16_ms':max(row['motion_to_threshold_ns']+row['i2s_abs16_ns'] for row in rows)/1e6,
        'c4_phase_sweep_i2s_word_ms':[fn(row['i2s_word_ns'] for row in phase_sweep)/1e6 for fn in (min,max)],
        'scan_revisit_ms':.48064,'audio_tick_ms':.02048,
        'physical_scope_measurement':False,'zero_asynchronous_input_jitter':False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=HERE/'.work')
    parser.add_argument('--output',type=Path,default=HERE/'results')
    parser.add_argument('--meter-only',action='store_true',help='just compare the on-board marker and two C4 LCD readings with an external I2S decoder')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True,exist_ok=True)
    results = args.output.resolve(); results.mkdir(parents=True,exist_ok=True)
    compiler=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe'
    runtime=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    names=[FPGA/(n+'.v') for n in SOURCES]
    # Pin every production input used in this build, including later top-level edits.
    source_sha={}
    for p in names:
        data=p.read_bytes();source_sha[p.name]=hashlib.sha256(data).hexdigest();(work/p.name).write_bytes(data)
    binary=work/'latency.vvp'
    subprocess.run([compiler,'-g2012','-i','-s','tb_latency','-o',str(binary),str(HERE/'tb_latency.v'),
                    *[str(work/p.name) for p in names]],cwd=FPGA,check=True)
    def simulate(filename,arguments):
        with (results/filename).open('w',encoding='utf8') as out:
            job=subprocess.Popen([runtime,str(binary),*arguments],cwd=FPGA,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            lines=[]
            for line in job.stdout:
                print(line.rstrip(),flush=True);out.write(line);out.flush();lines.append(line)
            if job.wait()!=0 or not any(line.startswith('PASS ') for line in lines):raise RuntimeError('HDL test did not pass')
            return lines
    if args.meter_only:
        lines=simulate('meter.log',['+CHECK_METER','+METER_ONLY'])
        save_meter(lines,results,source_sha,2)
        return
    lines=simulate('latency.log',['+CHECK_METER'])
    records=[dict(zip(COLUMNS,map(int,line.split()[1:]),strict=True)) for line in lines if line.startswith('NOTE ')]
    report=summarize(records)
    cold_lines=simulate('cold.log',['+COLD','+CHECK_METER'])
    cold=next(line for line in cold_lines if line.startswith('COLD '))
    save_meter(lines+cold_lines,results,source_sha,19)
    report['cold_simultaneous_arm_and_step']=dict(zip(COLD_COLUMNS,map(int,cold.split()[1:]),strict=True))
    with (results/'measurements.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS);writer.writeheader();writer.writerows(records)
    report['source_sha256']=source_sha
    (results/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2))


if __name__=='__main__':main()
