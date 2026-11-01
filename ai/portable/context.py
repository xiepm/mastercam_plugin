"""Append-only task evidence. References existing plans; this is not a CAM IR."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, shutil
from .common import ROOT, config, load, scoped, sha, token, write_new

STAGES = ('input', 'geometry', 'planning', 'native_project', 'toolpath', 'save_reopen',
          'material_simulation', 'gouge', 'holder_collision', 'fixture_collision',
          'machine_simulation', 'nc', 'nc_simulation', 'dimensions', 'production_release')
STATES = ('pending', 'running', 'pass', 'fail', 'unknown', 'not_applicable')

def validate(value, definition):
    from jsonschema import Draft202012Validator
    schema = load(ROOT/'ai/context/task.schema.json')
    Draft202012Validator({'$ref': '#/$defs/'+definition, '$defs': schema['$defs']}).validate(value)

def task_directory(c, task_id):
    return Path(c['workspace'])/'tasks'/token(task_id)

def create(task_id, source_path, goal, requirements, config_path=None):
    c = config(config_path)
    source = Path(source_path).resolve(strict=True)
    if source.suffix.lower() not in ('.step', '.stp', '.mcam') or not source.is_file():
        raise ValueError('Input must be a local STEP/STP/MCAM file')
    if not goal.strip():
        raise ValueError('Task goal is required')
    d = task_directory(c, task_id)
    value = {'schema_version': 'mastercam-agent-task/1.0', 'task_id': token(task_id),
             'created_at': datetime.now(timezone.utc).isoformat(), 'goal': goal,
             'source': {'path': 'input'+source.suffix.lower(), 'sha256': sha(source)},
             'requirements': requirements, 'production_released': False}
    validate(value, 'task')
    d.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, d/value['source']['path'])
    if sha(d/value['source']['path']) != value['source']['sha256']:
        raise ValueError('Source changed while it was copied; retain the incomplete task for diagnosis')
    write_new(d/'task.json', value)
    (d/'events').mkdir()
    return resume(task_id, config_path)

def checkpoint(task_id, event_id, stage, state, summary, artifacts=None, bindings=None,
               next_action='', config_path=None):
    c = config(config_path); d = task_directory(c, task_id)
    task = load(d/'task.json'); validate(task, 'task')
    if stage not in STAGES or state not in STATES:
        raise ValueError('Unknown stage/state')
    if stage == 'production_release' and state == 'pass':
        raise ValueError('This software package cannot grant production release')
    if not summary.strip():
        raise ValueError('An evidence summary is required')
    refs = []
    for name in artifacts or []:
        p = scoped(name, c, exists=True)
        if not p.is_relative_to(d):
            raise ValueError('Copy evidence into this task before referencing it')
        refs.append({'path': p.relative_to(d).as_posix(), 'sha256': sha(p)})
    if state == 'pass' and not refs:
        raise ValueError('A claimed pass requires actual evidence files')
    bound = {'source': task['source']['sha256']}
    for key, name in (bindings or {}).items():
        token(key)
        if key == 'source':
            raise ValueError('Source identity cannot be overridden')
        p = scoped(name, c, exists=True)
        if not p.is_relative_to(d):
            raise ValueError('Plan/resource bindings must be in this task')
        bound[key] = {'path': p.relative_to(d).as_posix(), 'sha256': sha(p)}
    event = {'schema_version': 'mastercam-agent-event/1.0', 'event_id': token(event_id),
             'stage': stage, 'state': state, 'summary': summary, 'artifacts': refs,
             'bindings': bound, 'next_action': next_action}
    validate(event, 'event')
    path = d/'events'/(token(event_id)+'.json')
    if path.exists():
        if load(path) != event:
            raise ValueError('Event ID was already used with different evidence')
    else:
        write_new(path, event)
    return resume(task_id, config_path)

def resume(task_id, config_path=None):
    c = config(config_path); d = task_directory(c, task_id)
    task = load(d/'task.json'); validate(task, 'task')
    statuses = {k: {'state': 'pending'} for k in STAGES}
    source = (d/task['source']['path']).resolve()
    source_ok = source.is_relative_to(d) and source.is_file() and sha(source) == task['source']['sha256']
    events = []
    for p in sorted((d/'events').glob('*.json'), key=lambda p: (p.stat().st_mtime_ns, p.name)):
        e = load(p); validate(e, 'event'); stale = []
        if not source_ok or e['bindings']['source'] != task['source']['sha256']:
            stale.append('source')
        for ref in [*e['artifacts'], *[v for k,v in e['bindings'].items() if k != 'source']]:
            path = (d/ref['path']).resolve()
            if not path.is_relative_to(d) or not path.is_file() or sha(path) != ref['sha256']:
                stale.append(ref['path'])
        effective = 'unknown' if stale else e['state']
        statuses[e['stage']] = {'state': effective, 'reported_state': e['state'],
                               'event_id': e['event_id'], 'summary': e['summary'],
                               'stale_references': stale, 'next_action': e['next_action']}
        events.append(e['event_id'])
    return {'task': task, 'directory': str(d), 'source_unchanged': source_ok,
            'stages': statuses, 'events': events, 'production_released': False,
            'note': 'States are evidence records, not an independent certification. Verify each referenced receipt.'}
