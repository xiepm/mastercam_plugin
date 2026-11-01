"""Source-bound user-part trial: shared P01 import and unchanged P07 cam_plan builder.

Explicit feature interpretation for this STEP only; no model prediction or
general feature-recognition rule is claimed. All resources are simulation-only.
"""
from pathlib import Path
import copy, hashlib, json, math, struct, sys

ROOT = Path(__file__).resolve().parents[3]
for project in ('01_cad_core', '07_capp_planner'):
    sys.path.insert(0, str(ROOT / 'projects' / project / 'src'))
from cad_core.core import CadDocument
from cad_core.faceted_material_difference import triangulate
from cad_core.constructive_templates import volume
from capp_planner.planner import build_cam_plan

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)

def main():
    out = Path(sys.argv[1])
    source = out / 'source.step'
    assert digest(source) == '68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429'
    cad = CadDocument.from_step(source)
    records = {f['face_id']: f for f in cad.face_records}
    assert len(records) == 37 and cad.summary()['diagnostics']['brep_valid']
    assert records['F0008']['analytic']['radius'] == 3.1
    assert records['F0011']['analytic']['radius'] == 5.125
    assert records['F0012']['centroid'][2] == 6.4
    for n in (14, 16, 18, 20):
        assert records[f'F{n:04}']['analytic']['radius'] == 1.025
    write(out/'cad-summary.json',cad.summary())
    triangles = triangulate(cad.body, .002, 200000)
    facets=[]
    zero_area=0
    for a,b,c in triangles:
        u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n))
        if length == 0:
            zero_area += 1
            continue
        facets.append(struct.pack('<12fH', *[x/length for x in n], *a,*b,*c,0))
    raw = b'AICNC original STEP tessellated by shared P01, PCS millimetres'.ljust(80, b'\0') + struct.pack('<I',len(facets)) + b''.join(facets)
    (out/'target.stl').write_bytes(raw)
    f=json.loads((ROOT/'schemas/examples/features.example.json').read_text())
    template=copy.deepcopy(f['features'][0])
    f.update(part_id='2-200x-stand_1-original', source=cad.summary()['source'],
             face_id_namespace=cad.face_id_namespace, faces=cad.features_faces(), features=[], relations=[], models=[],
             warnings=['Agent-authored explicit feature interpretation, not neural inference or human production approval.',
                       'Material, actual fixture, tolerances and production cutting data not supplied.'])
    f['pipeline_metadata'].update(producer_version='source-bound-stand-trial/0.1', code_commit='P08 bounded trial',
        input_prediction_schema='manual-source-bound-trial', geometry_adapter_version='P01 CadDocument')
    # Source face groups are explicit and hash-locked; dimensions are checked against P01.
    specs=[
      ('external', 'step', list(range(8)), [0,0,-1], {'width':15.6,'depth':10}, [0,0,10]),
      ('through', 'hole', [8], [0,0,-1], {'diameter':6.2,'depth':10}, [0,0,10]),
      ('top_chamfer', 'edge_transition', list(range(21,29)), [0,0,-1], {'chamfer_width':.2,'chamfer_angle':45}, [0,0,10]),
      ('counterbore', 'pocket', [11,12], [0,0,1], {'width':10.25,'depth':6.4}, [0,0,0]),
    ]
    for n in (14,16,18,20):
        x,y,_=records[f'F{n:04}']['centroid']
        specs.append((f'blind_{n}', 'hole', [n-1,n], [0,0,1], {'diameter':2.05,'depth':7.5}, [x,y,0]))
    specs.append(('bottom_chamfer','edge_transition',list(range(29,37)),[0,0,1],{'chamfer_width':.2,'chamfer_angle':45},[0,0,0]))
    by_feature={}
    for i,(role,family,ids,direction,measures,origin) in enumerate(specs,1):
        feat=copy.deepcopy(template); fid=f'feature:{i:04}'; faces=[f'F{x:04}' for x in ids]
        feat['instance_id']=fid
        feat['canonical_label']={'taxonomy_id':'aicnc-manufacturing-feature/1.0','family':family,
            'attributes':{'edge_form':'chamfer'} if family=='edge_transition' else {}}
        bottoms=['F0012'] if role=='counterbore' else ([faces[0]] if role.startswith('blind') else [])
        feat['topology'].update(face_ids=faces, side_face_ids=[x for x in faces if x not in bottoms],bottom_face_ids=bottoms,transition_face_ids=[],opening_edge_ids=[],roles_complete=True)
        feat['placement'].update(origin=origin,origin_role='opening_center' if family in ('hole','pocket') else 'reference_corner',source='manual',access_directions=[direction])
        feat['placement']['local_frame'].update(definition_method='explicit source-bound trial',orientation_state='complete')
        feat['geometry']={'measurements':[dict(name=n,value=v,unit='deg' if n.endswith('angle') else 'mm',source='occt',method='P01 analytic faces plus explicit source-bound interpretation',face_ids=faces) for n,v in measures.items()],'reference_points':[],'complete':True}
        feat['requirements']={'status':'not_provided','dimensional':[],'geometric':[],'surface':[]}
        feat['prediction'].update(status='recognized',label_source='manual',confidence=1,instance_confidence=1,bottom_confidence=1,review_reasons=['No human manufacturing approval'])
        feat['provenance'].update(prediction_schema=None,raw_instance_id=None,source_label=None,taxonomy_mapping=None,evidence_source='manual',instance_boundary={'source':'manual','split_from_raw_instance':None,'partition_id':None,'method':'explicit face selection for hash-locked source'})
        f['features'].append(feat);by_feature[fid]={'role':role,'origin':origin,'direction':direction,'measurements':measures}
    write(out/'features.json',f)
    c=json.loads((ROOT/'schemas/examples/manufacturing_context.example.json').read_text())
    c['context_id']='STAND-2027-SIMULATION-ONLY'
    c['material']={'material_id':'UNKNOWN-SOFTWARE-TRIAL','designation':'unspecified','condition':'unknown','source':'No material supplied; values are simulation-only'}
    c['stock'].update(dimensions=[18,18,10],source='Explicit trial: pre-sized 10 mm stock, X/Y allowance 1.2 mm; not supplied manufacturing stock')
    c['machine'].update(machine_id='VIRTUAL-INDEXED-MILL',controller='unspecified',source='Native software simulation only')
    c['fixture'].update(fixture_id='TWO-SIDED-VIRTUAL-SETUPS',allowed_machining_directions=[[0,0,-1],[0,0,1]],source='Reclamping assumed for two-sided trial; physical fixture is not modelled')
    resources=[('EM4','flat_end_mill',4,1),('DR6.2','drill',6.2,2),('CH6','chamfer_mill',6,3),('DR2.05','drill',2.05,4)]
    c['tools']=[dict(tool_id=name,tool_type=kind,diameter=d,stickout=40,status='available',source='Explicit virtual assembly for simulation') for name,kind,d,n in resources]
    c['technology_presets']=[]
    for kind,tool,extra in [('contouring','flat_end_mill',{'stepdown':1}),('drilling','drill',{}),('pocketing','flat_end_mill',{'stepdown':1,'stepover':1}),('chamfering','chamfer_mill',{})]:
        c['technology_presets'].append(dict(preset_id='TRIAL-'+kind,material_id=c['material']['material_id'],operation_type=kind,tool_type=tool,strategy='bound_source_'+kind,cutting_parameters=dict(spindle_speed_rpm=3000,feed_rate=150,plunge_rate=60,coolant='off',**extra),status='prototype',source='Software trial only; not material-qualified cutting recommendation'))
    c['safety'].update(clearance=10,retract=5,stock_to_leave_radial=0,stock_to_leave_axial=0)
    write(out/'manufacturing_context.json',c)
    plan=build_cam_plan(f,c,features_path='features.json',features_sha256=digest(out/'features.json'),context_path='manufacturing_context.json',context_sha256=digest(out/'manufacturing_context.json'),code_commit='working-tree')
    write(out/'cam_plan.json',plan)
    assert not plan['unplanned_features'],plan['unplanned_features']
    assert len(plan['setups'])==2 and sum(len(s['operations']) for s in plan['setups'])==9
    native=[]
    for setup in plan['setups']:
        for op in setup['operations']:
            x=by_feature[op['feature_instance_ids'][0]]
            tool=next(v for v in resources if v[0]==op['tool']['tool_id'])
            role=x['role']; bottom=x['direction'][2]>0
            depth={'external':-.05,'through':-2.0,'top_chamfer':10,'counterbore':-6.4,'bottom_chamfer':0}.get(role,-(7.5+1.025/math.tan(math.radians(59))))
            native.append(dict(operation_id=op['operation_id'],name=f"S{setup['sequence']}_{role}",role=role,bottom=bottom,origin=x['origin'],top=0 if bottom else 10,depth=depth,tool_number=tool[3],tool=op['tool'],cutting_parameters=op['cutting_parameters'],face_ids=op['face_ids'],feature_instance_ids=op['feature_instance_ids']))
    write(out/'trial-binding.json',dict(schema_version='aicnc.mastercam-bound-stand-trial/0.1',scope='user_part_software_simulation',source_sha256=digest(source),plan_sha256=digest(out/'cam_plan.json'),target_sha256=digest(out/'target.stl'),source_face_namespace=cad.face_id_namespace,operations=native,stock_min=[-9,-9,0],stock_max=[9,9,10],target_volume_mm3=volume(cad.body),production_released=False))
    print(json.dumps({'operations':len(native),'setups':len(plan['setups']),'target_volume':volume(cad.body),'triangles':len(facets),'exact_zero_area_tessellation_facets_omitted':zero_area}))

if __name__=='__main__':main()
