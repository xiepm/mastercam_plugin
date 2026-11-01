"""Export an explicit, hash-recorded source subset; no CAD, weights or credentials."""
import argparse, ast, hashlib, json, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def export(source):
    source=Path(source).resolve();dest=ROOT/'ai/aicnc';selected=set()
    packages={'cad_core':'01_cad_core','capp_planner':'07_capp_planner','mastercam_bridge':'08_mastercam_bridge'}
    def add(rel):
        rel=Path(rel).as_posix()
        if rel in selected:return
        p=source/rel
        if not p.is_file():raise FileNotFoundError(p)
        selected.add(rel)
        if p.suffix!='.py':return
        for n in ast.walk(ast.parse(p.read_text('utf-8-sig'))):
            if not isinstance(n,ast.ImportFrom):continue
            if n.level:
                base=p.parent
                for _ in range(n.level-1):base=base.parent
                names=[n.module] if n.module else [x.name for x in n.names]
                for name in names:
                    q=base.joinpath(*name.split('.'))
                    if q.with_suffix('.py').is_file():add(q.with_suffix('.py').relative_to(source))
                    elif (q/'__init__.py').is_file():add((q/'__init__.py').relative_to(source))
            elif n.module and n.module.split('.')[0] in packages:
                parts=n.module.split('.');q=source/'projects'/packages[parts[0]]/'src'/Path(*parts)
                if q.with_suffix('.py').is_file():add(q.with_suffix('.py').relative_to(source))
                elif (q/'__init__.py').is_file():add((q/'__init__.py').relative_to(source))
    for package,project in packages.items():add(f'projects/{project}/src/{package}/__init__.py')
    for name in ('core','constructive_templates','faceted_material_difference'):
        add(f'projects/01_cad_core/src/cad_core/{name}.py')
    for name in ('contour_smoke','plan_simulation','plan_multi','configuration_audit','cimco_setup','stand_replay'):
        add(f'projects/08_mastercam_bridge/src/mastercam_bridge/{name}.py')
    for name in ('prepare_stand_trial.py','run_bound_stand_2027.py','verify_bound_stand_2027.py',
                 'create_multi_plan_fixture.py','create_plan_simulation_fixture.py',
                 'prepare_stand_local_preview_post.py','prepare_stand_zfirst_post.py',
                 'verify_stand_local_preview_nc.py','verify_stand_zfirst_nc.py','verify_stand_setups_2027.py','compare_simulation_stls.py'):
        add('projects/08_mastercam_bridge/tools/'+name)
    for p in (source/'projects/08_mastercam_bridge/src/mastercam').glob('aicnc*.csx'):add(p.relative_to(source))
    for name in ('SimulationDomainBridge.cs','SimulationFrameworkEntry.cs'):
        add('projects/08_mastercam_bridge/src/mastercam/'+name)
    for name in ('features','feature_taxonomy','manufacturing_context','cam_plan','mastercam_contour_smoke',
                 'mastercam_plan_simulation','mastercam_plan_multi','mastercam_bound_stand_trial',
                 'mastercam_setup_readback','mastercam_configuration_audit','nx_native_ipw_polygons','mastercam_setup_replay'):
        add('schemas/'+name+'.schema.json')
    for name in ('features','manufacturing_context','cam_plan','mastercam_setup_replay','mastercam_setup_readback'):
        add('schemas/examples/'+name+'.example.json')
    files=[]
    base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    for rel in sorted(selected):
        data=(source/rel).read_bytes();out=data;changes=[]
        if rel.endswith(('.py','.csx','.cs')):
            text=data.decode('utf-8-sig')
            if rel.endswith('aicnc_contour_smoke.csx'):
                text=text.replace('#r "System.Web.Extensions"','#r "__SYSTEM_TEXT_JSON__"')
                text=text.replace('System.Web.Script.Serialization.JavaScriptSerializer','AicncPortableJson')
                text=text.replace('FileName = "AICNC synthetic contour validation tool"','FileName = "", Name = "AICNC synthetic contour validation tool"')
                text=text.replace('Require(Mastercam.IO.FileManager.SaveAs(model, false), "SaveAs failed");','Require(Mastercam.IO.FileManager.SaveAs(model, false), "SaveAs failed");\n                Mastercam.IO.FileManager.CurrentFileName = model;\n                Require(Mastercam.IO.FileManager.Save(), "Save failed");')
                text+='\n'+(ROOT/'ai/compiler/PortableJson.cs').read_text('utf-8')
                changes.append('2027 smoke compatibility: System.Text.Json adapter, tool name/file distinction and SaveAs current path readback')
            if rel.endswith('contour_smoke.py'):
                text=text.replace('text = TEMPLATE.read_text(encoding="utf-8")','text = TEMPLATE.read_text(encoding="utf-8")\n        assembly=subprocess.check_output([__import__("sys").executable,str(ROOT.parent/"tools/compile_script.py"),"--json-assembly"],text=True).strip()\n        text=text.replace("__SYSTEM_TEXT_JSON__",assembly.replace("\\\\","/"))')
                text=text.replace('subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()', 'json.loads((ROOT/"source-manifest.json").read_text(encoding="utf-8"))["upstream_base_commit"]')
                changes.append('2027 smoke resolves local JSON assembly and recorded source revision, works without .git')
            if rel.endswith('plan_simulation.py'):
                text=text.replace('PYTHON = Path("D:/NXTEST/.venv/Scripts/python.exe")','PYTHON = Path(sys.executable)')
                text=text.replace('MCP_CALL = Path("D:/NXTEST/scripts/mcp_call.py")','MCP_CALL = ROOT.parent / "tools/mcp_call.py"\n\ndef runtime_config():\n    path=os.environ.get("MC_PLUGIN_AI_CONFIG") or os.environ.get("MC_BRIDGE_CONFIG")\n    if not path:raise ValueError("Portable runtime configuration is required")\n    return load(Path(path))\n\ndef json_assembly():\n    return command([sys.executable,ROOT.parent/"tools/compile_script.py","--json-assembly"]).strip()')
                text=text.replace("Path('D:/NXTEST/mastercam').resolve()","Path(runtime_config()['workspace']).resolve()")
                text=text.replace("cfg=tomllib.loads((Path.home()/'.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['mastercam']","cfg=runtime_config()['upstream']")
                text=text.replace("['C:/Program Files/dotnet/dotnet.exe','D:/NXTEST/mastercam/compat-2027-20261024/Mc2027Compile.exe',script,'all']","[sys.executable,ROOT.parent/'tools/compile_script.py','--script',script,'--config',runtime_config()['upstream']['env']['MC_BRIDGE_CONFIG']]")
                text=text.replace("Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319')","Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319'")
                text=text.replace("start.write_text('#r \"C:/Program Files/dotnet/shared/Microsoft.NETCore.App/10.0.0/System.Text.Json.dll\"\\n'+","start.write_text('#r '+json.dumps(json_assembly())+'\\n'+")
                text=text.replace("text=template.read_text(encoding='utf-8-sig')","text=template.read_text(encoding='utf-8-sig')\n    if '__SYSTEM_TEXT_JSON__' in text:text=text.replace('__SYSTEM_TEXT_JSON__',json_assembly().replace('\\\\','/'))")
                changes.append('Portable runtime/workspace/MCP/static compiler references; native plan semantics unchanged')
            if 'C:/Program Files/dotnet/shared/Microsoft.NETCore.App/10.0.0/System.Text.Json.dll' in text:
                text=text.replace('C:/Program Files/dotnet/shared/Microsoft.NETCore.App/10.0.0/System.Text.Json.dll','__SYSTEM_TEXT_JSON__')
                changes.append('Render .NET assembly reference using locally installed .NET 10 runtime')
            old="subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()"
            if old in text:
                text=text.replace(old,"json.loads((ROOT/'source-manifest.json').read_text(encoding='utf-8'))['upstream_base_commit']")
                changes.append('ZIP runtime reads recorded upstream base commit instead of requiring .git')
            if changes:out=text.encode('utf-8')
        p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(out)
        files.append({'path':rel,'source_sha256':digest(data),'distributed_sha256':digest(out),'adaptations':changes})
    manifest={'version':1,'source_project':'AI-CNC','upstream_base_commit':base,
              'source_scope':'selected current worktree bytes, including uncommitted files; base commit alone is not their identity',
              'model_weights_included':False,'customer_parts_included':False,'files':files}
    (dest/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(files),'bytes':sum((dest/f['path']).stat().st_size for f in files)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);export(p.parse_args().source)
