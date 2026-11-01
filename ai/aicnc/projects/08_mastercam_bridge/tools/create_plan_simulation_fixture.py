"""Generate the explicit synthetic test source with shared P01 and P07 (WSL OCCT env)."""
from pathlib import Path
import sys,json,subprocess
ROOT=Path(__file__).resolve().parents[3]
for project in ('01_cad_core','07_capp_planner','08_mastercam_bridge'):
    sys.path.insert(0,str(ROOT/'projects'/project/'src'))
from cad_core.core import CadDocument
from capp_planner.planner import build_cam_plan
from mastercam_bridge.plan_simulation import stepped_target
from mastercam_bridge.contour_smoke import digest,write_new,load
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCC.Core.gp import gp_Pnt
from OCC.Core.STEPControl import STEPControl_Writer,STEPControl_AsIs
from OCC.Core.IFSelect import IFSelect_RetDone
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
base=BRepPrimAPI_MakeBox(gp_Pnt(-3,-3,-10),66,46,8).Shape()
boss=BRepPrimAPI_MakeBox(gp_Pnt(0,0,-2),60,40,2).Shape()
shape=BRepAlgoAPI_Fuse(base,boss).Shape()
writer=STEPControl_Writer();writer.Transfer(shape,STEPControl_AsIs)
assert writer.Write(str(out/'target.step'))==IFSelect_RetDone
cad=CadDocument.from_step(out/'target.step');write_new(out/'p01.json',cad.summary())
f=load(ROOT/'schemas/examples/features.example.json')
f.update(part_id='P08-MASTERCAM-SYNTHETIC-CONTOUR',source=cad.summary()['source'],face_id_namespace=cad.face_id_namespace,faces=cad.features_faces(),relations=[],models=[],warnings=['Explicit synthetic manually assigned contour fixture; no model inference or drawing qualification.'])
f['pipeline_metadata'].update(producer_version='test-fixture-only',code_commit='P08 synthetic construction',input_prediction_schema='manual-fixture',geometry_adapter_version='P01 CadDocument')
# Select the four boss walls and shelf using their actual P01 Face identity.
selected=[x['face_id'] for x in cad.face_records if (abs(x['centroid'][2]+1)<1e-7 or abs(x['centroid'][2]+2)<1e-7)]
assert len(selected)==5,selected
sides=[x['face_id'] for x in cad.face_records if abs(x['centroid'][2]+1)<1e-7]
feat=f['features'][0];f['features']=[feat]
feat['canonical_label']={'taxonomy_id':'aicnc-manufacturing-feature/1.0','family':'step','attributes':{}}
feat['topology'].update(face_ids=selected,side_face_ids=sides,bottom_face_ids=[x for x in selected if x not in sides],transition_face_ids=[],opening_edge_ids=[],roles_complete=True)
feat['placement'].update(origin=[0,0,0],origin_role='reference_corner',source='manual',access_directions=[[0,0,-1]])
feat['placement']['local_frame']['definition_method']='explicit_synthetic_fixture';feat['placement']['local_frame']['orientation_state']='complete'
feat['geometry']={'measurements':[{'name':n,'value':v,'unit':'mm','source':'manual','method':'explicit_analytical_fixture','face_ids':selected} for n,v in [('width',40),('depth',2)]],'reference_points':[],'complete':True}
feat['requirements']={'status':'not_provided','dimensional':[],'geometric':[],'surface':[]}
feat['prediction'].update(status='confirmed',label_source='manual',confidence=1,instance_confidence=1,bottom_confidence=1,review_reasons=[])
feat['provenance'].update(prediction_schema=None,raw_instance_id=None,source_label=None,taxonomy_mapping=None,evidence_source='manual',instance_boundary={'source':'manual','split_from_raw_instance':None,'partition_id':None,'method':'explicit test fixture selection'})
write_new(out/'features.json',f)
c=load(ROOT/'schemas/examples/manufacturing_context.example.json');c['context_id']='P08-MASTERCAM-SIMULATION-TEST'
c['material']={'material_id':'SOFTWARE-TEST','designation':'unspecified software fixture','condition':'not qualified','source':'explicit software test; no manufacturing recommendation'}
c['stock'].update(dimensions=[66,46,10],source='explicit analytical test stock')
c['tools']=[dict(tool_id='TEST-EM6',tool_type='flat_end_mill',diameter=6,stickout=50,status='available',source='synthetic geometry')]
c['technology_presets']=[dict(preset_id='TEST-CONTOUR',material_id='SOFTWARE-TEST',operation_type='contouring',tool_type='flat_end_mill',strategy='rectangular_external_contour',cutting_parameters=dict(spindle_speed_rpm=3000,feed_rate=300,plunge_rate=100,stepdown=2,coolant='off'),status='prototype',source='explicit software trial values')]
c['safety'].update(clearance=10,retract=5,stock_to_leave_radial=0,stock_to_leave_axial=0)
write_new(out/'manufacturing_context.json',c)
plan=build_cam_plan(f,c,features_path='features.json',features_sha256=digest(out/'features.json'),context_path='manufacturing_context.json',context_sha256=digest(out/'manufacturing_context.json'),code_commit=json.loads((ROOT/'source-manifest.json').read_text(encoding='utf-8'))['upstream_base_commit'])
assert len(plan['setups'])==1 and not plan['unplanned_features'],plan
write_new(out/'cam_plan.json',plan)
(out/'target.stl').write_bytes(stepped_target(60,40,-2,3,10))
binding=dict(schema_version='aicnc.mastercam-plan-simulation-binding/0.1',scope='synthetic_native_validation',profile='rectangular_external_contour',plan=dict(path='cam_plan.json',sha256=digest(out/'cam_plan.json')),setup_id=plan['setups'][0]['setup_id'],operation_id=plan['setups'][0]['operations'][0]['operation_id'],feature_instance_ids=[feat['instance_id']],face_ids=selected,geometry=dict(width_mm=60,height_mm=40,depth_mm=-2,margin_mm=3,stock_height_mm=10),tool_assembly=dict(length_mm=50,flute_length_mm=20,shoulder_length_mm=25,holder_diameter_mm=20,holder_length_mm=40),target=dict(path='target.stl',sha256=digest(out/'target.stl')))
write_new(out/'binding.json',binding)
print(json.dumps({'plan':str(out/'cam_plan.json'),'faces':selected,'target_sha256':digest(out/'target.stl')}))
