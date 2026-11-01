"""Bounded cam_plan 1.1 -> existing Mastercam MCP -> native Verify + reopen.

Explicit single-contour and bounded multi-operation profiles are supported. Simulation-only
requests do not approve the source plan, a machine or production NC.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, math, os, struct, subprocess, sys, threading, time, tomllib, uuid
from collections import Counter
from pathlib import Path
from jsonschema import Draft202012Validator
from .contour_smoke import digest, load, write_new

ROOT = Path(__file__).resolve().parents[4]
NATIVE = Path(__file__).resolve().parents[1] / "mastercam"
SCHEMA = ROOT / "schemas/mastercam_plan_simulation.schema.json"
PYTHON = Path(sys.executable)
MCP_CALL = ROOT.parent / "tools/mcp_call.py"

def runtime_config():
    path=os.environ.get("MC_PLUGIN_AI_CONFIG") or os.environ.get("MC_BRIDGE_CONFIG")
    if not path:raise ValueError("Portable runtime configuration is required")
    return load(Path(path))

def json_assembly():
    return command([sys.executable,ROOT.parent/"tools/compile_script.py","--json-assembly"]).strip()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schema(value, definition):
    doc = load(SCHEMA)
    Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": doc["$defs"]}).validate(value)


def resolve_asset(base, ref):
    path = Path(ref["path"])
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    require(digest(path) == ref["sha256"], f"Asset changed: {path.name}")
    return path


def compile_plan(plan_path, binding_path):
    plan_path, binding_path = Path(plan_path).resolve(), Path(binding_path).resolve()
    plan, binding = load(plan_path), load(binding_path)
    if binding.get('schema_version') == 'aicnc.mastercam-plan-simulation-binding/0.2':
        from .plan_multi import compile_multi
        return compile_multi(plan_path, binding_path)
    Draft202012Validator(load(ROOT / "schemas/cam_plan.schema.json")).validate(plan)
    schema(binding, "binding")
    require(resolve_asset(binding_path.parent, binding["plan"]) == plan_path, "Wrong plan binding")
    require(plan["status"] not in {"draft", "rejected"}, "Plan is draft/rejected")
    require(plan["units"] == {"length": "mm", "angle": "deg", "feed_rate": "mm/min"}, "Only metric plans")
    require(not plan["unplanned_features"] and len(plan["setups"]) == 1, "Only complete single setup")
    # Keep original provenance; no silent reinterpretation of an IR as cam_plan.
    features_path = resolve_asset(plan_path.parent, plan["source_features"])
    context_path = resolve_asset(plan_path.parent, plan["manufacturing_context"])
    features, context = load(features_path), load(context_path)
    step=resolve_asset(features_path.parent, {'path':features['source']['step_file'],'sha256':features['source']['step_sha256'].lower()})
    require(features["face_id_namespace"] == plan["source_features"]["face_id_namespace"], "Face namespace")
    require(features["part_id"] == plan["part_id"] and context["context_id"] == plan["manufacturing_context"]["context_id"], "Source identity")
    setup = plan["setups"][0]
    require(setup["setup_id"] == binding["setup_id"] and len(setup["operations"]) == 1, "Setup/operation cardinality")
    frame = setup["work_coordinate_system"]
    require([frame[k] for k in ("origin", "x_axis", "y_axis", "z_axis")] == [[0,0,0],[1,0,0],[0,1,0],[0,0,1]], "Only identity WCS")
    require(setup["machining_direction"] == [0,0,-1], "Only top machining")
    op = setup["operations"][0]
    require(op["operation_id"] == binding["operation_id"] and op["sequence"] == 1, "Operation identity")
    require(op["operation_type"] == "contouring" and op["strategy"] == "rectangular_external_contour", "Unsupported strategy")
    require(op["status"] in {"planned", "needs_review", "approved"}, "Operation blocked")
    require(op["feature_instance_ids"] == binding["feature_instance_ids"] and op["face_ids"] == binding["face_ids"], "Face/feature binding")
    source_ids = {f["instance_id"] for f in features["features"]}
    require(len(op['feature_instance_ids'])==1,'Single feature binding required')
    matched=[f for f in features['features'] if f['instance_id']==op['feature_instance_ids'][0]]
    require(len(matched)==1 and set(matched[0]['topology']['face_ids'])==set(op['face_ids']),'Feature face membership')
    require(set(op["feature_instance_ids"]) <= source_ids, "Unknown source feature")
    source_faces = {f["face_id"] for f in features["faces"]}
    require(set(op["face_ids"]) <= source_faces, "Unknown source face")
    g, t = binding["geometry"], binding["tool_assembly"]
    require('fixture_id' not in setup or setup['fixture_id']==context['fixture']['fixture_id'],'Fixture identity')
    tools=[x for x in context['tools'] if x['tool_id']==op['tool']['tool_id']]
    require(len(tools)==1 and all(tools[0].get(k)==v for k,v in op['tool'].items()),'Tool differs from context')
    w,h,z,m,sh = (g[k] for k in ("width_mm", "height_mm", "depth_mm", "margin_mm", "stock_height_mm"))
    require(z < 0 and sh > -z and m > 0, "Stock/depth geometry")
    require(setup["stock"]["type"] == "box" and setup["stock"]["dimensions"] == [w+2*m,h+2*m,sh], "Stock dimensions")
    require(op["tool"]["tool_type"] == "flat_end_mill" and op["tool"]["diameter"] == m*2, "Profile requires margin = cutter radius")
    require(op["tool"].get("corner_radius",0) == 0 and op["tool"].get("stickout") == t["length_mm"], "Tool geometry mismatch")
    require(t["flute_length_mm"] <= t["shoulder_length_mm"] <= t["length_mm"], "Tool assembly lengths")
    require(t["holder_diameter_mm"] > op["tool"]["diameter"], "Holder diameter")
    cut=op["cutting_parameters"]
    require(set(cut) <= {"spindle_speed_rpm","feed_rate","plunge_rate","coolant","stepdown"}, "Unsupported cutting parameter")
    require(cut["coolant"] == "off" and cut.get("plunge_rate") == 100 and cut.get("stepdown",-z) == -z, "Only one axial pass, explicit test plunge/coolant")
    require(cut["spindle_speed_rpm"] == int(cut["spindle_speed_rpm"]), "Integral RPM required")
    require(op["safety"] == {"clearance":10,"retract":5,"stock_to_leave_radial":0,"stock_to_leave_axial":0}, "Unsupported linking/allowance")
    target = resolve_asset(binding_path.parent,binding["target"])
    require(target.read_bytes() == stepped_target(w,h,z,m,sh), "Target is not the independently specified stepped prism")
    return dict(width_mm=w,height_mm=h,depth_mm=z,margin_mm=m,stock_height_mm=sh,
                tool_diameter_mm=op["tool"]["diameter"],feed_mm_min=cut["feed_rate"],spindle_rpm=cut["spindle_speed_rpm"],
                tool_length_mm=t["length_mm"],flute_length_mm=t["flute_length_mm"],shoulder_length_mm=t["shoulder_length_mm"],
                holder_diameter_mm=t["holder_diameter_mm"],holder_length_mm=t["holder_length_mm"],
                plan_path=str(plan_path),plan_sha256=digest(plan_path),binding_path=str(binding_path),binding_sha256=digest(binding_path),
                target_path=str(target),target_sha256=digest(target),step_path=str(step),step_sha256=digest(step))


def stepped_target(w,h,z,m,sh):
    """Explicit synthetic fixture construction, never derived from an IPW."""
    outer=[(-m,-m),(w+m,-m),(w+m,h+m),(-m,h+m)]
    inner=[(0,0),(w,0),(w,h),(0,h)]
    vertices=[(x,y,a) for points,a in [(outer,-sh),(outer,z),(inner,z),(inner,0)] for x,y in points]
    quads=[(0,3,2,1),(12,13,14,15)]
    for i in range(4):
        j=(i+1)%4
        quads += [(i,j,4+j,4+i),(4+i,4+j,8+j,8+i),(8+i,8+j,12+j,12+i)]
    triangles=[t for a,b,c,d in quads for t in [(a,b,c),(a,c,d)]]
    raw=bytearray(b'AICNC independent analytical stepped target mm'.ljust(80,b'\0'))+struct.pack('<I',len(triangles))
    for tri in triangles:
        a,b,c=[vertices[k] for k in tri]
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        raw += struct.pack('<12fH',*[x/length for x in n],*a,*b,*c,0)
    return bytes(raw)


def mesh_stats(path):
    raw=Path(path).read_bytes()
    require(len(raw)>=84, "Invalid binary STL")
    count=struct.unpack_from('<I',raw,80)[0]
    require(0<count<=1000000 and len(raw)==84+50*count,"STL size")
    points=[]; edges=Counter(); volume=0.; canonical=[]
    for i in range(count):
        values=struct.unpack_from('<12fH',raw,84+50*i)
        a,b,c=[tuple(values[j:j+3]) for j in (3,6,9)]
        require(all(math.isfinite(v) for p in (a,b,c) for v in p),"Nonfinite mesh")
        points.extend((a,b,c));canonical.append(sorted((a,b,c)))
        for x,y in ((a,b),(b,c),(c,a)): edges[(x,y)]+=1
        volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    require(all(n==1 and edges[(b,a)]==1 for (a,b),n in edges.items()),"Mesh not closed/oriented")
    require(volume>0,"Invalid signed volume")
    return dict(triangles=count,volume_mm3=volume,min=[min(p[i] for p in points) for i in range(3)],max=[max(p[i] for p in points) for i in range(3)],
                geometry_sha256=hashlib.sha256(json.dumps(sorted(canonical),separators=(',',':')).encode()).hexdigest(),sha256=digest(Path(path)))


def render(template, values, output):
    text=template.read_text(encoding='utf-8-sig')
    if '__SYSTEM_TEXT_JSON__' in text:text=text.replace('__SYSTEM_TEXT_JSON__',json_assembly().replace('\\','/'))
    for key,value in values.items(): text=text.replace('__'+key+'__',json.dumps(value))
    require('__DLL_' not in text and '__REQUEST_' not in text,"Unrendered template")
    with output.open('x',encoding='utf-8',newline='\n') as stream: stream.write(text)


def prepare(plan, binding, directory):
    request=compile_plan(plan,binding)
    directory=Path(directory).resolve()
    require(directory.is_relative_to(Path(runtime_config()['workspace']).resolve()),"Native outputs must stay under MCP workspace")
    directory.mkdir(parents=True,exist_ok=False)
    request.update(schema_version='aicnc.mastercam-plan-native-request/0.1',purpose='synthetic_native_validation',
                   run_id='plan-'+uuid.uuid4().hex[:12],model_path=str(directory/'contour.mcam'))
    request['operation_name']='AICNC_'+request['run_id']
    if 'operations' in request:
        request['schema_version']='aicnc.mastercam-plan-native-request/0.2'
        for op in request['operations']:
            op['operation_name']=request['operation_name']+'_'+str(op['sequence']).zfill(3)
        from .plan_multi import validate
        validate(request,'native_request')
    else:
        schema(request,'native_request')
    write_new(directory/'request.json',request)
    sources=[NATIVE/'aicnc_plan_contour.csx',NATIVE/'aicnc_simulation_dispatch.csx',NATIVE/'SimulationDomainBridge.cs',Path(__file__)]
    if 'operations' in request:
        sources += [NATIVE/'aicnc_plan_multi.csx',Path(__file__).with_name('plan_multi.py'),ROOT/'projects/01_cad_core/src/cad_core/faceted_material_difference.py']
    (directory/'source').mkdir()
    for path in sources:(directory/'source'/path.name).write_bytes(path.read_bytes())
    write_new(directory/'source_manifest.json',dict(base_commit=json.loads((ROOT/'source-manifest.json').read_text(encoding='utf-8'))['upstream_base_commit'],
        source_sha256={p.name:digest(p) for p in sources},
        request_sha256=digest(directory/'request.json')))
    return request


def command(args, timeout=60):
    env=dict(os.environ)
    if str(args[0]).lower().endswith('powershell.exe'):
        # PowerShell 7's module search path can hide the Windows PS5 utility
        # module when invoking the .NET Framework Roslyn compiler as a child.
        env['PSModulePath']=str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/Modules')
    proc=subprocess.run([str(x) for x in args],capture_output=True,encoding='utf-8',errors='replace',timeout=timeout,env=env)
    if proc.returncode: raise RuntimeError(f'Command failed ({proc.returncode}): {proc.stdout}\n{proc.stderr}')
    return proc.stdout


_client = None

class McpConnection:
    """Keep the installed stdio server alive for the owned native host lifetime."""
    def __enter__(self):
        self.ready=threading.Event();self.error=None
        self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
        require(self.ready.wait(20),'MCP connection startup timeout')
        if self.error:raise self.error
        return self
    def worker(self):
        try:asyncio.run(self.serve())
        except Exception as error:self.error=error;self.ready.set()
    async def serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        cfg=runtime_config()['upstream']
        params=StdioServerParameters(command=cfg['command'],args=cfg.get('args',[]),env=dict(os.environ,**cfg.get('env',{})),cwd=cfg.get('cwd'))
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                self.session=session;self.loop=asyncio.get_running_loop();self.stop=asyncio.Event()
                await session.initialize();self.ready.set();await self.stop.wait()
    def call(self,tool,args):
        return asyncio.run_coroutine_threadsafe(self.session.call_tool(tool,args),self.loop).result(60).model_dump(mode='json')
    def __exit__(self,*args):
        self.loop.call_soon_threadsafe(self.stop.set);self.thread.join(10)


def mcp(directory,label,tool,args):
    argfile=directory/(label+'.args.json');write_new(argfile,args)
    data=_client.call(tool,args) if _client is not None else json.loads(command([PYTHON,MCP_CALL,'mastercam',tool,argfile],60))
    write_new(directory/(label+'.mcp.json'),data)
    require(not data.get('isError'),'MCP error: '+str(data))
    return data


def compiled_script(directory,label,script,receipt,net10=False):
    if net10:
        raw=command([sys.executable,ROOT.parent/'tools/compile_script.py','--script',script,'--config',runtime_config()['upstream']['env']['MC_BRIDGE_CONFIG']],30)
        compiled=dict(compile_success='ERROR_COUNT=0' in raw,script_sha256=digest(script),runtime='NET10',diagnostics=raw)
    else:
        raw=command(['powershell.exe','-NoProfile','-File',ROOT/'projects/08_mastercam_bridge/tools/compile_netscript.ps1','-ScriptPath',script],30)
        compiled=json.loads(raw)
    write_new(directory/(label+'.compile.json'),compiled)
    require(compiled['compile_success'] and compiled['script_sha256'].lower()==digest(script),'Static compile failed')
    mcp(directory,label,'mastercam_run_script',{'script_path':str(script)})
    until=time.monotonic()+45
    while not receipt.exists() and time.monotonic()<until: time.sleep(.2)
    require(receipt.exists(),'Native outcome unknown; do not replay: '+str(receipt))
    result=load(receipt);require(result.get('ok') is True,'Native action failed: '+str(result))
    return result


def build_helper(directory):
    name='SimulationDomainBridge.'+digest(NATIVE/'SimulationDomainBridge.cs')[:12]+'.dll'
    dll=directory/name
    framework=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319'
    refs=[framework/'WPF'/x for x in ('WindowsBase.dll','PresentationFramework.dll','PresentationCore.dll')]+[framework/'System.Xaml.dll',framework/'System.Web.Extensions.dll']
    command([framework/'csc.exe','/nologo','/target:library','/out:'+str(dll),*['/r:'+str(x) for x in refs],NATIVE/'SimulationDomainBridge.cs'])
    write_new(directory/'helper.json',dict(path=str(dll),sha256=digest(dll),source_sha256=digest(NATIVE/'SimulationDomainBridge.cs')))
    return dll


def native_phase(directory,label,mode):
    request=directory/'request.json';script=directory/(label+'.csx');receipt=directory/(label+'.json')
    template='aicnc_plan_multi.csx' if 'operations' in load(request) else 'aicnc_plan_contour.csx'
    render(NATIVE/template,dict(REQUEST_PATH=str(request),REQUEST_SHA256=digest(request),RECEIPT_PATH=str(receipt),MODE=mode),script)
    return compiled_script(directory,label,script,receipt)


def dispatch(directory,label,action,dll,artifact):
    r=load(directory/'request.json');script=directory/(label+'.csx');receipt=directory/(label+'.json')
    render(NATIVE/'aicnc_simulation_dispatch.csx',dict(DLL_PATH=str(dll),DLL_SHA=digest(dll),ACTION=action,RECEIPT=str(receipt),MODEL=r['model_path'],
        MODEL_SHA=digest(Path(r['model_path'])),OP_NAME=r['operation_name'],REQUEST_PATH=str(directory/'request.json'),REQUEST_SHA=digest(directory/'request.json'),
        ARTIFACT=str(artifact),DISPATCH=str(directory/(label+'.dispatch.json'))),script)
    compiled_script(directory,label,script,directory/(label+'.dispatch.json'))
    until=time.monotonic()+45
    while not receipt.exists() and time.monotonic()<until:time.sleep(.2)
    require(receipt.exists(),'Asynchronous outcome unknown: '+str(receipt))
    result=load(receipt);require(result.get('ok') is True,'Simulator action failed: '+str(result))
    return result


def simulate(directory,label,dll):
    r=load(directory/'request.json');script=directory/(label+'-start.csx');receipt=directory/(label+'-start.json')
    error_log=Path.home()/'Documents/My Mastercam 2026/Mastercam/MastercamSimulatorExceptions.log'
    error_offset=error_log.stat().st_size if error_log.exists() else 0
    body='''#r "System.Web.Extensions"
var r=new System.Collections.Generic.Dictionary<string,object>();r["ok"]=false;
try {var ops=Mastercam.Support.SearchManager.GetOperations();
var names=__NAMES__;if(ops.Length!=names.Length)throw new System.Exception("Wrong operation count");
for(int i=0;i<ops.Length;i++)if(ops[i].Name!=names[i]||ops[i].Dirty)throw new System.Exception("Wrong operation/order");
if(!System.String.Equals(Mastercam.IO.FileManager.CurrentFileName,__MODEL__,System.StringComparison.OrdinalIgnoreCase))throw new System.Exception("Wrong file");
Mastercam.Operations.OperationsManager.SelectOperations(ops);
Mastercam.Support.ExternalAppsManager.RunFTCommand("OMverifySelectedOperations");r["ok"]=true;
}catch(System.Exception e){r["error"]=e.ToString();}
System.IO.File.WriteAllText(__RECEIPT__,new System.Web.Script.Serialization.JavaScriptSerializer().Serialize(r));
'''
    names=[o['operation_name'] for o in r['operations']] if 'operations' in r else [r['operation_name']]
    body=body.replace('__NAMES__','new string[]{'+','.join(json.dumps(n) for n in names)+'}')
    for k,v in dict(MODEL=r['model_path'],RECEIPT=str(receipt)).items():body=body.replace('__'+k+'__',json.dumps(v))
    script.write_text(body,encoding='utf-8')
    compiled_script(directory,label+'-start',script,receipt)
    for i in range(20):
        state=dispatch(directory,label+f'-ready-{i}','ready',dll,r['target_path'])
        if state['ready']:break
        time.sleep(.5)
    else:raise RuntimeError('Simulator initialization did not finish; no motion submitted')
    if 'operations' in r:
        dispatch(directory,label+'-quality','quality',dll,r['target_path'])
        for i in range(20):
            state=dispatch(directory,label+f'-fine-ready-{i}','ready-fine',dll,r['target_path'])
            if state['ready']:break
            time.sleep(.5)
        else:raise RuntimeError('Simulator fine precision reset did not finish')
    dispatch(directory,label+'-configure','configure',dll,r['target_path'])
    dispatch(directory,label+'-run','run',dll,r['target_path'])
    # Observe completion before requesting export. Polling never submits motion twice.
    for i in range(30):
        state=dispatch(directory,label+f'-inspect-{i}','inspect',dll,r['target_path'])
        errors=new_native_errors(error_log,error_offset)
        if errors:
            write_new(directory/(label+'-native-exceptions.json'),dict(passed=False,log_path=str(error_log),baseline_bytes=error_offset,exceptions=errors))
            raise RuntimeError('Native Simulator exception: '+errors)
        if state['motion']['completed']: break
    else: raise RuntimeError('Simulation did not complete')
    result=dispatch(directory,label+'-export','export',dll,directory/(label+'-ipw.stl'))
    errors=new_native_errors(error_log,error_offset)
    write_new(directory/(label+'-native-exceptions.json'),dict(passed=not errors,log_path=str(error_log),baseline_bytes=error_offset,exceptions=errors))
    require(not errors,'Native Simulator export exception: '+errors)
    return result


def new_native_errors(path,offset):
    if not path.exists():return ''
    # Never interpret an old native exception as a failure of this run.
    raw=path.read_bytes()
    if len(raw)<offset:raise RuntimeError('Native exception log truncated during run')
    text=raw[offset:].decode('utf-8',errors='replace')
    return text[:16000] if 'Exception occurred at' in text else ''


def wsl_path(path):
    path=Path(path).resolve().as_posix()
    require(len(path)>2 and path[1]==':','Expected local Windows path')
    return '/mnt/'+path[0].lower()+path[2:]


def material_compare(directory,label):
    r=load(directory/'request.json');stl=directory/(label+'-ipw.stl');raw=stl.read_bytes();mesh_stats(stl)
    polygons=[]
    for i in range(struct.unpack_from('<I',raw,80)[0]):
        v=struct.unpack_from('<12fH',raw,84+50*i);polygons.append([list(v[j:j+3]) for j in (3,6,9)])
    mesh=directory/(label+'-ipw.json')
    write_new(mesh,dict(schema_version='aicnc.native-ipw-polygons/1.0',units='mm',geometry_frame='PCS',approximation='Mastercam_native_faceted_IPW_not_exact_STEP',polygons=polygons,source_stl_sha256=digest(stl)))
    multi='operations' in r
    module='faceted_material_difference' if multi else 'ipw_material_difference'
    boot='import sys;sys.path.insert(0,'+repr(wsl_path(ROOT/'projects/01_cad_core/src'))+');from cad_core.'+module+' import main;main()'
    command(['wsl.exe','-d','Ubuntu-22.04','--','/home/xpm/.local/share/micromamba/envs/aicnc-aagnet-cpu/bin/python','-c',boot,
             '--target',wsl_path(r['step_path']),'--mesh',wsl_path(mesh),'--target-sha256',r['step_sha256'].upper(),
             '--mesh-sha256',digest(mesh).upper(),'--output',wsl_path(directory/(label+'-material.json')),
             *(['--deflection-mm','0.005'] if multi else [])],60)


def close_owned(directory,label,pid):
    r=load(directory/'request.json');model=Path(r['model_path'])
    require(model.is_file() and load(directory/'create.json')['model_sha256']==digest(model),'Saved file changed before host close')
    # PID comes from this package's native receipt, never all Mastercam processes.
    command(['powershell.exe','-NoProfile','-Command',f"$p=Get-Process -Id {int(pid)} -ErrorAction Stop; if($p.ProcessName -ne 'Mastercam'){{throw 'Wrong owner'}}; Stop-Process -Id {int(pid)} -Force; if(-not $p.WaitForExit(15000)){{throw 'Host exit timeout'}}"],30)
    write_new(directory/(label+'.json'),dict(pid=pid,model_sha256=digest(model),owned_host_closed=True))


def execute(directory, attach_empty=False):
    global _client
    with McpConnection() as client:
        _client=client
        try:return execute_connected(directory, attach_empty)
        finally:_client=None


def wait_ready(directory,label):
    for i in range(60):
        try:return mcp(directory,label+str(i),'mastercam_inspect',{})
        except ValueError:time.sleep(1)
    raise RuntimeError('Mastercam startup not ready; inspect before retrying')


def execute_connected(directory, attach_empty=False):
    directory=Path(directory).resolve();r=load(directory/'request.json')
    require(digest(directory/'request.json')==load(directory/'source_manifest.json')['request_sha256'],'Request drift')
    compiled=compile_plan(r['plan_path'],r['binding_path'])
    comparable=json.loads(json.dumps(r))
    for op in comparable.get('operations',[]):op.pop('operation_name',None)
    require(all(comparable.get(k)==v for k,v in compiled.items()),'Request is not the compiled plan')
    dll=build_helper(directory)
    if attach_empty:
        # Native create independently enforces no saved file, geometry,
        # operations or machine groups before the first mutation.
        mcp(directory,'attach-empty-inspect','mastercam_inspect',{})
    else:
        mcp(directory,'launch-create','mastercam_launch',{})
    wait_ready(directory,'ready-create-')
    created=native_phase(directory,'create','create')
    close_owned(directory,'close-created',created['pid'])
    mcp(directory,'launch-before','mastercam_launch',{'file_path':r['model_path']})
    wait_ready(directory,'ready-before-')
    before=native_phase(directory,'before','reopen')
    simulate(directory,'before',dll)
    material_compare(directory,'before')
    dispatch(directory,'before-close','close',dll,r['target_path'])
    close_owned(directory,'close-before',before['pid'])
    mcp(directory,'launch-after','mastercam_launch',{'file_path':r['model_path']})
    wait_ready(directory,'ready-after-')
    native_phase(directory,'after','reopen')
    simulate(directory,'after',dll)
    material_compare(directory,'after')
    result=verify(directory);write_new(directory/'verification.json',result)
    return result


def verify(directory):
    directory=Path(directory).resolve();r=load(directory/'request.json');errors=[]
    if 'operations' in r:
        from .plan_multi import verify_multi
        return verify_multi(directory)
    def check(condition,message):
        if not condition:errors.append(message)
    manifest=load(directory/'source_manifest.json')
    check(digest(directory/'request.json')==manifest['request_sha256'],'request hash')
    for name,value in manifest['source_sha256'].items():
        path=Path(__file__) if name==Path(__file__).name else NATIVE/name
        check(digest(path)==value,'source changed: '+name)
    compile_plan(r['plan_path'],r['binding_path'])
    a,b=load(directory/'before.json'),load(directory/'after.json')
    check(a['pid']!=b['pid'],'fresh host')
    for mode,receipt in [('before',a),('after',b)]:
        check(receipt['ok'] is True and receipt['mode']=='reopen' and receipt['regeneration_performed'] is False,'readback status')
        check(receipt['request_sha256']==digest(directory/'request.json') and receipt['run_id']==r['run_id'],'readback identity')
        snap=receipt['snapshot'];tool=snap['tool']
        check(snap['operation_name']==r['operation_name'] and snap['operation_type']=='Mastercam.Operations.ContourOperation' and snap['operation_count']==1 and snap['geometry_count']==4 and snap['dirty'] is False,'operation binding')
        for key in ('depth_mm','feed_mm_min','spindle_rpm'):check(snap[key]==r[key],'readback '+key)
        for key,request_key in [('diameter_mm','tool_diameter_mm'),('length_mm','tool_length_mm'),('flute_length_mm','flute_length_mm'),('shoulder_length_mm','shoulder_length_mm'),('holder_diameter_mm','holder_diameter_mm'),('holder_length_mm','holder_length_mm')]:
            check(tool[key]==r[request_key],'tool '+key)
        stock=snap['stock'];check(stock['StockSize']==dict(x=r['width_mm']+2*r['margin_mm'],y=r['height_mm']+2*r['margin_mm'],z=r['stock_height_mm']),'stock dimensions')
        check(stock['StockOrigin']==dict(x=r['width_mm']/2,y=r['height_mm']/2,z=0) and stock['StockPlaneID']==1 and stock['StockShape']==0,'stock position')
        check(snap['chain']['closed'] is True and snap['chain']['curves_count']==4 and snap['chain']['area_mm2']==r['width_mm']*r['height_mm'],'chain binding')
        check(snap['path']['data_valid'] is True and snap['path']['travel_valid'] is True and snap['path']['cycle_time_seconds']>0,'path readback')
    check(a['snapshot']==b['snapshot']==load(directory/'create.json')['snapshot'],'native geometry/tool/stock/path persistence')
    check(a['model_sha256']==b['model_sha256']==digest(Path(r['model_path'])),'model persistence')
    for key in ('host_version','api_version','api_sha256','machine_sha256'):
        check(a[key]==b[key],key+' changed')
    s=[load(directory/(name+'-export.json')) for name in ('before','after')]
    meshes=[]
    for name,native in zip(('before','after'),s):
        check(native['ok'] is True and native['motion']['completed'] is True,'motion incomplete')
        motion=native['motion'];check(motion['input_complete'] is True and motion['is_running'] is False and motion['is_busy'] is False and motion['position']['Index']==motion['num_moves']-1,'motion terminal state')
        host=a if name=='before' else b
        check(native['pid']==host['pid'] and native['model_path']==r['model_path'],'simulation identity')
        helper=load(directory/'helper.json');check(native['bridge_sha256']==helper['sha256']==digest(Path(helper['path'])),'helper hash')
        opts=native['collision_options'];check(all(opts.get(k) is True for k in ('CheckToolAgainstStock','CheckStockAgainstMillingHolder','CheckStockAgainstMillingShank','CheckStockAgainstMillingShoulder')),'native check options')
        check(native['motion']['num_moves']>0 and native['motion']['operation_count']==1,'motion count')
        check(native['target_sha256']==r['target_sha256'],'target binding')
        check(native['checks']=={'enabled':True,'between_moves':True},'check settings')
        check(not native['report_groups'],'native collision/report events')
        check(len(native['verifiers'])==1,'verifier count')
        v=native['verifiers'][0]
        check(v['target_count']==1 and v['gouges']==[] and v['excess']==[],'gouge/excess')
        for part in ('holder','shaft','arbor'):
            check(v[part]['IsCollisionChecked'] is True and v[part]['RapidCollisionReportSuppressed'] is False,'disabled '+part)
        check(v['current_volume_mm3']<v['initial_volume_mm3'],'no material removed')
        check(v['gouge_threshold_mm']==-.1 and v['excess_threshold_mm']==.1,'comparison threshold')
        check(0<v['precision_mm']<=.1 and 0<v['collision_tolerance_mm']<=.1524 and 0<v['holder_tolerance_mm']<=.1524,'native resolution/tolerance')
        material=load(directory/(name+'-material.json'))
        check(material['status']=='measured' and material['missing_material_mm3']<=1e-6 and material['extra_material_mm3']<=1e-6,'P01 bidirectional material difference')
        check(material['inputs']['target']['sha256'].lower()==r['step_sha256'] and material['inputs']['mesh']['sha256'].lower()==digest(directory/(name+'-ipw.json')),'material input binding')
        check(load(directory/(name+'-ipw.json'))['source_stl_sha256']==digest(directory/(name+'-ipw.stl')),'STL polygon binding')
        mesh=mesh_stats(directory/(name+'-ipw.stl'));meshes.append(mesh)
        expected=(r['width_mm']+2*r['margin_mm'])*(r['height_mm']+2*r['margin_mm'])*(r['stock_height_mm']+r['depth_mm'])-r['width_mm']*r['height_mm']*r['depth_mm']
        check(abs(mesh['volume_mm3']-expected)<1e-4,'IPW analytic volume')
        check(mesh['min']==[-r['margin_mm'],-r['margin_mm'],-r['stock_height_mm']] and mesh['max']==[r['width_mm']+r['margin_mm'],r['height_mm']+r['margin_mm'],0],'IPW world frame')
    check(meshes[0]['geometry_sha256']==meshes[1]['geometry_sha256'],'reopened IPW geometry')
    def stable(v):
        return {k:x for k,x in v.items() if k not in {'pid','utc','ipw_path','action'}} if isinstance(v,dict) else v
    for key in ('motion','checks','collision_options','stock_to_world','report_groups'):
        check(s[0][key]==s[1][key],key+' reopen')
    check(stable(s[0]['verifiers'][0])==stable(s[1]['verifiers'][0]),'simulation numeric results changed')
    result=dict(schema_version='aicnc.mastercam-plan-simulation-verification/0.1',passed=not errors,errors=errors,
        model_path=r['model_path'],model_sha256=digest(Path(r['model_path'])),plan_sha256=r['plan_sha256'],
        fresh_pids=[a['pid'],b['pid']],meshes=meshes,scope='single rectangular contour; native material removal and tool assembly versus stock; sidecar target/settings replayed after reopen',
        production_released=False,postprocessing_performed=False,machine_simulation_verified=False)
    schema(result,'verification')
    return result


def validate_bound_stand_2027(directory):
    from referencing import Registry, Resource
    directory=Path(directory).resolve()
    b=load(directory/'trial-binding.json');plan=load(directory/'cam_plan.json')
    Draft202012Validator(load(ROOT/'schemas/mastercam_bound_stand_trial.schema.json')).validate(b)
    for file,key in [('source.step','source_sha256'),('cam_plan.json','plan_sha256'),('target.stl','target_sha256')]:
        require(digest(directory/file)==b[key],f'Stand input changed: {file}')
    documents=[load(ROOT/f'schemas/{name}.schema.json') for name in ('features','feature_taxonomy','manufacturing_context','cam_plan')]
    registry=Registry().with_resources((doc['$id'],Resource.from_contents(doc)) for doc in documents)
    for file,contract in [('features.json','features'),('manufacturing_context.json','manufacturing_context'),('cam_plan.json','cam_plan')]:
        Draft202012Validator(load(ROOT/f'schemas/{contract}.schema.json'),registry=registry).validate(load(directory/file))
    require(plan['source_features']['sha256'].lower()==digest(directory/'features.json') and plan['manufacturing_context']['sha256'].lower()==digest(directory/'manufacturing_context.json'),'Stand plan provenance changed')
    features=load(directory/'features.json');context=load(directory/'manufacturing_context.json')
    require(b['source_face_namespace']==features['face_id_namespace']==plan['source_features']['face_id_namespace'],'Stand face namespace changed')
    require(features['source']['step_sha256'].lower()==b['source_sha256'] and features['part_id']==plan['part_id'],'Stand source identity changed')
    require(context['context_id']==plan['manufacturing_context']['context_id'],'Stand context identity changed')
    context_tools={t['tool_id']:t for t in context['tools']}
    for op in b['operations']:
        require(all(context_tools.get(op['tool']['tool_id'],{}).get(key)==value for key,value in op['tool'].items()),'Stand context tool changed')
    validate_bound_stand_profile(plan,b)
    return b


def validate_bound_stand_profile(plan,b):
    """Reject plan fields that this source-bound native template cannot implement."""
    Draft202012Validator(load(ROOT/'schemas/mastercam_bound_stand_trial.schema.json')).validate(b)
    require(len(plan['setups'])==2 and not plan['unplanned_features'],'Stand setup/coverage mismatch')
    require(plan['status']=='needs_review','Software trial must retain review status')
    for setup,direction,count in zip(plan['setups'],([0,0,-1],[0,0,1]),(3,6)):
        require(setup['machining_direction']==direction and len(setup['operations'])==count,'Stand setup direction/partition changed')
        require(setup['stock']==dict(type='box',dimensions=[18,18,10],material='unspecified'),'Stand stock changed')
        require(setup['work_coordinate_system']==dict(name='G54',origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],z_axis=[0,0,1]),'Stand WCS changed')
    operations=[o for s in plan['setups'] for o in s['operations']]
    require(len(operations)==9,'Stand operation coverage')
    expected=[('external',False,10,-.05,1,4),('through',False,10,-2,2,6.2),('top_chamfer',False,10,10,3,6),('counterbore',True,0,-6.4,1,4)]
    expected += [(f'blind_{n}',True,0,-(7.5+1.025/math.tan(math.radians(59))),4,2.05) for n in (14,16,18,20)]
    expected += [('bottom_chamfer',True,0,0,3,6)]
    origins=[[0,0,10]]*3+[[0,0,0],[-5,-5,0],[5,-5,0],[5,5,0],[-5,5,0],[0,0,0]]
    face_groups=[list(range(8)),[8],list(range(21,29)),[11,12],[13,14],[15,16],[17,18],[19,20],list(range(29,37))]
    types=['contouring','drilling','chamfering','pocketing']+['drilling']*4+['chamfering']
    tool_types={1:('EM4','flat_end_mill'),2:('DR6.2','drill'),3:('CH6','chamfer_mill'),4:('DR2.05','drill')}
    for index,(op,native,want) in enumerate(zip(operations,b['operations'],expected)):
        got=(native['role'],native['bottom'],native['top'],native['depth'],native['tool_number'],native['tool']['diameter'])
        require(got==want,'Unsupported stand operation binding')
        require(native['origin']==origins[index],'Stand hole/contour origin changed')
        require(native['name']==('S2_' if native['bottom'] else 'S1_')+native['role'],'Stand operation name changed')
        require((native['tool']['tool_id'],native['tool']['tool_type'])==tool_types[native['tool_number']],'Stand tool type changed')
        require(native['face_ids']==[f'F{n:04d}' for n in face_groups[index]],'Stand face binding changed')
        require(op['operation_type']==types[index] and op['strategy']=='bound_source_'+types[index],'Stand strategy changed')
        require(op['status']=='needs_review','Stand operation must retain review status')
        require(op['safety']==dict(clearance=10,retract=5,stock_to_leave_radial=0,stock_to_leave_axial=0),'Stand safety changed')
        for key in ('operation_id','tool','cutting_parameters','face_ids','feature_instance_ids'):
            require(op[key]==native[key],f'Stand plan/native mismatch: {key}')


def validate_bound_stand_simulation(final):
    motion=final['motion']
    require(final['ok'] and motion['completed'] and motion['input_complete'] and not motion['is_running'] and not motion['is_busy'],'Motion incomplete')
    require(motion['operation_count']==9 and motion['num_moves']==233 and motion['position']['Index']==232,'Stand motion coverage changed')
    require(final['checks']==dict(enabled=True,between_moves=True),'Collision checks disabled')
    require(final['quality_policy']['adaptive_quality_disabled'] and not final['quality_policy']['allow_auto_adjust_precision'],'Adaptive precision enabled')
    require(final['report_groups']==[] and len(final['verifiers'])==1,'Native collision report is not empty')
    for v in final['verifiers']:
        require(v['gouges']==[] and v['excess']==[],'Native deviation report is not empty')
        require(0<v['precision_mm']<=.0051 and 0<v['cutting_tolerance_mm']<=.0051 and 0<v['collision_tolerance_mm']<=.0201 and 0<v['holder_tolerance_mm']<=.0201,'Tolerance readback changed')
        require(v['target_count']==1 and abs(v['gouge_threshold_mm']+.02)<1e-6 and abs(v['excess_threshold_mm']-.02)<1e-6,'Deviation target/threshold changed')
        require(all(v[k]['IsCollisionChecked'] and not v[k]['RapidCollisionReportSuppressed'] and not v[k]['RemovesMaterial'] for k in ('holder','shaft','arbor')),'Assembly collision checks disabled')


def execute_bound_stand_2027(directory,label,mode):
    """Source-locked profile in the existing P08 executor; no general STEP compiler."""
    global _client
    directory=Path(directory).resolve()
    require(directory.is_relative_to(Path(runtime_config()['workspace']).resolve()),'Trial workspace required')
    require(label and all(c.isalnum() or c in '-_' for c in label),'Invalid run label')
    require(mode in ('create','reopen'),'Invalid stand mode')
    validate_bound_stand_2027(directory)
    def note(message):print(message,flush=True)
    def native(stage,template,values):
        name=label+'-'+stage;script=directory/(name+'.csx');receipt=directory/(name+'.json')
        render(NATIVE/template,dict(values,RECEIPT=str(receipt)),script)
        return compiled_script(directory,name,script,receipt,net10=True)
    with McpConnection() as client:
        _client=client
        try:
            note('Native '+mode)
            result=native('native','aicnc_bound_stand_2027.csx',dict(ROOT=str(directory),MODE=mode))
            model=directory/'stand-2setup.mcam'
            framework=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319'
            sources=[NATIVE/'SimulationDomainBridge.cs',NATIVE/'SimulationFrameworkEntry.cs']
            dll=directory/('SimulationBridgeHost.'+hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()[:12]+'.dll')
            if not dll.exists():
                refs=[framework/'WPF'/x for x in ('WindowsBase.dll','PresentationFramework.dll','PresentationCore.dll')]+[framework/'System.Xaml.dll',framework/'System.Web.Extensions.dll']
                command([framework/'csc.exe','/nologo','/target:library','/out:'+str(dll),*['/r:'+str(x) for x in refs],*sources])
            write_new(directory/(label+'-helper.json'),dict(path=str(dll),sha256=digest(dll),source_sha256={p.name:digest(p) for p in sources}))
            def sim(stage,action,artifact=''):
                name=label+'-'+stage;request=directory/(name+'.request.json');receipt=directory/(name+'.json');dispatch_receipt=directory/(name+'.dispatch.json');script=directory/(name+'.csx')
                write_new(request,dict(action=action,receipt=str(receipt),model=str(model),artifact=str(artifact),dispatch_receipt=str(dispatch_receipt)))
                render(NATIVE/'aicnc_simulation_dispatch_2027.csx',dict(MODEL=str(model),MODEL_SHA=digest(model),REQUEST=str(request),REQUEST_SHA=digest(request),DLL=str(dll),DLL_SHA=digest(dll)),script)
                compiled_script(directory,name,script,dispatch_receipt,net10=True)
                until=time.monotonic()+(180 if action=='export' else 45)
                next_note=time.monotonic()+15
                while not receipt.exists() and time.monotonic()<until:
                    time.sleep(.1)
                    if time.monotonic()>=next_note:
                        note('Waiting for native '+action+' receipt; request is not replayed')
                        next_note=time.monotonic()+15
                require(receipt.exists(),'Unknown simulator outcome; do not replay')
                value=load(receipt);require(value.get('ok') is True,'Simulator failed: '+str(value))
                return value
            start=directory/(label+'-start.csx');start_receipt=directory/(label+'-start.json')
            start.write_text('#r '+json.dumps(json_assembly())+'\n'+
                'if(Mastercam.IO.FileManager.CurrentFileName!='+json.dumps(str(model))+')throw new System.Exception("Wrong file");\n'+
                'Mastercam.Operations.OperationsManager.SelectOperations(Mastercam.Support.SearchManager.GetOperations());\n'+
                'Mastercam.Support.ExternalAppsManager.RunFTCommand("OMverifySelectedOperations");\n'+
                'System.IO.File.WriteAllText('+json.dumps(str(start_receipt))+',"{\\"ok\\":true}");',encoding='utf-8')
            compiled_script(directory,label+'-start',start,start_receipt,net10=True)
            for n in range(30):
                ready=sim(f'ready{n}','ready')
                if ready['ready']:break
                time.sleep(1)
            require(ready['ready'],'Simulator initialization timeout')
            note('Configure 0.005 mm resolution and 0.02 mm checks')
            sim('quality','quality')
            for n in range(30):
                ready=sim(f'fine{n}','ready-fine')
                if ready['ready'] and ready['precision_mm']<=.0051:break
                time.sleep(1)
            require(ready['ready'] and ready['precision_mm']<=.0051,'Fine precision unavailable')
            sim('configure','configure',directory/'target.stl')
            sim('run','run')
            for n in range(30):
                state=sim(f'inspect{n}','inspect')
                if state['motion']['completed']:break
                time.sleep(1)
            require(state['motion']['completed'],'Motion incomplete')
            final=sim('export','export',directory/(label+'-ipw.stl'))
            schema(final,'simulator_receipt')
            validate_bound_stand_simulation(final)
            note('Complete: '+str(directory/(label+'-ipw.stl')))
            return dict(native=result,simulation=final)
        finally:_client=None


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('directory',type=Path)
    p.add_argument('--plan',type=Path);p.add_argument('--binding',type=Path);p.add_argument('--attach-empty',action='store_true');a=p.parse_args()
    result=prepare(a.plan,a.binding,a.directory) if a.action=='prepare' else execute(a.directory,a.attach_empty) if a.action=='run' else verify(a.directory)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('passed',True) else 1

if __name__=='__main__':raise SystemExit(main())
