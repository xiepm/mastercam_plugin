"""Replay support for the hash-bound stand using the existing P08 executor.

Host lifecycle and P01 environment selection belong to the portable adapter.
These functions do not infer features, release NC, or implement another IR.
"""
from pathlib import Path
from . import plan_simulation as p

MODEL = 'stand-3axis-2setups.mcam'
SOURCE_SHA256 = '68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429'


def native(directory, label, template, values):
    d = Path(directory)
    receipt = d / (label + '.json')
    script = d / (label + '.csx')
    p.require(not receipt.exists() and not script.exists(), 'Phase already attempted; inspect its outcome before any new action')
    p.render(p.NATIVE / template, dict(values, RECEIPT=str(receipt)), script)
    with p.McpConnection() as client:
        p._client = client
        try:
            return p.compiled_script(d, label, script, receipt, net10=True)
        finally:
            p._client = None


def configure(directory, machine):
    d = Path(directory); machine = Path(machine).resolve()
    binding = dict(schema_version='aicnc.mastercam-setup-replay-request/0.1',
                   source_model=str(d/'stand-2setup.mcam'), source_model_sha256=p.digest(d/'stand-2setup.mcam'),
                   machine_definition=str(machine), machine_sha256=p.digest(machine))
    p.Draft202012Validator(p.load(p.ROOT/'schemas/mastercam_setup_replay.schema.json')).validate(binding)
    p.write_new(d/'setup-replay.json', binding)
    native(d, 'setup-apply', 'aicnc_stand_setups_2027.csx', dict(ROOT=str(d), MODE='apply'))
    native(d, 'clearance-apply', 'aicnc_stand_return_point_2027.csx',
           dict(MODEL=str(d/MODEL), MODEL_SHA=p.digest(d/MODEL), CLEARANCE_MM=5))


def readback(directory, label):
    d = Path(directory)
    result = native(d, label+'-readback', 'aicnc_stand_setups_2027.csx', dict(ROOT=str(d), MODE='read'))
    p.require(len(result['operations']) == 9 and len(result['view_sheets']) == 2, 'Setup coverage changed')
    for i, op in enumerate(result['operations']):
        top = i < 3
        p.require(op['clearance'] == op['retract'] == 5 and op['feed_plane'] == 2 and op['top'] == 0 and op['depth'] <= 0, 'Setup-local heights changed')
        p.require(op['wcs']['x'] == [1,0,0] and op['wcs']['y'] == [0,1 if top else -1,0] and op['wcs']['z'] == [0,0,1 if top else -1], 'Setup axes changed')
        p.require(op['wcs']['work_offset'] == (0 if top else 1), 'Work offset changed')
        p.require(op['home_enabled'] and op['home'] == [0,0,15 if top else -5], 'Local return point changed')
        p.require(op['tool_assembly']['length'] == 40 and op['tool_assembly']['holder_diameter'] == 20 and op['tool_assembly']['holder_length'] == 40, 'Tool assembly changed')
    for i, sheet in enumerate(result['view_sheets']):
        plane = result['operations'][0 if i == 0 else 3]['wcs']['id']
        p.require(sheet['has_bookmark'] and all(sheet[k] == plane for k in ('wcs_id','tool_plane_id','construction_plane_id','graphics_plane_id')), 'Setup view changed')
    return result


def stable_readback(value):
    result = {k:value[k] for k in ('machine_name','stock','operations','view_sheets')}
    result['machine_name'] = str(result['machine_name']).replace('/', chr(92)).casefold()
    return result


def verify_replays(directory, labels=('initial','cold1','cold2')):
    d = Path(directory)
    states = [p.load(d/(label+'-readback.json')) for label in labels]
    finals = [p.load(d/(label+'-export.json')) for label in labels]
    model_hash = p.digest(d/MODEL)
    p.require(len({s['pid'] for s in states}) == len(labels), 'Cold replay must use distinct processes')
    p.require(all(s['model_sha256'] == model_hash for s in states), 'MCAM changed after save')
    p.require(all(stable_readback(s) == stable_readback(states[0]) for s in states), 'Persisted parameters changed')
    for state, final in zip(states, finals):
        p.validate_bound_stand_simulation(final)
        p.require(final['pid'] == state['pid'] and final['model_path'] == str(d/MODEL), 'Simulation provenance mismatch')
        p.require(final['target_sha256'] == p.digest(d/'target.stl'), 'Target changed')
    hashes = [p.digest(d/(label+'-ipw.stl')) for label in labels]
    p.require(len(set(hashes)) == 1, 'Reopened material result differs')
    for final in finals[1:]:
        p.require(all(final[k] == finals[0][k] for k in ('checks','quality_policy','collision_options','stock_to_world')), 'Simulation settings changed')
    return dict(passed=True, model_sha256=model_hash, ipw_sha256=hashes[0], fresh_pids=[s['pid'] for s in states],
                setups=2, operations=9, moves=233, identical_native_parameters=True, identical_ipw_bytes=True,
                native_gouges=0, native_excess=0, native_collision_reports=0,
                deviation_threshold_mm=0.02, assembly_collision_tolerance_mm=0.02,
                actual_resolution_mm=finals[0]['verifiers'][0]['precision_mm'],
                simulation_settings_and_target_reapplied=True, production_released=False,
                machine_kinematics_verified=False, physical_fixtures_verified=False, unseen_STEP_supported=False,
                feature_semantics='source-bound Agent-authored; no AAGNet inference',
                plan_mapping='P07 cam_plan 1.1 retained; P08 records setup-local G54/G55 and 5 mm clearance mapping')
