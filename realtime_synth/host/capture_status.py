"""Save a read-only status snapshot from the running local control panel."""
import json
from pathlib import Path
import re
import urllib.request

base='http://127.0.0.1:8765'
page=urllib.request.urlopen(base,timeout=2).read().decode('utf-8')
token=re.search(r"TOKEN='([a-f0-9]+)'",page).group(1)
request=urllib.request.Request(base+'/api/state',headers={'X-Synth-Token':token})
state=json.load(urllib.request.urlopen(request,timeout=2))
path=Path(__file__).resolve().parents[1]/'sim/host_hardware_validation.json'
path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(state,ensure_ascii=False))
