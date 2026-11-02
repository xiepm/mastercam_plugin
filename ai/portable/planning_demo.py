"""Explicit synthetic evidence for package acceptance, never a real KB fallback."""
import copy,shutil
from pathlib import Path
from .common import ROOT,load,sha,write_new


def make_knowledge(root):
    root=Path(root);case=root/'cases/synthetic';frozen=case/'02_initial_plan/独立工艺初稿.md'
    frozen.parent.mkdir(parents=True)
    frozen.write_text('Synthetic independent plan: verify hole guidance before drilling. No MCAM readback.','utf-8')
    (case/'report.md').write_text('Synthetic workflow test only; placeholder STEP/MCAM provenance identifiers. No real historical machining evidence.','utf-8')
    lib=load(ROOT/'ai/aicnc/schemas/examples/historical_process_reference.example.json')
    lib.update(case_id='synthetic',part_name='Synthetic reference only; no MCAM',source_step_sha256='1'*64,source_mcam_sha256='2'*64,frozen_initial_plan_sha256=sha(frozen))
    lib['evidence']=[dict(path='02_initial_plan/独立工艺初稿.md',sha256=sha(frozen))]
    base=lib['templates'][0];lib['templates']=[]
    for name,kind,advice in [('experience','agreement_refinement','Evaluate spotting or other guidance before drilling, subject to drill manufacturer and entry face'),('conflict','historical_conflict','Do not copy a conflicting historical hole diameter'),('gap','missing_stage','Actual stock, fixture and tool assemblies remain unconfirmed')]:
        item=copy.deepcopy(base)
        item.update(id=name,kind=kind,title='Synthetic hole '+name,tags=['孔','定位','装夹'],conditions=['New part has through holes'],exclusions=['Not verified machining parameters'],initial_plan='Initial synthetic hole route',historical_observation='Synthetic test record only',planning_advice=advice)
        lib['templates'].append(item)
    path=case/'05_templates/reference_library.json';write_new(path,lib)
    entry=dict(case_id='synthetic',title='Synthetic reference only',library='cases/synthetic/05_templates/reference_library.json',report='cases/synthetic/report.md',library_sha256=sha(path),templates=3,status='reference_candidate')
    write_new(root/'catalog.json',dict(schema_version='aicnc.local-reference-catalog/0.1',production_enabled=False,cases=[entry]))
    write_new(root/'merged/merge_plan.json',dict(schema_version='aicnc.historical-reference-merge/0.1',production_enabled=False,families=[dict(id='holes',title='孔加工前置检查',summary='Conditional guidance, no universal parameter values',members=['experience'])],conflicts=['conflict'],gaps=['gap']))
    return root


def make_intake(task):
    task=Path(task)
    rows=load(task/'input-sources.json')['sources']
    intake=load(ROOT/'ai/aicnc/schemas/examples/planning_reference_intake.example.json')
    intake['sources']=[{k:r[k] for k in ('id','role','path')} for r in rows]
    intake['requirements'][0]['description']='Two diameter-4 through holes in a synthetic 30 x 20 x 5 plate'
    intake['requirements'][0]['evidence'][0]['locator']='Synthetic drawing hole callout and centre coordinates'
    write_new(task/'intake.json',intake)
    return task/'intake.json'


def make_review(task):
    task=Path(task)
    (task/'plan.md').write_text('## P01 Through-hole planning\nR01: Two diameter-4 through holes. Evaluate guidance before drilling using family:holes and source experience; choose actual spotting/drill sequence only after tool and entry-face review. Do not copy conflicting diameters. Material, stock, fixture and approved cutter assembly remain unknown.\n','utf-8')
    evidence=[dict(source_id='drawing',locator='Synthetic drawing: 2 x diameter 4 THRU')]
    common=dict(reason='Explicit comparison to new synthetic drawing and unresolved resources',requirement_ids=['R01'],plan_sections=['P01'],evidence=evidence)
    review=dict(schema_version='aicnc.planning-reference-review/0.1',packet_sha256=sha(task/'reference_run/packet.json'),plan_path='plan.md',requirement_reviews=[dict(requirement_id='R01',status='addressed',reason='Hole route is covered as a conditional planning decision',plan_sections=['P01'],evidence=evidence)],reference_decisions=[dict(common,reference_id='family:holes',disposition='adapt',selected_source_ids=['experience']),dict(common,reference_id='conflict',disposition='not_applicable',selected_source_ids=[]),dict(common,reference_id='gap',disposition='unresolved',selected_source_ids=[])],additional_findings=[])
    write_new(task/'review.json',review)
    return review
