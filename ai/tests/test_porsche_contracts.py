import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from pydantic import TypeAdapter,ValidationError
from models import ChangeRequest,PorscheContour,PorscheHoles,PorscheHealing,UnitVector

class PorscheContracts(unittest.TestCase):
 def test_healing_is_explicit_radius_copy_contract(self):
  r=dict(action='porsche.heal_holes',expected_document='fixture.mcam',solid_ids=[1],parameters=dict(minimum_radius=2.9,maximum_radius=3.1))
  self.assertEqual(TypeAdapter(ChangeRequest).validate_python(r).parameters.maximum_radius,3.1)
  for change in ({'replace_original':True},{'solid_ids':[1,1]},{'parameters':dict(minimum_radius=3,maximum_radius=3)},{'parameters':dict(minimum_radius=True,maximum_radius=3)}):
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**r,**change})
 def test_projection_requires_height_intent_and_real_view_id(self):
  r=dict(action='porsche.project_boundary',expected_document='fixture.mcam',solid_ids=[1],plane_id=1,parameters=dict(tolerance=.02,output_level=1,height=None))
  self.assertIsNone(TypeAdapter(ChangeRequest).validate_python(r).parameters.height)
  for change in ({'plane_id':True},{'parameters':dict(tolerance=.02,output_level=1)},{'parameters':dict(tolerance=0,output_level=1,height=None)}):
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**r,**change})
 def test_alignment_is_unit_world_vector(self):
  self.assertEqual(UnitVector(x=0,y=0,z=1).z,1)
  for v in (dict(x=0,y=0,z=0),dict(x=1,y=1,z=1),dict(x=True,y=0,z=0)):
   with self.assertRaises(ValidationError):UnitVector(**v)
 def test_no_machining_defaults_or_implicit_regeneration(self):
  for cls in (PorscheContour,PorscheHoles):
   required=set(cls.model_json_schema()['required'])
   self.assertTrue({'FeedModeReviewed','Regenerate','Feed','Plunge','Rpm','ToolLength','FluteLength'}<=required)
   with self.assertRaises(ValidationError):cls(FeedModeReviewed=True)

if __name__=='__main__':unittest.main()
