"""Mastercam 2027 MCP adapter for its installed, local NET-Scripting IPC service."""
import csv
import os
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from mcp.server.fastmcp import FastMCP

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PACKAGE/'ai'))
from portable.common import config, scoped as scope_path, load, sha, token, write_new
from portable.native_host import launch as launch_desktop
sys.path.insert(0,str(PACKAGE/'ai/mcp'))
from runtime import process_guard
CONFIG = config()
ROOT = Path(CONFIG['workspace'])
JOBS = ROOT / 'mastercam/jobs'
JOBS.mkdir(parents=True,exist_ok=True)
LOCK = threading.Lock()
mcp = FastMCP('mastercam-local', instructions='Uses the installed Mastercam NET-Script IPC service. Inspect first. Geometry and scripts run inside the active document. Check returned readback and saved artifacts. No toolpath or postprocessing certification is implied.')

def pid():
    r=subprocess.run(['tasklist','/FI','IMAGENAME eq Mastercam.exe','/FO','CSV','/NH'],capture_output=True,text=True,encoding='mbcs',errors='replace',timeout=10)
    ids=[int(row[1]) for row in csv.reader(io.StringIO(r.stdout)) if len(row)>1 and row[0].lower()=='mastercam.exe']
    if len(ids)!=1: raise RuntimeError(f'Expected exactly one Mastercam.exe; found {ids}')
    return ids[0]

def scoped(path, exists=False):
    return scope_path(path, CONFIG, exists=exists)

