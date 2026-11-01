"""Check portable files/dependencies, optionally probe the actual stdio/native bridge."""
import argparse, asyncio, importlib.metadata, json, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT, config, load, sha, VERSION

def inspect(c):
    checks=[]
    def check(name,ok,detail=''):checks.append({'name':name,'passed':bool(ok),'detail':detail})
    check('python_311_or_newer',sys.version_info >= (3,11),sys.version.split()[0])
    for name in ('mcp','pydantic','jsonschema'):
        try:check('dependency_'+name,True,importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:check('dependency_'+name,False,'not installed')
    mc=Path(c['mastercam_root'])
    try:
        sys.path.insert(0,str(ROOT/'ai/upstream'))
        from ipc_client import transport_path,_kernel32
        transport_path(_kernel32(),Path(c['workspace']))
        check('ipc_transport_path',True)
    except Exception as e:check('ipc_transport_path',False,str(e))
    for rel in ('Mastercam.exe','NETHook3_0.dll','chooks/MCNetScripting/IPCServer.dll'):
        check(rel,(mc/rel).is_file())
    manifest=load(ROOT/'catalog/package.json')
    for item in manifest['nativeBuild']:
        p=mc/item['path'];check('native_build:'+item['path'],p.is_file() and sha(p).upper()==item['sha256'].upper())
    for item in manifest['files']:
        p=mc/item['path'];check('installed:'+item['path'],p.is_file() and sha(p).upper()==item['sha256'].upper())
    identity=load(ROOT/'ai/bridge/identity.json');bridge=ROOT/'ai/bridge/bin'/identity['file']
    check('typed_bridge',bridge.is_file() and sha(bridge).upper()==identity['sha256'].upper())
    source_manifest=ROOT/'ai/aicnc/source-manifest.json'
    if source_manifest.exists():
        for item in load(source_manifest)['files']:
            p=ROOT/'ai/aicnc'/item['path']
            check('source:'+item['path'],p.is_file() and sha(p)==item['distributed_sha256'])
    check('unresolved_native_request',not (Path(c['workspace'])/'mastercam/active.json').exists(),
          'An active record requires reconciliation before a new write')
    return {'package_version':VERSION,'passed':all(x['passed'] for x in checks),'checks':checks,
            'native_tested':False,'other_computer_tested':False,'production_released':False}

async def native_probe(c):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    u=c['upstream']
    async with stdio_client(StdioServerParameters(command=u['command'],args=u['args'],env={**os.environ,**u.get('env',{})})) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize();result=(await s.call_tool('mastercam_inspect',{})).model_dump(mode='json')
            return {'passed':not result.get('isError',False),'result':result}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--native',action='store_true');p.add_argument('--output');a=p.parse_args()
    c=config(a.config);result=inspect(c)
    if a.native:
        try:result['native_probe']=asyncio.run(native_probe(c));result['native_tested']=True;result['passed'] &= result['native_probe']['passed']
        except Exception as e:result['native_probe']={'passed':False,'error':str(e)};result['passed']=False
    if a.output:Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'checks':len(result['checks']),'failures':[x for x in result['checks'] if not x['passed']],'native_probe':result.get('native_probe'),'report':a.output},ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
