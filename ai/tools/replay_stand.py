"""Private STEP -> P01/P07 -> native 2-setup MCAM -> Verify -> two cold replays.

This source-bound acceptance profile reuses P08; it is not arbitrary STEP CAM.
Requires licensed Mastercam 2027, installed MCP runtime, and the pinned WSL P01
environment. Failed/unknown mutations are recorded and never automatically retried.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_smoke as host
from portable.common import ROOT, config, scoped, load, write_new, sha
from mastercam_bridge import plan_simulation as p, stand_replay as stand
from portable import context


def contract(value, definition):
    schema=load(ROOT/'ai/schemas/stand-replay.schema.json')
    p.Draft202012Validator(dict(schema, **{'$ref':'#/$defs/'+definition})).validate(value)


def checkpoint(a,d,stage,artifacts):
    if not a.task_id:return
    context.checkpoint(a.task_id,'stand-'+stage,stage,'pass',
        'Source-bound stand software replay; inspect the attached native evidence',
        [str(d/x) for x in artifacts],{'plan':str(d/'cam_plan.json'),'model':str(d/stand.MODEL)},
        'Review remaining physical-fixture, machine, dimensional and NC requirements',a.config)


def linux_path(path, distro):
    return subprocess.check_output(['wsl.exe','-d',distro,'--','wslpath','-a','-u',Path(path).resolve().as_posix()],
                                   stderr=subprocess.PIPE).decode('utf-8').strip()


def p01(a, script, paths, log):
    cmd = ['wsl.exe','-d',a.wsl_distro,'--',a.p01_python,linux_path(script,a.wsl_distro)]
    cmd += [linux_path(path,a.wsl_distro) for path in paths]
    with Path(log).open('xb') as out:
        result = subprocess.run(cmd, stdout=out, stderr=out, timeout=600)
    if result.returncode:
        raise RuntimeError('P01 failed; see '+str(log))


def call(c, tool, args):
    with p.McpConnection() as client:
        host.CLIENT = client
        try:
            return host.invoke(tool,args,c)
        finally:
            host.CLIENT = None


def wait_host(c):
    with p.McpConnection() as client:
        host.CLIENT = client
        try:
            return host.ready(c)
        finally:
            host.CLIENT = None


def close_session(d, label, pid, c, original_hash):
    # Native Verify/readback may dirty display state. Save a separate inspection
    # session so the verified on-disk MCAM is never silently overwritten.
    copy = d/(label+'-inspection-session.mcam')
    write_new(d/(label+'-inspection-save.json'), call(c,'mastercam_save_as',{'output_path':str(copy)}))
    if sha(d/stand.MODEL) != original_hash:
        raise RuntimeError('Verified MCAM changed during session cleanup')
    with p.McpConnection() as client:
        host.CLIENT = client
        try:
            host.close_owned(pid,copy,c)
        finally:
            host.CLIENT = None


def replay(a):
    c = config(a.config)
    os.environ['MC_PLUGIN_AI_CONFIG'] = str(Path(a.config).resolve())
    d = scoped(a.directory,c)
    stage = a.action
    try:
        if a.action=='build':
            if not (a.source and a.machine and a.p01_python):raise ValueError('build requires --source, --machine and --p01-python')
            source=Path(a.source).resolve();machine=Path(a.machine).resolve()
            if sha(source)!=stand.SOURCE_SHA256:raise ValueError('Unsupported STEP hash; do not apply this profile to a new part')
            if not machine.is_file() or machine.name!='MILL 3 - AXIS VMC MM.mcam-mmd':raise ValueError('Installed metric 3-axis definition required')
            if d.exists():raise FileExistsError('Fresh build directory required: '+str(d))
            if a.task_id:
                task_dir=context.task_directory(c,a.task_id).resolve()
                if not d.is_relative_to(task_dir) or d==task_dir:raise ValueError('--directory must be a new child of workspace/tasks/<task-id>')
                if not task_dir.exists():context.create(a.task_id,str(source),'STEP to two-setup nine-operation native software acceptance',{'simulation_only':True},a.config)
                if load(task_dir/'task.json')['source']['sha256']!=sha(source):raise ValueError('Task source differs')
            d.mkdir(parents=True)
            shutil.copy2(source,d/'source.step')
            request=dict(schema_version='aicnc.mastercam-stand-replay-request/0.1',source_sha256=sha(source),
                machine_sha256=sha(machine),p01_python=a.p01_python,wsl_distro=a.wsl_distro,
                source_manifest_sha256=sha(ROOT/'ai/aicnc/source-manifest.json'),
                production_released=False,model_inference_used=False,task_id=a.task_id)
            contract(request,'request');write_new(d/'replay-request.json',request)
            stage='prepare'
            p01(a,p.ROOT/'projects/08_mastercam_bridge/tools/prepare_stand_trial.py',[d],d/'prepare.log')
            p.validate_bound_stand_2027(d)
            print('P01/P07 prepared: 2 setups, 9 operations; no neural inference',flush=True)
            stage='import'
            started=host.launch_desktop(c,str(d/'source.step'));write_new(d/'initial-launch.json',started)
            imported=wait_host(c);write_new(d/'import-readback.json',imported)
            fields=dict(line.split('=',1) for line in imported['native_readback'].splitlines() if '=' in line)
            if fields.get('metric')!='True' or fields.get('geometry_count')!='1':raise ValueError('Expected one metric solid')
            write_new(d/'import-save.json',call(c,'mastercam_save_as',{'output_path':str(d/'source.mcam')}))
            stage='create';p.execute_bound_stand_2027(d,'generated','create',native_only=True)
            stage='setup';stand.configure(d,machine)
            built=stand.readback(d,'build')
            prepared=dict(status='needs_native_ui_label_commit',pid=started['pid'],model_sha256=sha(d/stand.MODEL),
                          request_sha256=sha(d/'replay-request.json'),readback_sha256=sha(d/'build-readback.json'))
            write_new(d/'prepared.json',prepared)
            print('NEXT: In native UI rename BOTH view-sheet tabs to 装夹1_正面_G54 / 装夹2_翻面_G55 and Enter. Do NOT use Ctrl+S; verify saves through MCP. Exit 20 is this expected UI checkpoint.',flush=True)
            return 20
        # Verification never repeats build. UI naming is the only allowed
        # change at this boundary; compare all captured manufacturing fields.
        if (d/'failure.json').exists():raise ValueError('Failed run needs investigation; do not automatically replay')
        prepared=load(d/'prepared.json');request=load(d/'replay-request.json')
        contract(request,'request')
        if sha(d/'replay-request.json')!=prepared['request_sha256'] or sha(d/'build-readback.json')!=prepared['readback_sha256']:raise ValueError('Prepared evidence changed')
        if sha(ROOT/'ai/aicnc/source-manifest.json')!=request['source_manifest_sha256']:raise ValueError('Source package changed between phases')
        a.p01_python=request['p01_python'];a.wsl_distro=request['wsl_distro'];a.task_id=request['task_id']
        p.validate_bound_stand_2027(d)
        built=load(d/'build-readback.json')
        stand.native(d,'ui-save','aicnc_stand_save_views_2027.csx',
                     dict(MODEL=str(d/stand.MODEL),MODEL_SHA=sha(d/stand.MODEL)))
        initial=stand.readback(d,'initial')
        if initial['pid']!=prepared['pid'] or stand.stable_readback(initial)!=stand.stable_readback(built):raise ValueError('Prepared host or manufacturing state changed')
        started=dict(pid=initial['pid']);model_hash=sha(d/stand.MODEL)
        if initial['model_sha256']!=model_hash:raise ValueError('UI save still pending')
        write_new(d/'ui-commit.json',dict(required=True,model_before=prepared['model_sha256'],model_after=model_hash,
                                       native_names=[v['name'] for v in initial['view_sheets']],cold_persistence_verified=False))
        for stage,artifacts in [('geometry',['cad-summary.json']),('planning',['cam_plan.json']),
                                ('native_project',['initial-readback.json']),('toolpath',['initial-readback.json'])]:
            checkpoint(a,d,stage,artifacts)
        for label in ('initial','cold1','cold2'):
            stage = label+'-readback'
            if label != 'initial':
                started = host.launch_desktop(c,str(d/stand.MODEL))
                write_new(d/(label+'-launch.json'),started)
                wait_host(c)
            readback = initial if label=='initial' else stand.readback(d,label)
            if readback['pid'] != started['pid'] or readback['model_sha256'] != model_hash:
                raise ValueError('Host/model ownership changed')
            stage = label+'-simulation'
            p.execute_bound_stand_2027(d,label,'simulate',model_name=stand.MODEL,close_simulator=True)
            stage = label+'-close'
            close_session(d,label,started['pid'],c,model_hash)
            print(label+': native Verify complete; owned process closed',flush=True)
        stage = 'compare'
        result = stand.verify_replays(d)
        compare = p.ROOT/'projects/08_mastercam_bridge/tools/compare_simulation_stls.py'
        for label in ('initial','cold1','cold2'):
            p01(a,compare,[d/'target.stl',d/(label+'-ipw.stl'),d/(label+'-material.json')],d/(label+'-material.log'))
        for label in ('cold1','cold2'):
            output = d/(label+'-equivalence.json')
            p01(a,compare,[d/'initial-ipw.stl',d/(label+'-ipw.stl'),output],d/(label+'-equivalence.log'))
            equivalent = load(output)
            # Byte identity above is stronger than geometric equivalence. Keep
            # the independent P01 closed-mesh comparison as additional evidence.
            result[label+'_material_equivalence'] = equivalent['volumes']
        result.update(schema_version='aicnc.mastercam-stand-replay/0.1',
                      source_sha256=sha(d/'source.step'), source_manifest_sha256=sha(ROOT/'ai/aicnc/source-manifest.json'),
                      initial_material_difference=load(d/'initial-material.json')['volumes'],
                      evidence={q.name:sha(q) for q in sorted(d.glob('*.json'))},
                      another_physical_computer_tested=False,native_ui_label_commit_required=True)
        contract(result,'acceptance')
        write_new(d/'acceptance.json',result)
        for stage in ('save_reopen','material_simulation','gouge','holder_collision'):
            checkpoint(a,d,stage,['acceptance.json','initial-export.json','cold1-export.json','cold2-export.json'])
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return 0
    except Exception as e:
        failure=d/'failure.json'
        if d.is_dir() and not failure.exists():
            write_new(failure,dict(passed=False,stage=stage,error=str(e),traceback=traceback.format_exc(),
                                  native_outcome_requires_inspection=True,automatic_retry=False))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['build','verify'])
    parser.add_argument('--source')
    parser.add_argument('--directory',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--machine')
    parser.add_argument('--task-id',default='')
    parser.add_argument('--wsl-distro',default='Ubuntu-22.04')
    parser.add_argument('--p01-python',help='Absolute Linux Python path from install_p01.py')
    return replay(parser.parse_args())


if __name__=='__main__':
    raise SystemExit(main())
