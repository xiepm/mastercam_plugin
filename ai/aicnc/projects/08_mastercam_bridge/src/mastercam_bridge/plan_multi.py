"""Multi-operation lowering/verification for the existing plan_simulation runner.

cam_plan 1.1 stays the planning contract. This is a bounded, explicitly bound
test adapter, not another planner, IR, STEP parser, or native execution engine.
"""
from pathlib import Path
import json, math
from jsonschema import Draft202012Validator
from .contour_smoke import digest, load, write_new
from . import plan_simulation as p

SCHEMA=p.ROOT/'schemas/mastercam_plan_multi.schema.json'
STRATEGIES={'contouring':'rectangular_external_contour','pocketing':'rectangular_pocket','drilling':'through_drilling'}
TYPES={'contouring':'ContourOperation','pocketing':'PocketOperation','drilling':'DrillOperation'}


def validate(value, definition):
    doc=load(SCHEMA)
    Draft202012Validator({'$ref':'#/$defs/'+definition,'$defs':doc['$defs']}).validate(value)


def compile_multi(plan_path, binding_path):
    plan_path,binding_path=Path(plan_path).resolve(),Path(binding_path).resolve()
    plan,b=load(plan_path),load(binding_path)
    Draft202012Validator(load(p.ROOT/'schemas/cam_plan.schema.json')).validate(plan)
    validate(b,'binding')
    def finite(value):
        if isinstance(value,float):p.require(math.isfinite(value),'Nonfinite plan/binding value')
        elif isinstance(value,dict):
            for x in value.values():finite(x)
        elif isinstance(value,list):
            for x in value:finite(x)
    finite(plan);finite(b)
    p.require(p.resolve_asset(binding_path.parent,b['plan'])==plan_path,'Wrong plan binding')
    p.require(plan['status'] not in {'draft','rejected'} and not plan['unplanned_features'],'Incomplete/rejected plan')
    p.require(plan['units']=={'length':'mm','angle':'deg','feed_rate':'mm/min'},'Metric plan required')
    p.require(len(plan['setups'])==1,'Multiple setups not yet supported')
    setup=plan['setups'][0]
    p.require(setup['setup_id']==b['setup_id'] and setup['sequence']==1,'Setup identity')
    p.require([setup['work_coordinate_system'][k] for k in ('origin','x_axis','y_axis','z_axis')]==[[0,0,0],[1,0,0],[0,1,0],[0,0,1]] and setup['machining_direction']==[0,0,-1],'Identity top WCS required')
    fp=p.resolve_asset(plan_path.parent,plan['source_features']);cp=p.resolve_asset(plan_path.parent,plan['manufacturing_context'])
    features,context=load(fp),load(cp)
    step=p.resolve_asset(fp.parent,{'path':features['source']['step_file'],'sha256':features['source']['step_sha256'].lower()})
    target=p.resolve_asset(binding_path.parent,b['target'])
    p.require(features['part_id']==plan['part_id'] and features['face_id_namespace']==plan['source_features']['face_id_namespace'],'Feature identity')
    p.require(context['context_id']==plan['manufacturing_context']['context_id'],'Context identity')
    p.require(setup.get('fixture_id')==context['fixture']['fixture_id'],'Fixture binding')
    p.require(setup['stock']['type']=='box' and setup['stock']['dimensions']==context['stock']['dimensions'],'Stock context')
    stock=b['stock'];lo,hi=stock['min_mm'],stock['max_mm']
    p.require([hi[i]-lo[i] for i in range(3)]==setup['stock']['dimensions'] and hi[2]==0 and lo[2]<0,'Stock bounds')
    ops=setup['operations'];bindings=b['operations']
    p.require(2<=len(ops)<=64 and len(ops)==len(bindings),'Full operation coverage required')
    p.require([o['sequence'] for o in ops]==list(range(1,len(ops)+1)),'Contiguous ordered sequence required')
    p.require(len({o['operation_id'] for o in ops})==len(ops),'Duplicate operation ID')
    p.require([o['operation_id'] for o in ops]==[x['operation_id'] for x in bindings],'Binding order/coverage')
    source_features={f['instance_id']:f for f in features['features']}
    p.require(len(source_features)==len(features['features']),'Duplicate source features')
    source_faces={f['face_id'] for f in features['faces']}
    tool_numbers={};used_numbers={};seen=[];lowered=[]
    for op,bind in zip(ops,bindings):
        kind=op['operation_type'];g=bind['geometry'];a=bind['tool_assembly'];cut=op['cutting_parameters'];tool=op['tool']
        p.require(STRATEGIES.get(kind)==op['strategy'],'Unsupported operation/strategy: '+op['operation_id'])
        p.require(op['status'] in {'planned','needs_review','approved'},'Blocked operation')
        p.require(op['feature_instance_ids']==bind['feature_instance_ids'] and op['face_ids']==bind['face_ids'],'Feature/Face binding')
        p.require(len(op['feature_instance_ids'])==1,'One feature per bound operation')
        fid=op['feature_instance_ids'][0];p.require(fid in source_features,'Unknown feature')
        feature=source_features[fid];seen.append(fid)
        p.require(feature['canonical_label']['family']=={'contouring':'step','pocketing':'pocket','drilling':'hole'}[kind],'Feature family mismatch')
        p.require(set(op['face_ids'])==set(feature['topology']['face_ids']) and set(op['face_ids'])<=source_faces,'Source face membership')
        matches=[x for x in context['tools'] if x['tool_id']==tool['tool_id']]
        p.require(len(matches)==1 and all(matches[0].get(k)==v for k,v in tool.items()),'Tool differs from context')
        p.require(tool['tool_type']==('drill' if kind=='drilling' else 'flat_end_mill'),'Tool type mismatch')
        p.require(tool.get('corner_radius',0)==0 and tool.get('stickout')==a['length_mm'],'Tool geometry mismatch')
        p.require(a['flute_length_mm']<=a['shoulder_length_mm']<=a['length_mm'] and a['holder_diameter_mm']>tool['diameter'],'Tool assembly')
        p.require(a['flute_length_mm']>=abs(g['depth_mm']),'Insufficient cutting length')
        p.require(set(cut)<= {'spindle_speed_rpm','feed_rate','plunge_rate','coolant','stepdown','stepover'},'Unsupported cutting parameters')
        p.require(cut['coolant']=='off' and cut.get('plunge_rate',0)>0 and cut['spindle_speed_rpm']==int(cut['spindle_speed_rpm']),'Cutting settings')
        p.require(op['safety']=={'clearance':10,'retract':5,'stock_to_leave_radial':0,'stock_to_leave_axial':0},'Unsupported linking/allowance')
        p.require(g['top_mm']==0 and g['depth_mm']<0,'Top/depth')
        expected_shape='points' if kind=='drilling' else 'rectangle'
        p.require(g['shape']==expected_shape,'Geometry type')
        measures={x['name']:x['value'] for x in feature['geometry']['measurements']}
        if kind=='drilling':
            p.require(30<=a['tip_angle_deg']<=170,'Unsupported drill tip angle')
            p.require(measures.get('diameter')==tool['diameter'] and len(g['points_mm'])==1,'Drill diameter/points')
            p.require(g['points_mm'][0]==feature['placement']['origin'],'Drill origin binding')
            tip=tool['diameter']/2/math.tan(math.radians(a['tip_angle_deg']/2))
            p.require(g['depth_mm']<=lo[2]-tip and g['depth_mm']>=lo[2]-tip-3,'Through drill tip extension')
            p.require(set(cut)<= {'spindle_speed_rpm','feed_rate','plunge_rate','coolant'},'Drilling cut keys')
        else:
            p.require(a['tip_angle_deg']==0,'Flat mill tip angle')
            p.require(measures.get('depth')==-g['depth_mm'] and measures.get('width')==min(g['width_mm'],g['height_mm']),'Feature dimensions')
            p.require(g['origin_mm']==feature['placement']['origin'],'Rectangle origin binding')
            p.require(cut.get('stepdown')==-g['depth_mm'],'Single axial pass required')
            p.require(g['depth_mm']>lo[2],'Bottom would leave stock')
            if kind=='pocketing':
                p.require(tool['diameter']<min(g['width_mm'],g['height_mm']) and 0<cut.get('stepover',0)<=tool['diameter']/2,'Pocket stepover/tool')
            else:
                p.require('stepover' not in cut,'Contour stepover unsupported')
        number=a['number'];identity=(tool,a)
        p.require(number not in used_numbers or used_numbers[number]==identity,'Conflicting tool number')
        p.require(tool['tool_id'] not in tool_numbers or tool_numbers[tool['tool_id']]==number,'Tool identity renumbered')
        used_numbers[number]=identity;tool_numbers[tool['tool_id']]=number
        lowered.append(dict(operation_id=op['operation_id'],sequence=op['sequence'],operation_type=kind,
            feature_instance_ids=op['feature_instance_ids'],face_ids=op['face_ids'],geometry=g,tool=dict(tool,**a),
            cutting_parameters=cut,safety=op['safety']))
    p.require(set(seen)==set(source_features) and len(seen)==len(set(seen)),'Source feature coverage')
    return dict(operations=lowered,stock=stock,acceptance=b['acceptance'],
        plan_path=str(plan_path),plan_sha256=digest(plan_path),binding_path=str(binding_path),binding_sha256=digest(binding_path),
        target_path=str(target),target_sha256=digest(target),step_path=str(step),step_sha256=digest(step))


