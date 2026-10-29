"""Configure this source checkout for a local upstream MCP. Does not modify Mastercam startup or its plugin files."""
import argparse,json,os,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser()
p.add_argument('--mastercam-root',required=True)
p.add_argument('--workspace',required=True,help='Must be inside the upstream Mastercam MCP allowed script directory')
p.add_argument('--codex-config',default=str(Path.home()/'.codex/config.toml'))
p.add_argument('--upstream-name',default='mastercam')
p.add_argument('--register',action='store_true')
a=p.parse_args();cfg=Path(a.codex_config);text=cfg.read_text('utf-8');parsed=tomllib.loads(text)
workspace=Path(a.workspace).resolve()
if workspace.is_relative_to(ROOT):raise SystemExit('Private runtime configuration and backups must be outside the distributable checkout. Choose an external workspace.')
upstream=parsed['mcp_servers'][a.upstream_name]
runtime={'mastercam_root':str(Path(a.mastercam_root).resolve()),'workspace':str(Path(a.workspace).resolve()),'execution_policy':'preview_first','upstream':{k:v for k,v in upstream.items() if k in ('command','args','cwd','env')}}
out=workspace/'plugin-ai-config.json';out.parent.mkdir(parents=True,exist_ok=True)
if out.exists() and json.loads(out.read_text('utf-8'))!=runtime:raise SystemExit('Existing runtime configuration differs; review it before replacement.')
out.write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if a.register:
    existing=parsed.get('mcp_servers',{}).get('mastercam-plugins')
    desired={'command':sys.executable,'args':[str(ROOT/'ai/mcp/server.py')],'env':{'PYTHONUTF8':'1','MC_PLUGIN_AI_CONFIG':str(out)}}
    if existing and any(existing.get(k)!=v for k,v in desired.items()):raise SystemExit('Existing mastercam-plugins registration differs; not replaced.')
    if not existing:
        backup=out.parent/'codex-before-plugin-ai.toml'
        if not backup.exists():backup.write_bytes(cfg.read_bytes())
        q=lambda s:json.dumps(s,ensure_ascii=False)
        block='\n[mcp_servers.mastercam-plugins]\ncommand = '+q(sys.executable)+'\nargs = ['+q(str(ROOT/'ai/mcp/server.py'))+']\n\n[mcp_servers.mastercam-plugins.env]\nPYTHONUTF8 = "1"\nMC_PLUGIN_AI_CONFIG = '+q(str(out))+'\n'
        updated=text+block;tomllib.loads(updated)
        if cfg.read_text('utf-8')!=text:raise SystemExit('Codex configuration changed concurrently; retry after reviewing it.')
        cfg.write_text(updated,encoding='utf-8')
    print('Registered mastercam-plugins without changing existing MCP servers or approval settings.')
print(out)
