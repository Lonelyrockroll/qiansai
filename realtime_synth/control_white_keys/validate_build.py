"""Check all routed IOs and every reported timing clock before SRAM download."""
from pathlib import Path
import re,json,html,hashlib,argparse
from check_sources import inspect
R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--build-dir',type=Path,default=R,help='isolated layout using the same source manifest')
build_dir=parser.parse_args().build_dir.resolve()
B=build_dir/'impl/pnr/synth_display'
source_hashes=inspect()
manifest=json.loads((build_dir/'source_manifest.json').read_text())
assert source_hashes==manifest, 'RTL changed after the build began; rebuild before downloading.' 
timing=Path(str(B)+'_tr_content.html').read_text()
pins=Path(str(B)+'.rpt.txt').read_text();fs=Path(str(B)+'.fs')
def rows(name):
    table=timing.split(f'name="{name}"',1)[1].split('</table>',1)[0]
    return [[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',r,re.S)]
        for r in re.findall(r'<tr[^>]*>(.*?)</tr>',table,re.S)][1:]
freq=rows('Max_Frequency_Report');slack=rows('Total_Negative_Slack_Report')
assert all(float(r[3].split('(')[0])>=float(r[2].split('(')[0]) for r in freq),freq
assert all(float(r[2])>=0 and int(r[3])==0 for r in slack),slack
assert {r[0] for r in slack}=={'sys_clk','serial_clk','pixel_clk','usb_clk'},slack
checked=[]
for signal,loc in re.findall(r'IO_LOC\s+"([^"]+)"\s+([^;]+);',(R/'display.cst').read_text()):
    row=[line.split('|') for line in pins.splitlines() if line.split('|')[0].strip()==signal]
    assert len(row)==1,(signal,row)
    actual=row[0][2].strip().split('/')[0];expected=loc.strip()
    assert actual==expected,(signal,actual,expected)
    checked.append(dict(signal=signal,pin=actual))
record=dict(result='passed',frequency=freq,slack=slack,pins=checked,
    source_hashes=source_hashes,
    sha256=hashlib.sha256(fs.read_bytes()).hexdigest(),
    user_code=re.search(r'//UserCode:\s*(\S+)',fs.read_text()[:2000]).group(1),
    warning='PR1014 retained. Tight 50 MHz synthesis-path timing margin. Static timing is not an electrical/video-link test.',
    reference='screen_edid.json; 49 MHz pixel / 245 MHz serial, 1312x622 total, -H +V')
(build_dir/'build_validation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='pins'},indent=2))