def reopen_material(directory):
    """Use the shared P01 faceted kernel, no alignment, welding or mesh rewriting."""
    boot='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from cad_core.faceted_material_difference import solid,compare,digest
a,b,out=map(Path,sys.argv[2:])
left,_=solid(json.loads(a.read_text())['polygons'],2000000)
right,_=solid(json.loads(b.read_text())['polygons'],2000000)
r=compare(left,right)
r.update(before_sha256=digest(a),after_sha256=digest(b),alignment_performed=False,geometry_modified=False)
with out.open('x') as f:json.dump(r,f,indent=2)
'''
    p.command(['wsl.exe','-d','Ubuntu-22.04','--','/home/xpm/.local/share/micromamba/envs/aicnc-aagnet-cpu/bin/python','-c',boot,
        p.wsl_path(p.ROOT/'projects/01_cad_core/src'),p.wsl_path(directory/'before-ipw.json'),p.wsl_path(directory/'after-ipw.json'),p.wsl_path(directory/'reopen-material.json')],60)


def motion_stream_valid(motion, stream, operation_count):
    if len(stream)!=operation_count or motion['operation_count']!=operation_count:return False
    offset=0
    for row in stream:
        if row.get('IsComplete') is not True or row.get('Count',0)<=0 or row.get('NumMovesBefore')!=offset:return False
        offset+=row['Count']
    pos=motion.get('position')
    return bool(pos and motion['completed'] and motion['input_complete'] and not motion['is_running'] and not motion['is_busy'] and offset==motion['num_moves'] and pos['Index']==offset-1 and pos['OperationIndex']==operation_count-1 and pos['MoveIndex']==stream[-1]['Count']-1)


def stream_identity_valid(stream, native_operations):
    """Bind each simulator operation to the persisted native operation and tool."""
    if len(stream)!=len(native_operations):return False
    tool_ids={};reverse_ids={}
    for row,op in zip(stream,native_operations):
        info=row.get('operation_info',{});tool=row.get('tool_metadata',{})
        if info.get('OperationNo')!=op['operation_id'] or row.get('has_tool') is not True:return False
        if tool.get('ToolDiameter')!=op['tool']['diameter_mm'] or tool.get('ToolProfileIsEmpty') is not False:return False
        number=op['tool']['number'];native_id=tool.get('ToolId')
        if not isinstance(native_id,int) or native_id<0:return False
        if tool_ids.setdefault(number,native_id)!=native_id or reverse_ids.setdefault(native_id,number)!=number:return False
    return True


def verify_multi(directory):
    directory=Path(directory);r=load(directory/'request.json');manifest=load(directory/'source_manifest.json');errors=[]
    def check(ok,message):
        if not ok:errors.append(message)
    validate(r,'native_request')
    compiled=compile_multi(r['plan_path'],r['binding_path'])
    comparable=json.loads(json.dumps(r))
    for op in comparable['operations']:op.pop('operation_name',None)
    check(all(comparable.get(k)==v for k,v in compiled.items()),'request recompilation')
    check(digest(directory/'request.json')==manifest['request_sha256'],'request SHA')
    for name,expected in manifest['source_sha256'].items():
        if name=='faceted_material_difference.py':path=p.ROOT/'projects/01_cad_core/src/cad_core'/name
        elif name.endswith('.py'):path=Path(__file__).with_name(name)
        else:path=p.NATIVE/name
        check(digest(path)==expected and digest(directory/'source'/name)==expected,'source drift: '+name)
    created,a,b=[load(directory/(name+'.json')) for name in ('create','before','after')]
    check(a['pid']!=b['pid'],'fresh native process')
    check(created['snapshot']==a['snapshot']==b['snapshot'],'native persistence')
    check(created['model_sha256']==a['model_sha256']==b['model_sha256']==digest(Path(r['model_path'])),'native file persistence')
    for receipt in (created,a,b):
        check(receipt['ok'] is True and receipt['request_sha256']==digest(directory/'request.json'),'native receipt identity')
        snap=receipt['snapshot'];actual=snap['operations']
        check(len(actual)==len(r['operations']) and snap['operation_count']==len(actual),'operation coverage')
        for op,expected in zip(actual,r['operations']):
            prefix=expected['operation_id']+': '
            check(op['operation_name']==expected['operation_name'] and op['operation_type']=='Mastercam.Operations.'+TYPES[expected['operation_type']] and op['dirty'] is False,prefix+'native type/name/order')
            for key,ek in [('depth_mm','depth_mm'),('top_stock_mm','top_mm')]:check(op[key]==expected['geometry'][ek],prefix+key)
            for key,ek in [('feed_mm_min','feed_rate'),('spindle_rpm','spindle_speed_rpm'),('plunge_mm_min','plunge_rate')]:check(op[key]==expected['cutting_parameters'][ek],prefix+key)
            check(op['coolant']=='COOL_OFF' and op['clearance_mm']==10 and op['retract_mm']==5,prefix+'linking/coolant')
            for key,ek in [('number','number'),('diameter_mm','diameter'),('length_mm','length_mm'),('flute_length_mm','flute_length_mm'),('shoulder_length_mm','shoulder_length_mm'),('holder_diameter_mm','holder_diameter_mm'),('holder_length_mm','holder_length_mm'),('tip_angle_deg','tip_angle_deg')]:
                check(op['tool'][key]==expected['tool'][ek],prefix+'tool '+key)
            check(op['length_offset']==expected['tool']['number'] and op['diameter_offset']==expected['tool']['number'],prefix+'offsets')
            check(op['path']['data_valid'] and op['path']['travel_valid'] and op['path']['cycle_time_seconds']>0,prefix+'nonempty path')
            g=expected['geometry']
            if g['shape']=='points':check(op['drill_points']==g['points_mm'] and op['drill_cycle']=='Drill',prefix+'drill binding')
            else:
                check(op['chain']['closed'] and op['chain']['curves_count']==4 and abs(op['chain']['area_mm2']-g['width_mm']*g['height_mm'])<1e-8,prefix+'chain geometry')
            if expected['operation_type']=='pocketing':check(op['pocket']['stepover_mm']==expected['cutting_parameters']['stepover'] and op['pocket']['wall_stock_mm']==0 and op['pocket']['floor_stock_mm']==0,prefix+'pocket settings')
        lo,hi=r['stock']['min_mm'],r['stock']['max_mm'];stock=snap['stock']
        check(stock['StockSize']==dict(zip('xyz',[hi[i]-lo[i] for i in range(3)])),'stock dimensions')
        check(stock['StockOrigin']==dict(x=(lo[0]+hi[0])/2,y=(lo[1]+hi[1])/2,z=hi[2]) and stock['StockPlaneID']==1,'stock origin/frame')
    check(a['regeneration_performed'] is False and b['regeneration_performed'] is False,'reopen regenerated')
    for key in ('host_version','api_version','api_sha256','machine_sha256'):check(a[key]==b[key],key+' changed')
    sims=[];meshes=[];material=[]
    for name,host in [('before',a),('after',b)]:
        audit=load(directory/(name+'-native-exceptions.json'))
        check(audit['passed'] is True and not audit['exceptions'],'native exception log')
        s=load(directory/(name+'-export.json'));sims.append(s);motion=s['motion']
        check(s['ok'] is True and s['pid']==host['pid'] and s['model_path']==r['model_path'],'simulation identity')
        check(motion['completed'] and motion['input_complete'] and not motion['is_running'] and not motion['is_busy'] and motion['num_moves']>0 and motion['position']['Index']==motion['num_moves']-1,'complete motion')
        check(motion['operation_count']==len(r['operations']),'all operations simulated')
        check(motion_stream_valid(motion,s['operation_stream'],len(r['operations'])),'per-operation motion coverage/terminal position')
        check(stream_identity_valid(s['operation_stream'],host['snapshot']['operations']),'simulator/native operation and tool binding')
        check(s['target_sha256']==r['target_sha256'] and s['checks']=={'enabled':True,'between_moves':True},'target/check settings')
        check(all(s['collision_options'].get(k) is True for k in ('CheckToolAgainstStock','CheckStockAgainstMillingHolder','CheckStockAgainstMillingShank','CheckStockAgainstMillingShoulder')),'collision options')
        check(not s['report_groups'],'native collision events')
        check(len(s['verifiers'])==1,'verifier cardinality')
        v=s['verifiers'][0]
        check(v['target_count']==1 and not v['gouges'] and not v['excess'],'native gouge/excess')
        check(v['gouge_threshold_mm']==-.1 and v['excess_threshold_mm']==.1 and 0<v['precision_mm']<=.02,'native resolution')
        check(v['thread_limit']==2,'native worker limit')
        check(0<v['collision_tolerance_mm']<=.1524 and 0<v['holder_tolerance_mm']<=.1524,'collision tolerance')
        for part in ('holder','shaft','arbor'):check(v[part]['IsCollisionChecked'] and not v[part]['RapidCollisionReportSuppressed'],'tool check '+part)
        check(v['current_volume_mm3']<v['initial_volume_mm3'],'material removal')
        check(s['bridge_sha256']==load(directory/'helper.json')['sha256']==digest(Path(load(directory/'helper.json')['path'])),'helper identity')
        mat=load(directory/(name+'-material.json'));material.append(mat)
        check(mat['status']=='measured' and mat['missing_material_mm3']<=r['acceptance']['material_difference_mm3'] and mat['extra_material_mm3']<=r['acceptance']['material_difference_mm3'],'P01 target/IPW difference')
        check(mat['inputs']['target']['sha256'].lower()==r['step_sha256'] and mat['inputs']['mesh']['sha256'].lower()==digest(directory/(name+'-ipw.json')),'P01 input hashes')
        check(load(directory/(name+'-ipw.json'))['source_stl_sha256']==digest(directory/(name+'-ipw.stl')),'native STL provenance')
        meshes.append(p.mesh_stats(directory/(name+'-ipw.stl')))
    if not (directory/'reopen-material.json').exists():reopen_material(directory)
    rep=load(directory/'reopen-material.json')
    check(rep['before_sha256'].lower()==digest(directory/'before-ipw.json') and rep['after_sha256'].lower()==digest(directory/'after-ipw.json'),'reopen mesh hashes')
    check(rep['missing_material_mm3']<=r['acceptance']['reopen_difference_mm3'] and rep['extra_material_mm3']<=r['acceptance']['reopen_difference_mm3'],'reopen geometric difference')
    for key in ('motion','operation_stream','checks','collision_options','stock_to_world','report_groups'):check(sims[0][key]==sims[1][key],key+' changed on reopen')
    return dict(schema_version='aicnc.mastercam-plan-simulation-verification/0.2',passed=not errors,errors=errors,
        model_path=r['model_path'],model_sha256=digest(Path(r['model_path'])),plan_sha256=r['plan_sha256'],fresh_pids=[a['pid'],b['pid']],
        operation_count=len(r['operations']),tool_count=len({o['tool']['number'] for o in r['operations']}),meshes=meshes,
        material_differences=material,reopen_material_difference=rep,acceptance=r['acceptance'],
        scope='single setup; rectangular external contour, rectangular rounded-floor pocket and through drill; native tool assembly versus stock',
        production_released=False,postprocessing_performed=False,machine_simulation_verified=False)
