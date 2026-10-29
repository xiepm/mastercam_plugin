import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from pydantic import TypeAdapter,ValidationError
from models import ChangeRequest

class PanelContracts(unittest.TestCase):
 def validate(self,action,parameters,**kwargs):
  return TypeAdapter(ChangeRequest).validate_python(dict(action=action,expected_document='fixture.mcam',parameters=parameters,**kwargs))
 def test_parameter_edits_require_a_value(self):
  p=dict(feed=None,spindle=None,wall=None,floor=None)
  with self.assertRaises(ValidationError):self.validate('operation.parameters',p,operation_ids=[1])
  self.validate('operation.parameters',{**p,'wall':0},operation_ids=[1])
 def test_duplicate_group_ids_rejected(self):
  with self.assertRaises(ValidationError):self.validate('groups.rename',dict(names=[dict(group_id=2,name='A'),dict(group_id=2,name='B')]))
 def test_stock_requires_positive_dimensions(self):
  p=dict(machine_group_id=1,size=dict(x=1,y=2,z=3),origin=dict(x=0,y=0,z=0),anchor='TopLeft',plane_id=1)
  for bad in [0,-1,float('inf')]:
   with self.subTest(bad=bad),self.assertRaises(ValidationError):self.validate('stock.rectangle',{**p,'size':dict(x=bad,y=2,z=3)})
 def test_import_geometry_is_disabled_before_native_call(self):
  p=dict(path='D:/test.mcam-operations',sha256='A'*64,library_operation_ids=[1],target_group_id=2,include_geometry=False,set_views_to_current=False)
  self.validate('operations.import',p)
  for changes in [dict(include_geometry=True),dict(include_geometry=0),dict(sha256='bad'),dict(library_operation_ids=[1,1])]:
   with self.subTest(changes=changes),self.assertRaises(ValidationError):self.validate('operations.import',{**p,**changes})
 def test_chamfer_requires_unique_edges_positive_distance(self):
  self.validate('geometry.chamfer_edges',dict(edge_tags=[1,2],distance=1),source_id=1)
  for p in [dict(edge_tags=[1,1],distance=1),dict(edge_tags=[1],distance=0),dict(edge_tags=[True],distance=1)]:
   with self.assertRaises(ValidationError):self.validate('geometry.chamfer_edges',p,source_id=1)
 def test_tap_contract_requires_explicit_real_target_and_pitch(self):
  from panel_models import DrillStage
  p=dict(Name='Tap',Purpose='Tap',Cycle='Tap',Sorting='SelectionOrder',Tool=dict(Slot=1,Kind='TapRH',Diameter=6,LengthOffset=1,DiameterOffset=1),Cutting=dict(Feed=600,Plunge=600,Retract=600,Rpm=600,NativeFeedModeReviewed=True),Depth=-10,Clearance=15,Retract=5,FeedPlane=2,Peck1=0,Peck2=0,PeckClearance=0,ChipBreak=0,Dwell=0,ThreadPitch=1,TapTarget=dict(MachineGroupId=1,MachineName='test',PostName='test',ExplicitFeedReviewed=True))
  DrillStage(**p)
  for delta in [dict(ThreadPitch=0),dict(TapTarget=None),dict(Cycle='Drill'),dict(Purpose='Drill')]:
   with self.assertRaises(ValidationError):DrillStage(**{**p,**delta})
  sets=dict(sets=[dict(name='test',reference_id=1,local_points=[dict(x=0,y=0,z=0)],top=0,stages=[p])])
  self.validate('drilling.tap',sets)
  with self.assertRaises(ValidationError):self.validate('drilling.stages',sets)

if __name__=='__main__':unittest.main()
