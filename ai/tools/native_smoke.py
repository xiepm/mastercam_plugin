"""Replay the existing P08 synthetic contour in an owned Mastercam 2027 process.

Checks native creation, toolpath and cold reopen. Not material/collision/NC acceptance.
"""
import argparse,asyncio,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from portable.common import ROOT,config,scoped,load,write_new,sha
from portable.native_host import launch as launch_desktop
from mcp_call import call
from compile_script import compile_script
sys.path.insert(0,str(ROOT/'ai/aicnc/projects/08_mastercam_bridge/src'))
from mastercam_bridge import contour_smoke
from mastercam_bridge.plan_simulation import McpConnection
CLIENT=None

def invoke(tool,args,c):
    raw=CLIENT.call(tool,args) if CLIENT is not None else asyncio.run(call(tool,args,c))
    if raw.get('isError'):raise RuntimeError(json.dumps(raw,ensure_ascii=False))
    value=raw.get('structuredContent')
    if value is None:value=json.loads(raw['content'][0]['text'])
    return value

def ready(c):
    last=None
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        try:return invoke('mastercam_inspect',{},c)
        except Exception as e:
            last=e
            if 'unknown' in str(e).lower() or 'Unresolved native request' in str(e):raise
            time.sleep(1)
    raise RuntimeError('Native startup was not ready: '+str(last))

def phase(d,mode,c):
    if (d/(mode+'.json')).exists():raise ValueError('Receipt already exists; do not replay this phase')
    script=d/(mode+'.csx')
    if compile_script(script,c):raise RuntimeError('Static compile failed')
    invoke('mastercam_run_script',{'script_path':str(script)},c)
    result=load(d/(mode+'.json'))
    if not result.get('ok'):raise RuntimeError(json.dumps(result,ensure_ascii=False))
    return result

def close_owned(pid,model,c):
    current=invoke('mastercam_inspect',{},c)['native_readback']
    fields=dict(line.split('=',1) for line in current.splitlines() if '=' in line)
    if Path(fields.get('file','')).resolve()!=model.resolve():raise ValueError('Owned host now has a different document; leave it open')
    code='$p=Get-Process -Id '+str(int(pid))+' -ErrorAction Stop; if($p.ProcessName -ne "Mastercam"){throw "Wrong process"}; $sent=$false; $deadline=[DateTime]::UtcNow.AddSeconds(20); while(!$sent -and [DateTime]::UtcNow -lt $deadline){$p.Refresh(); if($p.HasExited){exit 0}; if($p.MainWindowHandle -ne 0){$sent=$p.CloseMainWindow()}; if(!$sent){Start-Sleep -Milliseconds 250}}; if(!$sent){throw "Cannot close owned window"}; if(!$p.WaitForExit(30000)){throw "Close requires attention; host left intact"}'
    env={**os.environ,'PSModulePath':str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/Modules')}
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',code],timeout=55,env=env,capture_output=True,text=True)
    write_new(model.parent/('close-'+str(pid)+'-'+str(time.time_ns())+'.json'),{'pid':pid,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('Owned host close requires attention: '+result.stderr)

def execute(a,c,d):
    if a.action in ('prepare','cycle'):
        request=contour_smoke.prepare(d)
        print(json.dumps({'prepared':str(d),'run_id':request['run_id']}),flush=True)
    if a.action=='cycle':
        started=launch_desktop(c);write_new(d/'launch-create.json',started);ready(c)
        created=phase(d,'create',c)
        if created['pid']!=started['pid']:raise ValueError('Host ownership changed')
        close_owned(created['pid'],d/'contour.mcam',c)
        reopened=launch_desktop(c,str(d/'contour.mcam'))
        write_new(d/'launch-reopen.json',reopened);ready(c);phase(d,'reopen',c)
    elif a.action in ('create','reopen'):print(json.dumps(phase(d,a.action,c),ensure_ascii=False))
    if a.action in ('verify','cycle'):
        result=contour_smoke.verify(d);write_new(d/'verification.json',result)
        print(json.dumps(result,ensure_ascii=False))
        if a.action=='cycle':
            if result['passed']:
                probe=subprocess.run([sys.executable,str(ROOT/'ai/tools/call.py'),'mc_inspect','--config',c['config_path'],
                    '--output',str(d/'plugin-inspect.json')],capture_output=True,text=True,timeout=90)
                (d/'plugin-inspect.log').write_text(probe.stdout+probe.stderr,encoding='utf-8')
                if probe.returncode:raise RuntimeError('Plugin native readback failed; inspect plugin-inspect.json/log')
            # Native inspection can mark the in-memory document modified.
            # Preserve that session in a NEW copy; never resave the verified MCAM.
            copy=d/'inspection-session.mcam'
            saved=invoke('mastercam_save_as',{'output_path':str(copy)},c)
            write_new(d/'inspection-save.json',saved)
            if sha(d/'contour.mcam')!=result['model_sha256']:raise RuntimeError('Verified source changed during cleanup')
            close_owned(reopened['pid'],copy,c)
        return 0 if result['passed'] else 1
    return 0

def main():
    global CLIENT
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','create','reopen','verify','cycle'])
    p.add_argument('--directory',required=True);p.add_argument('--config',required=True);a=p.parse_args()
    c=config(a.config);os.environ['MC_PLUGIN_AI_CONFIG']=a.config;d=scoped(a.directory,c)
    if a.action in ('prepare','verify'):return execute(a,c,d)
    # Reuse P08's persistent stdio connection. The standalone test runner owns
    # the desktop process outside the MCP child job, preserving it on failure.
    with McpConnection() as client:
        CLIENT=client
        try:return execute(a,c,d)
        finally:CLIENT=None
if __name__=='__main__':raise SystemExit(main())
