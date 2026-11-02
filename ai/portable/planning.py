"""Machine-local routing for the unchanged P07 planning evidence workflow."""
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path
from jsonschema import Draft202012Validator
from .common import ROOT, load, sha, write_new, token
sys.path.insert(0,str(ROOT/'ai/aicnc/projects/07_capp_planner/src'))
from capp_planner.historical_reference_index import compile_index
from capp_planner import planning_reference_workflow as workflow


def verify_snapshot():
    manifest=load(ROOT/'ai/aicnc/source-manifest.json')
    for entry in manifest['files']:
        if sha(ROOT/'ai/aicnc'/entry['path'])!=entry['distributed_sha256']:
            raise ValueError('Packaged source hash mismatch: '+entry['path'])


def config(path):
    c=load(path)
    Draft202012Validator(load(ROOT/'ai/schemas/planning-config.schema.json')).validate(c)
    if Path(c['repository']).resolve()!=ROOT:
        raise ValueError('Package moved; rerun Install-Planning to generate local paths')
    work=Path(c['workspace']).resolve()
    if not Path(c['workspace']).is_absolute() or work.is_relative_to(ROOT):
        raise ValueError('Planning workspace must be absolute and outside repository')
    if c['knowledge_root'] and not Path(c['knowledge_root']).is_absolute():
        raise ValueError('knowledge_root must be an absolute local path')
    return c


def scoped(path,c):
    p=Path(path).resolve()
    if not p.is_relative_to(Path(c['workspace']).resolve()):raise ValueError('Task output outside workspace')
    return p


def knowledge(c):
    if not c['knowledge_root']:
        raise ValueError('Historical knowledge is unconfigured. Import an authorized bundle and configure --knowledge-root; no demo fallback.')
    root=Path(c['knowledge_root']).resolve()
    compile_index(root/'catalog.json',root/'merged/merge_plan.json')
    return root


def install(workspace,codex_home,knowledge_root=None,python=None,p01_python=None,p01_distro='Ubuntu-22.04'):
    verify_snapshot()
    work=Path(workspace).resolve();home=Path(codex_home).resolve()
    if work.is_relative_to(ROOT) or home.is_relative_to(ROOT):
        raise ValueError('Workspace and Codex home must be outside repository')
    cfgpath=work/'planning-config.json'
    old=load(cfgpath) if cfgpath.exists() else None
    kb=str(Path(knowledge_root).resolve()) if knowledge_root else (old or {}).get('knowledge_root')
    geometry=({'distro':p01_distro,'python':p01_python} if p01_python else (old or {}).get('p01'))
    c=dict(schema_version='mastercam.planning-config/1',repository=str(ROOT),workspace=str(work),
           knowledge_root=kb,python=str(Path(python or sys.executable).resolve()),p01=geometry)
    if kb:knowledge(c)
    Draft202012Validator(load(ROOT/'ai/schemas/planning-config.schema.json')).validate(c)
    source=ROOT/'ai/skills/aicnc-plan-new-part';dest=home/'skills/aicnc-plan-new-part'
    # Only identical/current or previously receipted files may be replaced.
    receipt_path=dest/'references/installed-files.json'
    previous=load(receipt_path).get('files',{}) if receipt_path.exists() else {}
    legacy=load(ROOT/'ai/skills/managed-previous.json')['files']
    files={f.relative_to(source).as_posix():sha(f) for f in source.rglob('*') if f.is_file()}
    for rel,digest in files.items():
        target=dest/rel
        if target.exists() and sha(target)!=digest and previous.get(rel)!=sha(target) and sha(target) not in legacy.get('aicnc-plan-new-part/'+rel,[]):
            raise ValueError('Custom skill preserved; choose another Codex home or review migration: '+str(target))
    work.mkdir(parents=True,exist_ok=True)
    if old and old!=c:
        backup=work/('planning-config.before-'+sha(cfgpath)[:12]+'.json')
        if not backup.exists():shutil.copy2(cfgpath,backup)
    for rel in files:
        target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)!=files[rel]:
            backup=work/'skill-backups'/sha(target)/rel
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():shutil.copy2(target,backup)
        shutil.copy2(source/rel,target)
    connection=dict(repository=str(ROOT),planning_config=str(cfgpath),workspace=str(work),python=c['python'])
    for path,data in [(cfgpath,c),(dest/'references/connection.json',connection),(receipt_path,{'files':files})]:
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(path.suffix+'.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8');os.replace(temp,path)
    return dict(planning_config=str(cfgpath),skill=str(dest),knowledge_configured=bool(kb),native_required=False)


