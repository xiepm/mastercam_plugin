"""Codex planning evidence workflow. Does not generate an alternative CAM IR.

prepare: bind source documents and automatically retrieve from intake tags.
audit: check complete source-bound decisions and explicit requirement coverage.
Engineering interpretations are authored by Codex, not proven by string checks.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from .historical_reference_index import compile_index, digest, retrieve_index

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT/'schemas/planning_reference_workflow.schema.json'


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def validate(data, kind):
    schema = read(SCHEMA)
    registry=Registry()
    for name in ['historical_process_reference.schema.json','historical_reference_index.schema.json']:
        other=read(SCHEMA.parent/name)
        registry=registry.with_resource(other['$id'],Resource.from_contents(other))
    Draft202012Validator({'$ref': '#/$defs/'+kind, '$defs': schema['$defs']},registry=registry).validate(data)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('run_path_outside_root')
    return path


def unique(rows, key):
    values = [r[key] for r in rows]
    if len(set(values)) != len(values):
        raise ValueError('duplicate_'+key)
    return {r[key]: r for r in rows}


def select(index, intake, step_hash):
    """Exclude this same STEP, including MCAM revisions, before selecting hits."""
    index = json.loads(json.dumps(index))
    for f in index['families']:
        f['variants'] = [v for v in f['variants'] if v['source_step_sha256'].lower() != step_hash.lower()]
        f['source_case_count'] = len({v['case_id'] for v in f['variants']})
        f['distinct_geometry_count'] = len({v['source_step_sha256'].lower() for v in f['variants']})
    index['families'] = [f for f in index['families'] if f['variants']]
    for category in ['conflicts', 'gaps']:
        index[category] = [v for v in index[category] if v['source_step_sha256'].lower() != step_hash.lower()]
    terms = sorted({tag for r in intake['requirements'] for tag in r['tags']})
    results = retrieve_index(index, terms, 100)
    # Limit experience families; never silently truncate matched issues.
    selected = []
    for f in results['families'][:6]:
        selected.append(dict(id='family:'+f['id'], category='family', title=f['title'],
                             summary=f['summary'], sources=f['variants']))
    for category in ['conflicts', 'gaps']:
        for v in results[category]:
            v = {k:value for k,value in v.items() if k not in ['matched_terms','retrieval_score']}
            selected.append(dict(id=v['record']['id'], category=category, title=v['record']['title'],
                                 summary=v['record']['planning_advice'], sources=[v]))
    return terms, selected


def check_evidence(rows, source_ids):
    for e in rows:
        if e['source_id'] not in source_ids:
            raise ValueError('unknown_source_id: '+e['source_id'])


def prepare(intake_path: Path, run_dir: Path, knowledge_root: Path):
    intake_path, run_dir = Path(intake_path).resolve(), Path(run_dir).resolve()
    intake = read(intake_path); validate(intake, 'intake')
    ids = unique(intake['sources'], 'id')
    unique(intake['requirements'], 'id')
    steps = [s for s in intake['sources'] if s['role'] == 'step']
    if len(steps) != 1:
        raise ValueError('exactly_one_step_source_required')
    for req in intake['requirements']:
        check_evidence(req['evidence'], ids)
    for s in intake['sources']:
        if not (intake_path.parent/s['path']).is_file():
            raise ValueError('source_missing: '+s['id'])
    index = compile_index(knowledge_root/'catalog.json', knowledge_root/'merged/merge_plan.json')
    terms, selected = select(index, intake, digest(intake_path.parent/steps[0]['path']))
    if run_dir.exists():
        raise ValueError('run_directory_exists_use_new_revision')
    run_dir.mkdir(parents=True)
    sources = []
    for s in intake['sources']:
        origin = (intake_path.parent/s['path']).resolve()
        local = 'inputs/'+s['id']+origin.suffix.lower()
        target = contained(run_dir, local); target.parent.mkdir(exist_ok=True)
        shutil.copy2(origin, target)
        sources.append(dict(id=s['id'],role=s['role'],path=local,original_path=str(origin),sha256=digest(target)))
    write_new(run_dir/'intake.json', intake)
    write_new(run_dir/'reference_index.json', index)
    packet = dict(schema_version='aicnc.planning-reference-packet/0.1',
        created_utc=datetime.now(timezone.utc).isoformat(), part_name=intake['part_name'],
        intake_sha256=digest(run_dir/'intake.json'), index_sha256=digest(run_dir/'reference_index.json'),
        sources=sources, terms=terms, references=selected,
        production_enabled=False, simulation_performed=False)
    validate(packet,'packet')
    write_new(run_dir/'packet.json',packet)
    (run_dir/'packet.sha256').write_text(digest(run_dir/'packet.json')+'\n','utf-8')
    md=f"# 规划前检索：{intake['part_name']}\n\n自动查询词：{', '.join(terms)}。本STEP自身历史已排除。当前按关键词检索；无命中不等于不存在相关风险。\n\n"
    for item in selected:
        md+=f"## {item['id']} — {item['title']} [{item['category']}]\n\n{item['summary']}\n\n"
        for v in item['sources']:
            t=v['record']
            md+=f"- 来源模板：`{t['id']}`；案例：{v['part_name']}\n- 条件：{'；'.join(t['conditions'])}\n- 排除：{'；'.join(t['exclusions'])}\n- 历史事实：{t['historical_observation']}\n- 规划提示：{t['planning_advice']}\n\n"
    (run_dir/'reference_context.md').write_text(md,'utf-8')
    return dict(run_dir=str(run_dir),packet_sha256=digest(run_dir/'packet.json'),
                references=len(selected),terms=terms,context=str(run_dir/'reference_context.md'))


def verify_packet(run_dir, knowledge_root):
    run_dir = Path(run_dir).resolve()
    packet = read(run_dir/'packet.json');validate(packet,'packet')
    if digest(run_dir/'packet.json') != (run_dir/'packet.sha256').read_text('utf-8').strip():
        raise ValueError('packet_hash_mismatch')
    for name, key in [('intake.json','intake_sha256'),('reference_index.json','index_sha256')]:
        if digest(run_dir/name) != packet[key]:raise ValueError(name+'_hash_mismatch')
    for s in packet['sources']:
        if digest(contained(run_dir,s['path'])) != s['sha256']:raise ValueError('source_hash_mismatch: '+s['id'])
    live = compile_index(knowledge_root/'catalog.json',knowledge_root/'merged/merge_plan.json')
    if canonical_hash(live) != canonical_hash(read(run_dir/'reference_index.json')):
        raise ValueError('knowledge_changed_prepare_new_revision')
    intake=read(run_dir/'intake.json');validate(intake,'intake')
    step=next(s for s in packet['sources'] if s['role']=='step')
    terms, selected=select(live,intake,step['sha256'])
    if packet['references'] != selected or packet['terms'] != terms:
        raise ValueError('retrieval_replay_mismatch')
    return packet, intake


def sections(text):
    matches=list(re.finditer(r'^## ([A-Za-z][A-Za-z0-9_-]*)\s+.*$',text,re.M))
    if len({m[1] for m in matches}) != len(matches):raise ValueError('duplicate_plan_section')
    return {m[1]:text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)] for i,m in enumerate(matches)}


def audit(run_dir: Path, review_path: Path, knowledge_root: Path):
    run_dir, review_path=Path(run_dir).resolve(),Path(review_path).resolve()
    packet,intake=verify_packet(run_dir,knowledge_root)
    review=read(review_path);validate(review,'review')
    if review['packet_sha256'] != digest(run_dir/'packet.json'):raise ValueError('review_packet_binding_mismatch')
    plan_path=(review_path.parent/review['plan_path']).resolve()
    body=plan_path.read_text('utf-8-sig');sec=sections(body)
    source_ids={s['id'] for s in packet['sources']}
    reqs=unique(intake['requirements'],'id');refs=unique(packet['references'],'id')
    rr=unique(review['requirement_reviews'],'requirement_id')
    dd=unique(review['reference_decisions'],'reference_id')
    errors=[]
    open_items=[dict(id=f'input_unknown_{i:03d}',reason=value)
                for i,value in enumerate(intake['known_unknowns'],1)]
    for label,expected,got in [('requirement',reqs,rr),('reference',refs,dd)]:
        for missing in sorted(set(expected)-set(got)):errors.append('unreviewed_'+label+': '+missing)
        for extra in sorted(set(got)-set(expected)):errors.append('unknown_'+label+': '+extra)

    def coverage(row, requirement_ids):
        check_evidence(row['evidence'],source_ids)
        text='\n'.join(sec.get(k,'') for k in row['plan_sections'])
        for k in row['plan_sections']:
            if k not in sec:errors.append('unknown_plan_section: '+k)
        for rid in requirement_ids:
            if rid not in reqs:errors.append('unknown_requirement: '+rid)
            elif not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(rid)+r'(?![A-Za-z0-9_-])',text):
                errors.append('requirement_not_in_cited_plan_section: '+rid)
        return text

    for rid,row in rr.items():
        coverage(row,[rid])
        if row['status']=='deferred':open_items.append(dict(id=rid,reason=row['reason']))
    for refid,row in dd.items():
        text=coverage(row,row['requirement_ids'])
        if refid not in refs:continue
        ref=refs[refid];status=row['disposition']
        allowed=['adopt','adapt','reject','defer'] if ref['category']=='family' else ['resolved','not_applicable','unresolved']
        if status not in allowed:errors.append('invalid_disposition_for_category: '+refid)
        candidate_ids={v['record']['id'] for v in ref['sources']}
        if not set(row['selected_source_ids']).issubset(candidate_ids):errors.append('unknown_selected_template: '+refid)
        if status in ['adopt','adapt']:
            if not row['selected_source_ids'] or not row['requirement_ids'] or refid not in text:
                errors.append('adoption_missing_source_requirement_or_plan_citation: '+refid)
        if status in ['defer','unresolved']:open_items.append(dict(id=refid,reason=row['reason']))
    for row in review['additional_findings']:
        check_evidence(row['evidence'],source_ids)
        open_items.append(dict(id=row['id'],reason=row['description']))
    result=dict(schema_version='aicnc.planning-reference-audit/0.1',
        status='incomplete' if errors else ('complete_with_open_items' if open_items else 'complete'),
        packet_sha256=digest(run_dir/'packet.json'),review_sha256=digest(review_path),plan_sha256=digest(plan_path),
        references_considered=len(refs),requirements_considered=len(reqs),
        adopted_families=sorted(k for k,v in dd.items() if v['disposition'] in ['adopt','adapt'] and k in refs),
        selected_template_ids=sorted({tid for row in dd.values() if row['disposition'] in ['adopt','adapt'] for tid in row['selected_source_ids']}),
        errors=errors,open_items=open_items,semantic_review_by='codex',
        automated_check_scope='source integrity, retrieval replay, disposition and declared requirement coverage; not engineering correctness',
        production_enabled=False,ready_for_cam_execution=False,simulation_performed=False)
    validate(result,'audit')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','audit'])
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--knowledge-root',type=Path,default=ROOT/'知识库/工艺经验库')
    p.add_argument('--intake',type=Path)
    p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    if a.action=='prepare':
        if not a.intake:p.error('prepare requires --intake')
        result=prepare(a.intake,a.run_dir,a.knowledge_root)
    else:
        if not a.review:p.error('audit requires --review')
        result=audit(a.run_dir,a.review,a.knowledge_root)
        output=a.output or a.run_dir/'audit.json'
        write_new(output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('status')=='incomplete' else 0


if __name__=='__main__':
    raise SystemExit(main())
