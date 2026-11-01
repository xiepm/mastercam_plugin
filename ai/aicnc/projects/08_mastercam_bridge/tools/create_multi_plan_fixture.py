"""Synthetic multi-operation STEP/Face/plan fixture using shared P01 and P07.

Run in the existing WSL OCCT environment. No recognition or production labels.
"""
from pathlib import Path
import copy,json,math,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
for name in ('01_cad_core','07_capp_planner','08_mastercam_bridge'):
    sys.path.insert(0,str(ROOT/'projects'/name/'src'))
from cad_core.core import CadDocument
from cad_core.faceted_material_difference import triangulate
from cad_core.constructive_templates import volume
from capp_planner.planner import build_cam_plan
from mastercam_bridge.contour_smoke import load,write_new,digest
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse,BRepAlgoAPI_Cut
from OCC.Core.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCC.Core.gp import gp_Pnt,gp_Ax2,gp_Dir
from OCC.Core.STEPControl import STEPControl_Writer,STEPControl_AsIs
from OCC.Core.IFSelect import IFSelect_RetDone

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
box=lambda x,y,z,w,h,d:BRepPrimAPI_MakeBox(gp_Pnt(x,y,z),w,h,d).Shape()
cylinder=lambda x,y,z,r,d:BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(0,0,1)),r,d).Shape()
shape=BRepAlgoAPI_Fuse(box(-3,-3,-10,66,46,8),box(0,0,-2,60,40,2)).Shape()
pocket=BRepAlgoAPI_Fuse(box(13,12,-4,14,16,5),box(10,15,-4,20,10,5)).Shape()
for x,y in [(13,15),(27,15),(27,25),(13,25)]:pocket=BRepAlgoAPI_Fuse(pocket,cylinder(x,y,-4,3,5)).Shape()
shape=BRepAlgoAPI_Cut(shape,pocket).Shape()
for y,r in [(12,4),(28,3)]:shape=BRepAlgoAPI_Cut(shape,cylinder(46,y,-11,r,12)).Shape()
unify=ShapeUpgrade_UnifySameDomain(shape,True,True,False);unify.Build();shape=unify.Shape()
writer=STEPControl_Writer();writer.Transfer(shape,STEPControl_AsIs);assert writer.Write(str(out/'target.step'))==IFSelect_RetDone
cad=CadDocument.from_step(out/'target.step');write_new(out/'p01.json',cad.summary())
triangles=triangulate(cad.body,.005,100000)
raw=bytearray(b'AICNC P01 independent STEP target in PCS mm'.ljust(80,b'\0'))+struct.pack('<I',len(triangles))
for a,b,c in triangles:
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in n))
    raw+=struct.pack('<12fH',*[x/length for x in n],*a,*b,*c,0)
(out/'target.stl').write_bytes(raw)
write_new(out/'target-evidence.json',dict(step_sha256=digest(out/'target.step'),stl_sha256=digest(out/'target.stl'),p01_summary_sha256=digest(out/'p01.json'),requested_deflection_mm=.005,exact_volume_mm3=volume(cad.body),triangles=len(triangles),source='independent synthetic design through P01',production_released=False))

f=load(ROOT/'schemas/examples/features.example.json');template=copy.deepcopy(f['features'][0])
f.update(part_id='P08-MASTERCAM-MULTI-TEST',source=cad.summary()['source'],face_id_namespace=cad.face_id_namespace,faces=cad.features_faces(),features=[],relations=[],models=[],warnings=['Explicit synthetic fixture; manual feature labels; no manufacturing recommendation.'])
f['pipeline_metadata'].update(producer_version='multi-test-fixture-only',code_commit='P08 synthetic construction',input_prediction_schema='manual-fixture',geometry_adapter_version='P01 CadDocument')
records=cad.face_records
contour=[r['face_id'] for r in records if abs(r['centroid'][2]+1)<1e-7 or (abs(r['centroid'][2]+2)<1e-7 and r['analytic'].get('normal')==[0,0,1])]
pocketids=[r['face_id'] for r in records if 9.99<=r['centroid'][0]<=30.01 and 11.99<=r['centroid'][1]<=28.01 and -4.01<=r['centroid'][2]<=-1.99 and r['face_id'] not in contour]
hole1=[r['face_id'] for r in records if abs(r['centroid'][0]-46)<1e-6 and abs(r['centroid'][1]-12)<1e-6 and abs(r['centroid'][2]+5)<1e-6]
hole2=[r['face_id'] for r in records if abs(r['centroid'][0]-46)<1e-6 and abs(r['centroid'][1]-28)<1e-6 and abs(r['centroid'][2]+5)<1e-6]
assert len(contour)==5 and len(pocketids)==9 and len(hole1)==1 and len(hole2)==1,(contour,pocketids,hole1,hole2)
specs=[('step',contour,[0,0,0],{'width':40,'depth':2}),('pocket',pocketids,[10,12,0],{'width':16,'depth':4}),('hole',hole1,[46,12,0],{'diameter':8,'depth':10}),('hole',hole2,[46,28,0],{'diameter':6,'depth':10})]
for i,(family,faces,origin,measurements) in enumerate(specs,1):
    feat=copy.deepcopy(template);feat['instance_id']='feature:'+str(i).zfill(4)
    feat['canonical_label']={'taxonomy_id':'aicnc-manufacturing-feature/1.0','family':family,'attributes':{}}
    bottom=[r['face_id'] for r in records if r['face_id'] in faces and abs(r['centroid'][2]+(4 if family=='pocket' else 2))<1e-7] if family!='hole' else []
    feat['topology'].update(face_ids=faces,side_face_ids=[x for x in faces if x not in bottom],bottom_face_ids=bottom,transition_face_ids=[],opening_edge_ids=[],roles_complete=True)
    feat['placement'].update(origin=origin,origin_role='reference_corner' if family!='hole' else 'opening_center',source='manual',access_directions=[[0,0,-1]])
    feat['placement']['local_frame'].update(definition_method='explicit_synthetic_fixture',orientation_state='complete')
    feat['geometry']={'measurements':[dict(name=n,value=v,unit='mm',source='manual',method='explicit_analytical_fixture',face_ids=faces) for n,v in measurements.items()],'reference_points':[],'complete':True}
    feat['requirements']={'status':'not_provided','dimensional':[],'geometric':[],'surface':[]}
    feat['prediction'].update(status='confirmed',label_source='manual',confidence=1,instance_confidence=1,bottom_confidence=1,review_reasons=[])
    feat['provenance'].update(prediction_schema=None,raw_instance_id=None,source_label=None,taxonomy_mapping=None,evidence_source='manual',instance_boundary={'source':'manual','split_from_raw_instance':None,'partition_id':None,'method':'explicit test fixture selection'})
    f['features'].append(feat)
