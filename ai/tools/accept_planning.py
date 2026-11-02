"""Offline fresh-home replay with a public synthetic STEP and drawing."""
import argparse,copy,json,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT,load,sha,write_new
from portable import planning
from portable.planning_demo import make_knowledge,make_intake,make_review
from portable.knowledge_bundle import export_bundle,import_bundle


def run(output):
    root=Path(output).resolve()
    if root.is_relative_to(ROOT):raise ValueError('Acceptance output must be outside repository')
    root.mkdir(parents=True,exist_ok=False)
    kb=make_knowledge(root/'source-kb')
    exported=export_bundle(kb,root/'synthetic-reference.zip')
    imported=import_bundle(root/'synthetic-reference.zip',root/'迁移后的知识库',exported['sha256'])
    receipt=planning.install(root/'private work',root/'clean codex home',imported['knowledge_root'])
    planning.install(root/'private work',root/'clean codex home',imported['knowledge_root'])
    c=planning.config(receipt['planning_config'])
    started=planning.start(c,'synthetic-new-part',ROOT/'ai/samples/planning/plate.step',ROOT/'ai/samples/planning/drawing.svg')
    task=Path(started['directory']);intake=make_intake(task)
    prepared=planning.prepare(c,intake,task/'reference_run');review=make_review(task)
    positive=planning.audit(c,task/'reference_run',task/'review.json',task/'audit.json')
    assert positive['status']=='complete_with_open_items' and not positive['ready_for_cam_execution']
    assert positive['selected_template_ids']==['experience']
    missing_conflict=copy.deepcopy(review);missing_conflict['reference_decisions'].pop(1)
    write_new(task/'missing-conflict.json',missing_conflict)
    rejected=planning.audit(c,task/'reference_run',task/'missing-conflict.json',task/'missing-conflict-audit.json')
    assert rejected['status']=='incomplete' and 'unreviewed_reference: conflict' in rejected['errors']
    (task/'negative-plan.md').write_text('## P01 Incomplete\nNo linked requirement or template.','utf-8')
    missing_req=copy.deepcopy(review);missing_req['plan_path']='negative-plan.md'
    write_new(task/'missing-requirement.json',missing_req)
    incomplete=planning.audit(c,task/'reference_run',task/'missing-requirement.json',task/'missing-requirement-audit.json')
    assert incomplete['status']=='incomplete'
    tamper=task.with_name('negative-tamper');shutil.copytree(task,tamper)
    source=load(tamper/'reference_run/packet.json')['sources'][0]
    (tamper/'reference_run'/source['path']).write_bytes(b'changed synthetic input')
    try:planning.audit(c,tamper/'reference_run',tamper/'review.json',tamper/'tampered-audit.json')
    except ValueError as exc:
        assert 'source_hash_mismatch' in str(exc)
    else:raise AssertionError('Changed evidence was not rejected')
    result=dict(schema_version='mastercam.planning-acceptance/1',passed=True,fixture='public_synthetic',
                installed_in_clean_codex_home=True,installation_idempotent=True,relocated_knowledge_verified=True,
                positive_status=positive['status'],references=prepared['references'],selected_templates=positive['selected_template_ids'],
                negative_checks=['missing_conflict_rejected','missing_requirement_citation_rejected','changed_evidence_rejected'],
                geometry_execution_tested=False,codex_new_session_tested=False,native_cam_executed=False,simulation_performed=False,production_enabled=False)
    write_new(root/'acceptance.json',result)
    from jsonschema import Draft202012Validator
    Draft202012Validator(load(ROOT/'ai/schemas/planning-acceptance.schema.json')).validate(result)
    return result

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.output),ensure_ascii=False,indent=2))