def run(path, timeout=60):
    if not LOCK.acquire(blocking=False): raise RuntimeError('Mastercam request is already running')
    try:
        with process_guard(ROOT/'mastercam/native.lock'):
            active=ROOT/'mastercam/active.json'
            if active.exists():
                previous=load(active)
                raise RuntimeError('Unresolved native request '+previous['request_id']+'; inspect its status and host before recovery, do not resubmit.')
            rid=uuid.uuid4().hex; d=ROOT/'mastercam/requests'/rid; d.mkdir(parents=True)
            process_id=pid()
            write_new(d/'request.json',dict(request_id=rid,pid=process_id,script=str(path),script_sha256=sha(path)))
            write_new(active,dict(request_id=rid,pid=process_id))
            try:
                # Preserve the proven Windows bridge's base-interpreter launch:
                # the venv redirector adds another process to native IPC ownership.
                r=subprocess.run([sys._base_executable,str(Path(__file__).with_name('ipc_client.py')),'--pid',str(process_id),'--script',str(path),'--timeout-ms','5000'],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
                ok=r.returncode==0 and 'Ran Successfully.' in r.stdout
                write_new(d/'result.json',dict(request_id=rid,ok=ok,state='transport_complete' if ok else 'failed',stdout=r.stdout[-8000:],stderr=r.stderr[-8000:]))
                active.unlink()
                if not ok:raise RuntimeError((r.stdout+r.stderr)[-5000:])
                return r.stdout.strip()
            except subprocess.TimeoutExpired as error:
                tail=lambda v:(v.decode('utf-8',errors='replace') if isinstance(v,bytes) else v or '')[-8000:]
                write_new(d/'timeout.json',dict(request_id=rid,state='unknown',stdout=tail(error.stdout),stderr=tail(error.stderr),instruction='Native code may still be executing. Never replay without reconciliation.'))
                raise RuntimeError('Native outcome unknown. Request ID: '+rid)
    finally: LOCK.release()

@mcp.tool()
def mastercam_request_status(request_id:str)->dict:
    """Read a base-bridge transport receipt, including after a timeout. Transport success is not native business success. Never resend an unknown mutation."""
    d=ROOT/'mastercam/requests'/token(request_id)
    if (d/'result.json').exists():return load(d/'result.json')
    if (d/'request.json').exists():return dict(load(d/'request.json'),state='unknown',ok=False)
    return {'request_id':request_id,'state':'not_found','ok':False}

def execute(code):
    token=uuid.uuid4().hex
    script=JOBS/f'{token}.csx'
    receipt=JOBS/f'{token}.txt'
    code=code.replace('RECEIPT_PATH',json.dumps(str(receipt)))
    code='try {\n'+code+'\n} catch(System.Exception ex) { System.IO.File.WriteAllText('+json.dumps(str(receipt))+', "NATIVE_ERROR: "+ex.ToString()); }'
    script.write_text(code,encoding='utf-8')
    response=run(script)
    if not receipt.exists(): raise RuntimeError('IPC returned but the native script produced no receipt')
    readback=receipt.read_text(encoding='utf-8-sig')
    if readback.startswith('NATIVE_ERROR:'): raise RuntimeError(readback)
    return {'ipc_response':response,'receipt':str(receipt),'native_readback':readback}

@mcp.tool()
def mastercam_inspect() -> dict:
    """Read native current filename, units, geometry count and API version."""
    return execute('''var g = Mastercam.Support.SearchManager.GetGeometry();
System.IO.File.WriteAllLines(RECEIPT_PATH, new string[] {
"file=" + Mastercam.IO.FileManager.CurrentFileName,
"metric=" + Mastercam.IO.SettingsManager.Metric,
"geometry_count=" + g.Length,
"api=" + typeof(Mastercam.IO.FileManager).Assembly.FullName });''')

@mcp.tool()
def mastercam_run_script(script_path: str) -> dict:
    """Execute a reviewed .csx in the configured private workspace inside active Mastercam. May mutate the document. A timeout has unknown outcome; inspect before retrying."""
    p=scoped(script_path,True)
    if p.suffix.lower()!='.csx': raise ValueError('Expected .csx')
    # Mastercam 2027's IPC reliably executes unique files in its MCP jobs folder.
    # #load retains the original script directory for nested relative references.
    runtime_script=JOBS/f'{uuid.uuid4().hex}.csx'
    runtime_script.write_text('#load '+json.dumps(p.as_posix())+'\n',encoding='utf-8')
    return {'script':str(p),'runtime_script':str(runtime_script),'ipc_response':run(runtime_script)}

@mcp.tool()
def mastercam_create_rectangle(width_mm: float, height_mm: float, output_path: str) -> dict:
    """Create and save a native rectangle in an EMPTY metric document. Refuses existing geometry and output overwrite."""
    if not all(math.isfinite(x) and x>0 for x in [width_mm,height_mm]): raise ValueError('Dimensions must be finite and positive')
    p=scoped(output_path)
    if p.suffix.lower()!='.mcam': raise ValueError('Expected .mcam')
    if p.exists(): raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    result=execute('''if (!Mastercam.IO.SettingsManager.Metric) throw new System.Exception("Expected metric document");
if (Mastercam.Support.SearchManager.GetGeometry().Length != 0) throw new System.Exception("Expected empty document");
var lines=Mastercam.GeometryUtility.GeometryCreationManager.CreateRectangle(new Mastercam.Math.Point3D(0,0,0),new Mastercam.Math.Point3D(WIDTH,HEIGHT,0));
Mastercam.IO.GraphicsManager.FitScreen();
if (!Mastercam.IO.FileManager.SaveAs(OUTPUT_PATH,false)) throw new System.Exception("Save failed");
Mastercam.IO.FileManager.CurrentFileName=OUTPUT_PATH;
if (!Mastercam.IO.FileManager.Save()) throw new System.Exception("Save current document failed");
System.IO.File.WriteAllLines(RECEIPT_PATH,new string[]{"geometry_count="+Mastercam.Support.SearchManager.GetGeometry().Length,"saved="+Mastercam.IO.FileManager.CurrentFileName});'''.replace('WIDTH',repr(width_mm)).replace('HEIGHT',repr(height_mm)).replace('OUTPUT_PATH',json.dumps(str(p))))
    if not p.is_file() or p.stat().st_size == 0: raise RuntimeError('Native SaveAs returned but file is missing')
    return dict(result,output_path=str(p),file_size=p.stat().st_size)

@mcp.tool()
def mastercam_launch(file_path: str | None = None) -> dict:
    """Launch installed Mastercam with an optional workspace DXF/STEP/MCAM. Requires no existing Mastercam process. Native FileManager.New/Open inside IPC is not supported by this adapter."""
    return launch_desktop(CONFIG,file_path)

@mcp.tool()
def mastercam_save_as(output_path: str) -> dict:
    """Save current Mastercam geometry to a NEW .mcam file in the workspace and verify file creation."""
    p=scoped(output_path)
    if p.suffix.lower()!='.mcam': raise ValueError('Expected .mcam')
    if p.exists(): raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    result=execute('''if (!Mastercam.IO.FileManager.SaveAs(OUTPUT_PATH,false)) throw new System.Exception("Save failed");
Mastercam.IO.FileManager.CurrentFileName=OUTPUT_PATH;
if (!Mastercam.IO.FileManager.Save()) throw new System.Exception("Save current document failed");
System.IO.File.WriteAllLines(RECEIPT_PATH,new string[]{"file="+Mastercam.IO.FileManager.CurrentFileName,"geometry_count="+Mastercam.Support.SearchManager.GetGeometry().Length});'''.replace('OUTPUT_PATH',json.dumps(str(p))))
    if not p.is_file() or not p.stat().st_size: raise RuntimeError('Saved file missing')
    return dict(result,output_path=str(p),file_size=p.stat().st_size)

@mcp.tool()
def mastercam_inspect_operations() -> dict:
    """Read every native operation's name, runtime type and regeneration state."""
    return execute('''var ops=Mastercam.Support.SearchManager.GetOperations();
var lines=new System.Collections.Generic.List<string>();
lines.Add("operation_count="+ops.Length);
foreach(var op in ops) lines.Add(op.GetType().FullName+"|"+op.Name+"|dirty="+op.Dirty);
System.IO.File.WriteAllLines(RECEIPT_PATH,lines);''')

@mcp.tool()
def mastercam_regenerate_operations(operation_names: list[str]) -> dict:
    """Regenerate named existing operations. Preserve raw return values and check fresh database state; false remains failure. Does not create a machining strategy."""
    if not operation_names or len(set(operation_names)) != len(operation_names):
        raise ValueError('Provide unique operation names')
    names=','.join(json.dumps(n,ensure_ascii=True) for n in operation_names)
    return execute('''var lines=new System.Collections.Generic.List<string>();
try {
var names=new string[]{NAMES};
var all=Mastercam.Support.SearchManager.GetOperations();
var selected=new System.Collections.Generic.List<Mastercam.Database.Operation>();
foreach(var name in names) {
 var matches=System.Array.FindAll(all,op=>op.Name==name);
 if(matches.Length!=1) throw new System.Exception("Expected exactly one operation: "+name);
 selected.Add(matches[0]);
}
foreach(var op in selected) {
 int id=op.GetOperationID();
 lines.Add("operation_id="+id+"|name="+System.Text.Json.JsonSerializer.Serialize(op.Name)+"|beforeDirty="+op.Dirty);
 System.IO.File.WriteAllLines(RECEIPT_PATH,lines);
 bool ok=op.Regenerate();
 // Persist the raw bool before any readback can fail. Never use cached Dirty as a verdict.
 lines.Add("operation_id="+id+"|regenerate_returned="+ok);
 System.IO.File.WriteAllLines(RECEIPT_PATH,lines);
 var fresh=Mastercam.Support.SearchManager.GetOperation(id);
 var data=Mastercam.Support.SearchManager.GetOperationData(id);
 bool freshValid=fresh!=null && fresh.Validate();
 bool? freshDirty=fresh==null?(bool?)null:fresh.Dirty;
 lines.Add("operation_id="+id+"|cachedDirty="+op.Dirty+"|freshDirty="+freshDirty+"|freshValid="+freshValid+"|dataValid="+(data==null?(bool?)null:data.IsValid)+"|dataDirty="+(data==null?(bool?)null:data.Dirty));
 System.IO.File.WriteAllLines(RECEIPT_PATH,lines);
 if(!ok) throw new System.Exception("API_RETURNED_FALSE: "+op.Name);
 if(!freshValid || freshDirty!=false || data==null || !data.IsValid || data.Dirty)
  throw new System.Exception("FRESH_STATE_CHECK_FAILED: "+op.Name);
}
} catch(System.Exception ex) {
 // Handle locally so execute's generic catch cannot overwrite the raw return/readback rows.
 lines.Insert(0,"NATIVE_ERROR: "+ex.ToString());
 System.IO.File.WriteAllLines(RECEIPT_PATH,lines);
}'''.replace('NAMES',names))

@mcp.tool()
def mastercam_post_operations(operation_names: list[str], output_path: str) -> dict:
    """Post named clean operations using their configured native post. Output is for validation, not certified production NC."""
    if not operation_names or len(set(operation_names)) != len(operation_names):
        raise ValueError('Provide unique operation names')
    p=scoped(output_path)
    if p.suffix.lower() not in {'.nc','.tap'}: raise ValueError('Expected .nc or .tap')
    if p.exists(): raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    names=','.join(json.dumps(n,ensure_ascii=True) for n in operation_names)
    result=execute('''var names=new string[]{NAMES};
var all=Mastercam.Support.SearchManager.GetOperations();
var selected=new System.Collections.Generic.List<Mastercam.Database.Operation>();
foreach(var name in names) {
 var matches=System.Array.FindAll(all,op=>op.Name==name);
 if(matches.Length!=1 || matches[0].Dirty) throw new System.Exception("Missing, ambiguous or dirty operation: "+name);
 selected.Add(matches[0]);
}
Mastercam.Operations.OperationsManager.PostOperations(selected.ToArray(),OUTPUT,false,true,false);
System.IO.File.WriteAllText(RECEIPT_PATH,"posted_operation_count="+selected.Count);'''.replace('NAMES',names).replace('OUTPUT',json.dumps(str(p))))
    if not p.is_file() or not p.stat().st_size: raise RuntimeError('Native post produced no NC file')
    return dict(result,output_path=str(p),file_size=p.stat().st_size,production_certified=False)

if __name__=='__main__': mcp.run(transport='stdio')
