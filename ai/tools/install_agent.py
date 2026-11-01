"""Install the six portable agent components without changing unrelated client settings."""
from __future__ import annotations
import argparse, json, os, shutil, sys, tomllib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT, VERSION, load, write_new

def install(mastercam_root, workspace, codex_home, python=None, enable_startup=True):
    mc=Path(mastercam_root).resolve(); work=Path(workspace).resolve(); home=Path(codex_home).resolve()
    python=str(Path(python or sys.executable).resolve())
    if not (mc/'Mastercam.exe').is_file() or not (mc/'chooks/MCNetScripting/IPCServer.dll').is_file():
        raise ValueError('Mastercam.exe and installed chooks/MCNetScripting/IPCServer.dll are required')
    if work.is_relative_to(ROOT) or home.is_relative_to(ROOT):
        raise ValueError('Runtime workspace and Codex home must stay outside the distributable repository')
    cfg=home/'config.toml'; before=cfg.read_bytes() if cfg.exists() else b''
    parsed=tomllib.loads(before.decode('utf-8-sig'))
    runtime_path=work/'plugin-ai-config.json'
    upstream={'command':python,'args':[str(ROOT/'ai/upstream/server.py')],
              'env':{'PYTHONUTF8':'1','MC_BRIDGE_CONFIG':str(runtime_path)}}
    plugin={'command':python,'args':[str(ROOT/'ai/mcp/server.py')],
            'env':{'PYTHONUTF8':'1','MC_PLUGIN_AI_CONFIG':str(runtime_path)}}
    desired={'mastercam':upstream,'mastercam-plugins':plugin}
    runtime={'mastercam_root':str(mc),'workspace':str(work),'execution_policy':'preview_first',
             'upstream':upstream,'package_version':VERSION}
    for name,value in desired.items():
        existing=parsed.get('mcp_servers',{}).get(name)
        if existing and any(existing.get(k)!=v for k,v in value.items()):
            raise ValueError('Existing '+name+' registration differs; preserve it and review migration before replacement')
    if runtime_path.exists() and load(runtime_path)!=runtime:
        raise ValueError('Existing runtime configuration differs; choose a new workspace or review it')
    skills=[]
    connection={'repository':str(ROOT),'runtime_config':str(runtime_path),'workspace':str(work),
                'mcp_server':'mastercam-plugins','execution_policy':'preview_first'}
    for name in ('mastercam-plugin-suite','mastercam-project'):
        source=ROOT/'ai/skills'/name; dest=home/'skills'/name
        for f in source.rglob('*'):
            if f.is_file() and dest.exists():
                target=dest/f.relative_to(source)
                if not target.is_file() or target.read_bytes()!=f.read_bytes():
                    raise ValueError('Existing skill differs: '+str(target))
        old_connection=dest/'references/connection.json'
        if old_connection.exists() and load(old_connection)!=connection:
            raise ValueError('Existing skill connection differs: '+str(old_connection))
        skills.append((source,dest))
    marker=Path(os.environ.get('LOCALAPPDATA',str(home)))/'MC2027PluginSuite/agent-enabled.json'
    marker_value={'schema_version':1,'mastercam_root':str(mc),'enabled':True}
    if enable_startup and marker.exists() and load(marker)!=marker_value:
        raise ValueError('An IPC startup marker already belongs to a different installation')
    text=before.decode('utf-8-sig'); q=lambda s:json.dumps(s,ensure_ascii=False)
    for name,value in desired.items():
        if name in parsed.get('mcp_servers',{}):continue
        text+='\n[mcp_servers.'+name+']\ncommand = '+q(value['command'])+'\nargs = '+json.dumps(value['args'],ensure_ascii=False)+'\n'
        text+='\n[mcp_servers.'+name+'.env]\n'
        for k,v in value['env'].items():text+=k+' = '+q(v)+'\n'
    tomllib.loads(text)
    home.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    if (cfg.read_bytes() if cfg.exists() else b'')!=before:
        raise RuntimeError('Client configuration changed during installation; retry after inspection')
    if before and not (work/'codex-before-agent.toml').exists():
        with (work/'codex-before-agent.toml').open('xb') as f:f.write(before)
    if not runtime_path.exists():write_new(runtime_path,runtime)
    for source,dest in skills:
        if not dest.exists():shutil.copytree(source,dest)
        if not (dest/'references/connection.json').exists():write_new(dest/'references/connection.json',connection)
    if text!=before.decode('utf-8-sig'):
        tmp=cfg.with_name('config.mastercam-agent.tmp')
        with tmp.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
        if (cfg.read_bytes() if cfg.exists() else b'')!=before:
            raise RuntimeError('Client configuration changed; temporary file retained, original untouched')
        os.replace(tmp,cfg)
    if enable_startup and not marker.exists():write_new(marker,marker_value)
    receipt={'package_version':VERSION,'runtime_config':str(runtime_path),'codex_config':str(cfg),
             'skills':[p.name for _,p in skills],'servers':list(desired),
             'startup_marker':str(marker) if enable_startup else None,'native_tested':False,
             'next':'Restart Mastercam with the updated suite, reload Codex MCP, then run doctor --native.'}
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mastercam-root',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    p.add_argument('--python');p.add_argument('--no-startup',action='store_true');a=p.parse_args()
    print(json.dumps(install(a.mastercam_root,a.workspace,a.codex_home,a.python,not a.no_startup),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
