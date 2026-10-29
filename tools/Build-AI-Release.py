"""Build a complete plugin + AI package without modifying previous release assets."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
NAME='Mastercam2027-PluginSuite-AI-2027.10.29.3'
TOP={'README.md','CHANGELOG.md','Manage.ps1','Install.cmd','Uninstall.cmd','Verify.cmd'}
DIRS={'payload','catalog','docs','scripts','src','tools','tests','validation','ai'}
identity=json.loads((ROOT/'ai/bridge/identity.json').read_text('utf-8-sig'))
files=[]
for p in ROOT.rglob('*'):
 if not p.is_file():continue
 r=p.relative_to(ROOT)
 if not ((len(r.parts)==1 and p.name in TOP) or (len(r.parts)>1 and r.parts[0] in DIRS)):continue
 if any(x in r.parts for x in ('__pycache__','.git','.test-work')):continue
 if p.name in ('plugin-ai-config.json','codex-before-plugin-ai.toml','connection.json') or 'plugin-ai' in r.parts:continue
 if r.parts[:3]==('ai','bridge','bin') and p.name!=identity['file']:continue
 if p.suffix in ('.log','.pyc'):continue
 files.append(p)
files.sort(key=lambda p:p.relative_to(ROOT).as_posix())
out=ROOT/'artifacts';out.mkdir(exist_ok=True);archive=out/(NAME+'.zip')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in files:
  info=zipfile.ZipInfo(NAME+'/'+p.relative_to(ROOT).as_posix(),(2026,10,29,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes())
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for p in files:assert z.read(NAME+'/'+p.relative_to(ROOT).as_posix())==p.read_bytes()
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(out/'AI-SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({'archive':str(archive),'files':len(files),'bytes':archive.stat().st_size,'sha256':digest}))
