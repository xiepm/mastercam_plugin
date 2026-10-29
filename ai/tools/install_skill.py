import argparse,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--skills-root',default=str(Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'skills'));a=p.parse_args()
source=ROOT/'ai/skills/mastercam-plugin-suite';dest=Path(a.skills_root)/source.name
if dest.exists():
    differences=[f.relative_to(source).as_posix() for f in source.rglob('*') if f.is_file() and (not (dest/f.relative_to(source)).exists() or (dest/f.relative_to(source)).read_bytes()!=f.read_bytes())]
    if differences:raise SystemExit('Existing skill differs; preserve/review it before updating: '+', '.join(differences))
else:shutil.copytree(source,dest)
connection={'repository':str(ROOT),'runtime_config':str(Path(a.config).resolve()),'mcp_server':'mastercam-plugins','execution_policy':'preview_first'}
(dest/'references/connection.json').write_text(json.dumps(connection,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(dest)