def start(c,task_id,step,drawing):
    token(task_id);step=Path(step).resolve();drawing=Path(drawing).resolve()
    if step.suffix.lower() not in ['.step','.stp']:raise ValueError('STEP/STP required')
    if drawing.suffix.lower() not in ['.pdf','.svg','.png','.jpg','.jpeg','.tif','.tiff','.dxf','.dwg']:
        raise ValueError('Drawing must be PDF, image, SVG, DXF or DWG')
    if not step.is_file() or not drawing.is_file():raise ValueError('Input missing')
    knowledge(c)  # Fail before creating a task if reference data is unavailable.
    d=scoped(Path(c['workspace'])/'planning'/task_id,c)
    d.mkdir(parents=True,exist_ok=False)
    rows=[]
    for sid,role,origin in [('cad','step',step),('drawing','drawing',drawing)]:
        target=d/(sid+origin.suffix.lower());shutil.copy2(origin,target)
        rows.append(dict(id=sid,role=role,path=target.name,original_path=str(origin),sha256=sha(target)))
    write_new(d/'input-sources.json',dict(sources=rows))
    if drawing.suffix.lower()=='.pdf':
        import pymupdf
        with pymupdf.open(d/rows[1]['path']) as pdf:
            if pdf.needs_pass:raise ValueError('Password-protected drawing; provide an authorized readable copy')
            (d/'drawing-text.txt').write_text('\n'.join(page.get_text() for page in pdf),'utf-8')
            previews=d/'drawing-previews';previews.mkdir()
            for i in range(min(len(pdf),16)):
                pdf[i].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(previews/f'page-{i+1}.png')
            write_new(d/'drawing-preview.json',dict(pages=len(pdf),rendered=min(len(pdf),16),remaining_pages_need_review=max(0,len(pdf)-16)))
    return dict(directory=str(d),sources=rows,next='Read STEP with configured P01/native geometry and visually inspect drawing; write intake.json, then prepare.',geometry_configured=c['p01'] is not None)


def geometry(c,task):
    d=scoped(task,c);p01=c['p01']
    if not p01:raise ValueError('P01 not configured; install the pinned environment or use actual native geometry readback')
    source=next(x for x in load(d/'input-sources.json')['sources'] if x['role']=='step')
    step=d/source['path']
    if sha(step)!=source['sha256']:raise ValueError('STEP changed since task start')
    out=d/'geometry'
    if out.exists():raise ValueError('Geometry output exists; use a new task/revision')
    def linux(path):
        return subprocess.check_output(['wsl.exe','-d',p01['distro'],'--','wslpath','-a','-u',Path(path).resolve().as_posix()],stderr=subprocess.PIPE).decode('utf-8').strip()
    cmd=['wsl.exe','-d',p01['distro'],'--',p01['python'],linux(ROOT/'ai/tools/inspect_step.py'),'--step',linux(step),'--output',linux(out)]
    subprocess.run(cmd,check=True,timeout=600)
    return dict(output=str(out),aagnet_run=False,native_cam_executed=False)


def prepare(c,intake,run):
    return workflow.prepare(scoped(intake,c),scoped(run,c),knowledge(c))


def audit(c,run,review,output):
    result=workflow.audit(scoped(run,c),scoped(review,c),knowledge(c))
    workflow.write_new(scoped(output,c),result)
    return result
