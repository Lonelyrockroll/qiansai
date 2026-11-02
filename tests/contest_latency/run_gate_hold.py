"""Compare H15 sustained-input behavior in RTL and Gowin post-P&R simulation.

Builds an isolated real scanner; no board access and no change to production RTL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
FPGA=HERE.parents[1]/'fpga'
FIXTURE=HERE/'gate_fixture'
DEFAULT_GOWIN=Path('E:/Gowin_edu/Gowin_V1.9.11.03_Education_x64/IDE/bin/gw_sh.exe')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args,work,log,timeout):
    result=subprocess.run(list(map(str,args)),cwd=work,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          timeout=timeout,check=False)
    output=result.stdout.decode(errors='replace')
    log.write_text(output,encoding='utf8')
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed; see {log}')
    return output


def prepare(work,variant):
    work.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(FIXTURE/'probe.v',work/'probe.v')
    shutil.copyfile(FIXTURE/'pre_fix_keyboard.v' if variant=='original' else FPGA/'keyboard_input.v',work/'keyboard_input.v')
    for name in ('white_key_map.v','note_rom.v'):shutil.copyfile(FPGA/name,work/name)
    names=('probe.v','keyboard_input.v','white_key_map.v','note_rom.v')
    project=ET.parse(FPGA/'synth_display.gprj');files=project.find('FileList');files.clear()
    for name in names:ET.SubElement(files,'File',path=name,type='file.verilog',enable='1')
    project.write(work/'probe.gprj',encoding='utf-8',xml_declaration=True)
    (work/'build.tcl').write_text('cd [file dirname [info script]]\nopen_project probe.gprj\n'
        'set_option -top_module probe\nset_option -output_base_name probe\n'
        'set_option -use_cpu_as_gpio 1\nset_option -gen_verilog_sim_netlist 1\nrun all\n')
    return names


def read_result(output):
    m=re.search(r'^RESULT\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',output,re.M)
    if not m:raise RuntimeError('Missing completed long-hold simulation result')
    return dict(zip(('ons','offs','held_scans','missing_held_bit_scans'),map(int,m.groups())))


def h15_cone(netlist):
    """Evaluate the emitted LUT cones, independently from the serial stimulus.

    Gowin Education 1.9.11.03 names the physical key counter `physical_d` and
    retains binary FSM state and delta_work flop nets. If a future mapper uses
    different names, the pin-level sustained-input test remains applicable.
    """
    text=netlist.read_text(encoding='utf8');drivers={}
    inits={k:int(v,16) for k,v in re.findall(r"defparam\s+(\S+)\s+\.INIT=\d+'h([0-9A-Fa-f]+)",text)}
    for kind,inst,body in re.findall(r'^(\w+)\s+(\S+)\s+\((.*?)\n\);',text,re.M|re.S):
        ports={p:v.strip() for p,v in re.findall(r'\.(\w+)\(([^()]+)\)',body)}
        out=ports.get('F') or ports.get('Q') or ports.get('O')
        if out:drivers[out]=(kind,inst,ports)

    def row(key,state,delta,old_q,gate,valid):
        known={'GND':0,'VCC':1,'play_d':1,'rst_d':0,'recalibrate_d':0,'fault_d':0,'cal_d':1,
               'valid_d':valid,'gate_d':gate,'ready_d':1,'eoc_d':1,'\\keys/seen_low':1}
        for prefix,value,width in [('physical_d',key,5),('\\keys/state ',state,4),('\\keys/timer ',20,20),
                                   ('\\keys/delta_work ',delta,13),('mask_d',old_q<<14,32)]:
            for i in range(width):known[f'{prefix}[{i}]']=(value>>i)&1

        def evaluate(net):
            if net not in known:
                kind,inst,ports=drivers[net]
                if kind.startswith('LUT'):
                    address=sum(evaluate(ports[f'I{i}'])<<i for i in range(int(kind[3:])))
                    value=(inits[inst]>>address)&1
                elif kind.startswith('MUX2'):
                    value=evaluate(ports['I1' if evaluate(ports['S0']) else 'I0'])
                elif kind=='IBUF':value=evaluate(ports['I'])
                else:raise ValueError(f'unexpected {kind} in cone at {net}')
                known[net]=value
            return known[net]

        kind,instance,ports=drivers['mask_d[14]']
        if kind!='DFFRE':raise ValueError(f'unexpected H15 FF type {kind}')
        d,ce,reset=(evaluate(ports[name]) for name in ('D','CE','RESET'))
        new_q=0 if reset else d if ce else old_q
        return dict(key=key,state=state,delta=delta,old_q=old_q,gate=gate,valid=valid,
                    ff_instance=instance,ff_ports=ports,D=d,CE=ce,RESET=reset,next_q=new_q)

    try:
        return [row(*args) for args in ((14,8,720,1,1,0),(14,10,720,0,1,1),(13,8,720,1,1,0))]
    except (KeyError,ValueError) as exc:
        return {'unavailable_with_this_mapper':str(exc)}


def summarize(builds,output,hold_scans):
    output.mkdir(parents=True,exist_ok=True)
    cases={}
    for variant,folder in builds.items():
        net=folder/'impl/pnr/probe.vo'
        record={'scanner_sha256':digest(folder/'keyboard_input.v'),'probe_sha256':digest(folder/'probe.v'),
                'postroute_vo_sha256':digest(net)}
        for kind in ('rtl','gate'):
            contents=(folder/f'full-{kind}.log').read_text(encoding='utf-8-sig')
            record[kind]=read_result(contents)
            sensed=re.findall(r'^HELD .*?sensed=([0-9a-fA-F]+)$',contents,re.M)
            assert len(sensed)==hold_scans and all(int(value,16)==1<<14 for value in sensed)
            (output/f'{variant}-{kind}.log').write_text(contents,encoding='utf8')
        record['h15_lut_cone']=h15_cone(net)
        cases[variant]=record
    expected={'ons':1,'offs':1,'held_scans':hold_scans,'missing_held_bit_scans':0}
    assert cases['original']['rtl']==expected and cases['final']['rtl']==expected
    assert cases['final']['gate']==expected, cases['final']
    report={'scope':'Isolated GW5AT-60B scanner, functional simulation of routed primitives using the Gowin library, no SDF. Not a hardware measurement or a simulation of the encrypted full-board netlist.',
            'user_visible_key':'H15 / zero-based physical 14', 'baseline_code':4000,'hold_code':4720,
            'clock_hz':50_000_000,'adc_conversion_clocks':20,'hold_scans':hold_scans,
            'hold_ms':hold_scans*0.48064,'internal_state_forced':False,
            'testbench_sha256':digest(HERE/'tb_gate_hold.v'),'original_synth_mismatch_reproduced':cases['original']['gate']!=expected,
            'cases':cases}
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gowin',type=Path,default=DEFAULT_GOWIN)
    p.add_argument('--work',type=Path,default=HERE/'.work/gate_hold')
    p.add_argument('--output',type=Path,default=HERE/'results/gate_hold')
    args=p.parse_args();gw=args.gowin.resolve();prim=gw.parents[1]/'simlib/gw5a/prim_sim.v'
    iv=shutil.which('iverilog') or 'E:/iverilog/bin/iverilog.exe';vv=shutil.which('vvp') or 'E:/iverilog/bin/vvp.exe'
    builds={}
    for variant in ('original','final'):
        work=(args.work/variant).resolve();builds[variant]=work;names=prepare(work,variant)
        command([gw,work/'build.tcl'],work,work/'build.log',300)
        for kind,sources in [('rtl',names),('gate',('impl/pnr/probe.vo',prim))]:
            binary=f'full-{kind}.vvp'
            command([iv,'-g2012','-s','tb_gate_hold','-o',binary,HERE/'tb_gate_hold.v',*sources],work,work/f'compile-{kind}.log',120)
            command([vv,binary,'+N=32'],work,work/f'full-{kind}.log',900)
    summarize(builds,args.output.resolve(),32)


if __name__=='__main__':main()
