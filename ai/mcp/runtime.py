"""Broker to an existing Mastercam MCP bridge; no arbitrary-code tool exposed."""
import asyncio, hashlib, json, os, re, uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[2]
DEPS=['AdvancedDrill2027/AdvancedDrill2027.dll','OperationTools2027/OperationTools2027.dll','PorscheAdvanced2027/PorscheAdvanced2027.dll','HSMRebuild2027/HSMRebuild2027.dll','MPRebuild2027/MPRebuild2027.Core.dll','MPRebuild2027/MPRebuild2027.dll']
DEPS += ['MPEdgeTools2027/MPEdgeTools2027.dll', 'MPDesignTools2027/MPDesignTools2027.Core.dll', 'MPDesignTools2027/MPDesignTools2027.dll', 'MPDesignSurfaceSelect2027/MPDesignSurfaceSelect2027.Core.dll', 'MPDesignSurfaceSelect2027/MPDesignSurfaceSelect2027.dll', 'MPDesignRadiusSelect2027/MPDesignRadiusSelect2027.Core.dll', 'MPDesignRadiusSelect2027/MPDesignRadiusSelect2027.dll', 'GeometryTools2027/GeometryTools2027.dll', 'SVGGeometry2027/SVGGeometry2027.dll', 'TpSketcher2027/TpSketcher2027.Core.dll', 'TpSketcher2027/TpSketcher2027.dll', 'FixtureTools2027/FixtureTools2027.Core.dll', 'FixtureTools2027/FixtureTools2027.dll', 'HirthTools2027/HirthTools2027.Core.dll', 'HirthTools2027/HirthTools2027.dll', 'SetupSheets2027/SetupSheets2027.dll', 'LevelExport2027/LevelExport2027.Core.dll', 'LevelExport2027/LevelExport2027.dll', 'ScreenTools2027/ScreenTools2027.dll', 'ElectrodeReport2027/ElectrodeReport2027.Core.dll', 'ElectrodeReport2027/ElectrodeReport2027.dll']

DEPS += ['HolderTools2027/HolderTools2027.dll']
DEPS += ['AdvancedDrillTap2027/AdvancedDrillTap2027.dll','SolidBoundary2027/SolidBoundary2027.dll','MiddleConfirm2027/MiddleConfirm2027.dll','Workshop2027/Workshop2027.dll','LittleBee2027/LittleBee2027.dll']

