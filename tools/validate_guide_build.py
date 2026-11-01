"""Validate a routed v30 image against the current sources, IOs and all clocks."""
import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fpga'))
from check_sources import inspect


def validate(build):
    manifest = json.loads((build / 'source_manifest.json').read_text())
    expected = {Path(name).name: sha for name, sha in inspect().items()}
    built = {Path(name).name: sha for name, sha in manifest.items()}
    assert len(built) == len(manifest) and built == expected, 'Build/source mismatch'
    for name, sha in built.items():
        assert hashlib.sha256((build/name).read_bytes()).hexdigest() == sha, name
    prefix = build / 'impl/pnr/synth_display'
    timing = Path(str(prefix) + '_tr_content.html').read_text()
    report = Path(str(prefix) + '.rpt.txt').read_text()
    bitstream = Path(str(prefix) + '.fs')

    def rows(section):
        table = timing.split('name="' + section + '"', 1)[1].split('</table>', 1)[0]
        return [[html.unescape(re.sub('<[^>]+>', '', cell)).strip()
                 for cell in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)]
                for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S)][1:]

    frequency = rows('Max_Frequency_Report')
    slack = rows('Total_Negative_Slack_Report')
    assert frequency and all(float(r[3].split('(')[0]) >= float(r[2].split('(')[0]) for r in frequency), frequency
    assert all(float(r[2]) >= 0 and int(r[3]) == 0 for r in slack), slack
    assert {r[0] for r in slack} == {'sys_clk', 'serial_clk', 'pixel_clk', 'usb_clk'}, slack
    pins = []
    for signal, location in re.findall(r'IO_LOC\s+"([^"]+)"\s+([^;]+);', (ROOT/'fpga/display.cst').read_text()):
        found = [line.split('|') for line in report.splitlines() if line.split('|')[0].strip() == signal]
        assert len(found) == 1, (signal, found)
        actual = found[0][2].strip().split('/')[0]
        assert actual == location.strip(), (signal, actual, location)
        pins.append({'signal': signal, 'pin': actual})
    resources = {row[1]: [float(row[2]), int(row[3])] for row in re.finditer(
        r'^\s*(Logic|Register|BSRAM|DSP)\s*\|\s*([\d.]+)/([\d]+)', report, re.M)}
    assert resources and resources['BSRAM'][0] <= resources['BSRAM'][1] == 118, resources
    assert not re.search(r'ERROR\s+\(', (build/'build.log').read_text(errors='replace'))
    result = dict(validated=True, firmware=30, resources=resources, frequency=frequency,
                  slack=slack, pins=pins, source_sha256=built,
                  sha256=hashlib.sha256(bitstream.read_bytes()).hexdigest(),
                  user_code=re.search(r'//UserCode:\s*(\S+)', bitstream.read_text()[:2000])[1],
                  note='Static timing and pin checks. PR1014 clock-routing warning retained; hardware results are recorded separately.')
    (build/'build_validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('pins','source_sha256')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    validate(parser.parse_args().build.resolve())