write_new(out/'features.json',f)
c=load(ROOT/'schemas/examples/manufacturing_context.example.json');c['context_id']='P08-MASTERCAM-MULTI-TEST'
c['material']={'material_id':'SOFTWARE-TEST','designation':'unspecified software fixture','condition':'not qualified','source':'explicit software test; no manufacturing recommendation'}
c['stock'].update(dimensions=[66,46,10],source='explicit analytical stock')
c['tools']=[dict(tool_id=tid,tool_type=typ,diameter=diameter,stickout=50,status='available',source='synthetic geometry') for tid,typ,diameter in [('TEST-EM6','flat_end_mill',6),('TEST-DR8','drill',8),('TEST-DR6','drill',6)]]
c['technology_presets']=[]
for i,(kind,strategy,typ,extra) in enumerate([('contouring','rectangular_external_contour','flat_end_mill',{'stepdown':2}),('pocketing','rectangular_pocket','flat_end_mill',{'stepdown':4,'stepover':2}),('drilling','through_drilling','drill',{})]):
    c['technology_presets'].append(dict(preset_id='MULTI-'+str(i),material_id='SOFTWARE-TEST',operation_type=kind,tool_type=typ,strategy=strategy,cutting_parameters=dict(spindle_speed_rpm=3000,feed_rate=300,plunge_rate=100,coolant='off',**extra),status='prototype',source='explicit software trial values'))
c['safety'].update(clearance=10,retract=5,stock_to_leave_radial=0,stock_to_leave_axial=0)
write_new(out/'manufacturing_context.json',c)
commit=sys.argv[2] if len(sys.argv)>2 else json.loads((ROOT/'source-manifest.json').read_text(encoding='utf-8'))['upstream_base_commit']
assert len(commit)==40 and all(x in '0123456789abcdef' for x in commit)
plan=build_cam_plan(f,c,features_path='features.json',features_sha256=digest(out/'features.json'),context_path='manufacturing_context.json',context_sha256=digest(out/'manufacturing_context.json'),code_commit=commit)
assert len(plan['setups'])==1 and len(plan['setups'][0]['operations'])==4 and not plan['unplanned_features'],plan
write_new(out/'cam_plan.json',plan)
geometries=[dict(shape='rectangle',origin_mm=[0,0,0],width_mm=60,height_mm=40,top_mm=0,depth_mm=-2),dict(shape='rectangle',origin_mm=[10,12,0],width_mm=20,height_mm=16,top_mm=0,depth_mm=-4),dict(shape='points',points_mm=[[46,12,0]],top_mm=0,depth_mm=-13),dict(shape='points',points_mm=[[46,28,0]],top_mm=0,depth_mm=-13)]
bound=[]
for i,(op,g) in enumerate(zip(plan['setups'][0]['operations'],geometries)):
    bound.append(dict(operation_id=op['operation_id'],feature_instance_ids=op['feature_instance_ids'],face_ids=op['face_ids'],geometry=g,tool_assembly=dict(number=[1,1,2,3][i],length_mm=50,flute_length_mm=20,shoulder_length_mm=25,holder_diameter_mm=20,holder_length_mm=40,tip_angle_deg=118 if i>=2 else 0)))
binding=dict(schema_version='aicnc.mastercam-plan-simulation-binding/0.2',scope='synthetic_native_validation',profile='top_multi_contour_pocket_drill',plan=dict(path='cam_plan.json',sha256=digest(out/'cam_plan.json')),setup_id=plan['setups'][0]['setup_id'],stock=dict(min_mm=[-3,-3,-10],max_mm=[63,43,0]),operations=bound,target=dict(path='target.stl',sha256=digest(out/'target.stl')),acceptance=dict(material_difference_mm3=5,reopen_difference_mm3=.01,scope='software_test_faceted_volume_only_not_dimensional_conformance'))
write_new(out/'binding.json',binding)
print(json.dumps(dict(plan=str(out/'cam_plan.json'),face_groups=[x[1] for x in specs],target_volume_mm3=volume(cad.body)),indent=2))