def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def load(path):return json.loads(Path(path).read_text('utf-8-sig'))
def token(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',value):raise ValueError('ID must be 8-80 letters, digits, _ or -')
    return value

@contextmanager
def process_guard(path):
    with path.open('a+b') as f:
        if f.seek(0,2)==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another native caller holds the workspace lock')
            try:yield
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield
            finally:fcntl.flock(f,fcntl.LOCK_UN)

class Runtime:
    def __init__(self,config_path=None,backend=None):
        self.config_path=config_path or os.environ.get('MC_PLUGIN_AI_CONFIG')
        self.backend=backend
    def config(self):
        if not self.config_path:raise RuntimeError('No MC_PLUGIN_AI_CONFIG configured. Catalog tools remain usable; see ai/README.md.')
        c=load(self.config_path)
        for key in ('mastercam_root','workspace','upstream'):
            if key not in c:raise ValueError('Missing configuration: '+key)
        workspace=Path(c['workspace']).resolve()
        if not workspace.is_absolute():raise ValueError('Workspace must be absolute')
        workspace.mkdir(parents=True,exist_ok=True)
        c['workspace']=str(workspace)
        return c
    def directory(self,c):
        p=Path(c['workspace'])/'plugin-ai';p.mkdir(exist_ok=True);return p
    def check_dependencies(self,c):
        manifest=load(ROOT/'catalog/package.json')
        pinned={f['path']:f['sha256'] for f in manifest['files']}
        actual=[]
        for rel in DEPS:
            path=Path(c['mastercam_root'])/'chooks'/rel
            if not path.is_file() or sha(path)!=pinned['chooks/'+rel]:raise RuntimeError('Installed dependency mismatch: '+rel)
            actual.append((path,pinned['chooks/'+rel]))
        identity=load(ROOT/'ai/bridge/identity.json')
        bridge=ROOT/'ai/bridge/bin'/identity['file']
        pinned_bridge=identity['sha256']
        if sha(bridge)!=pinned_bridge:raise RuntimeError('AI bridge hash mismatch')
        return actual+[(bridge,pinned_bridge)]
    async def invoke_upstream(self,c,script):
        if self.backend:return await self.backend(script)
        u=c['upstream'];env={**os.environ,**u.get('env',{})}
        params=StdioServerParameters(command=u['command'],args=u.get('args',[]),cwd=u.get('cwd'),env=env)
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                return await session.call_tool('mastercam_run_script',{'script_path':str(script)},read_timeout_seconds=timedelta(seconds=150))
    def status(self,request_id):
        c=self.config();d=self.directory(c)/token(request_id)
        if (d/'result.json').exists():return {'request_id':request_id,**load(d/'result.json')}
        if (d/'request.json').exists():return {'request_id':request_id,'ok':False,'state':'unknown_or_running','instruction':'Do not repeat the mutation. Query this request again; inspect the host before recovery.'}
        return {'request_id':request_id,'ok':False,'state':'not_found'}
    async def call(self,command,values=None,request_id=None):
        c=self.config();root=self.directory(c)
        with process_guard(root/'broker.lock'):
            return await self._call_locked(command,values,request_id)
    async def _call_locked(self,command,values=None,request_id=None):
        c=self.config();root=self.directory(c);rid=token(request_id or uuid.uuid4().hex);d=root/rid
        values=values or {};semantic={'command':command,**values}
        signature=hashlib.sha256(dump(semantic).encode()).hexdigest()
        lock=root/'active.json'
        # An existing request is never resubmitted, even across MCP restarts.
        if d.exists():
            previous=load(d/'meta.json')
            if previous['signature']!=signature:raise ValueError('Request ID already used for different arguments')
            return self.status(rid)
        if lock.exists():
            active=load(lock);active_result=root/active['request_id']/'result.json'
            if not active_result.exists():raise RuntimeError('Unresolved native request '+active['request_id']+'; use mc_request_status before any other native call.')
            lock.unlink()
        dependencies=self.check_dependencies(c)
        try:
            with lock.open('x',encoding='utf-8') as f:json.dump({'request_id':rid},f)
        except FileExistsError:raise RuntimeError('Another native request is active')
        may_have_submitted=False
        try:
            d.mkdir();(d/'meta.json').write_text(dump({'signature':signature}),encoding='utf-8')
            request={**semantic,'artifact_directory':str(d/'artifacts')}
            (d/'request.json').write_text(dump(request),encoding='utf-8')
            # JSON escaping is used for C# string literals only, never shell commands.
            lit=lambda p:json.dumps(str(p),ensure_ascii=True)
            lines=['try {']
            lines += ['var bridge = System.Reflection.Assembly.LoadFrom('+lit(dependencies[-1][0])+');']
            # Business assemblies are hashed inside CheckAssembly before being loaded.
            for path,digest in [dependencies[-1],*dependencies[:-1]]:
                lines+=['bridge.GetType("MastercamPluginAI.Bridge").GetMethod("CheckAssembly").Invoke(null,new object[]{'+lit(path)+','+lit(digest)+'});']
            lines += [
                'bridge.GetType("MastercamPluginAI.Bridge").GetMethod("RunFile").Invoke(null,new object[]{'+lit(d/'request.json')+','+lit(d/'result.json')+'});',
                '} catch(System.Exception ex) { System.IO.File.WriteAllText('+lit(d/'result.json')+',System.Text.Json.JsonSerializer.Serialize(new {ok=false,error=ex.ToString()})); }']
            script=d/'run.csx';script.write_text('\n'.join(lines),encoding='utf-8')
            try:
                may_have_submitted=True
                await self.invoke_upstream(c,script)
            except Exception as e:
                (d/'transport-error.txt').write_text(str(e),encoding='utf-8')
            result=self.status(rid)
            if (d/'result.json').exists():lock.unlink(missing_ok=True)
            return result
        except Exception as e:
            # Fail before submission can be retried with a new ID; after submission retain unknown state.
            if not may_have_submitted:
                try:
                    if (d/'meta.json').exists():
                        (d/'result.json').write_text(dump({'ok':False,'state':'not_submitted','error':str(e)}),encoding='utf-8')
                finally:lock.unlink(missing_ok=True)
                if (d/'result.json').exists():return self.status(rid)
            raise
