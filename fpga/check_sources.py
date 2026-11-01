"""Fail before Gowin if a declared input or literal ROM initializer is missing."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parent
def inspect():
 files={(R/x.get('path')).resolve() for x in ET.parse(R/'synth_display.gprj').findall('.//File')}
 for p in list(files):
  if not p.is_file():raise FileNotFoundError(p)
  if p.suffix=='.v':
   for name in re.findall(r'\$readmem[hb]\s*\(\s*"([^"]+)"',p.read_text(encoding='utf8')):
    rom=R/name
    if not rom.is_file():raise FileNotFoundError(f'{p.name} needs ROM {rom}')
    files.add(rom.resolve())
 return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
if __name__=='__main__':
 out=inspect();(R/'source_manifest.json').write_text(json.dumps(out,indent=2)+'\n');print('PASS declared sources and literal ROMs:',len(out))
