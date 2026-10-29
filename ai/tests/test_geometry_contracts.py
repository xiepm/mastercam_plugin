import json,sys,unittest
from pathlib import Path
from pydantic import TypeAdapter,ValidationError
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai/mcp'))
from models import ChangeRequest
from geometry_models import FixtureParameters,SketchParameters,RadiusParameters,GeometryCopyParameters

class GeometryContracts(unittest.TestCase):
 def test_fixture_rejects_non_quarter_turn_and_bool(self):
  p=dict(reference=dict(x=0,y=0,z=0),target=dict(x=10,y=0,z=0),translation=dict(x=0,y=0,z=0),world_z_degrees=90)
  self.assertEqual(FixtureParameters(**p).world_z_degrees,90)
  for x in (True,90.0,'90',45,360):
   with self.subTest(x=x),self.assertRaises(ValidationError):FixtureParameters(**{**p,'world_z_degrees':x})
 def test_svg_cannot_smuggle_path_or_options(self):
  request=dict(action='xplus.svg',expected_document='test.mcam',svg_xml='<svg/>',parameters=dict(Scale=1,OffsetX=0,OffsetY=0,Z=0,FlipY=False,ChordTolerance=.02,Level=1,Color=10,MaxSegments=200))
  self.assertEqual(TypeAdapter(ChangeRequest).validate_python(request).action,'xplus.svg')
  for extra in ({'file_path':'outside.svg'},{'script':'anything'}):
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**request,**extra})
  for key,value in [('FlipY',1),('Scale',float('inf')),('Color',256),('MaxSegments',20001)]:
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**request,'parameters':{**request['parameters'],key:value}})
 def test_sketch_machining_requires_explicit_tool(self):
  p=dict(depth=-1,diameter=6,level=1,color=10,chains=[[dict(x=0,y=0),dict(x=10,y=0)]],machining=None,existing_tool_slot=None)
  self.assertIsNone(SketchParameters(**p).machining)
  with self.assertRaises(ValidationError):SketchParameters(**{**p,'existing_tool_slot':1})
  with self.assertRaises(ValidationError):SketchParameters(**{**p,'chains':[[dict(x=0,y=0)]]})
 def test_radius_is_bounded_unique_and_finite(self):
  self.assertEqual(RadiusParameters(kinds=['Cylinder'],minimum=3,maximum=3).maximum,3)
  for p in (dict(kinds=['Cylinder'],minimum=4,maximum=3),dict(kinds=['Cylinder','Cylinder'],minimum=0,maximum=3),dict(kinds=['Ellipse'],minimum=0,maximum=3)):
   with self.assertRaises(ValidationError):RadiusParameters(**p)
 def test_nci_names_never_accept_paths_or_duplicate_ids(self):
  def req(names):return TypeAdapter(ChangeRequest).validate_python(dict(action='xplus.rename_nci',expected_document='test.mcam',parameters=dict(names=names)))
  self.assertEqual(req([dict(operation_id=1,name='O_001')]).parameters.names[0].name,'O_001')
  for name in ('../file','C:\\x','a/b','name.nci','a\nb'):
   with self.assertRaises(ValidationError):req([dict(operation_id=1,name=name)])
  with self.assertRaises(ValidationError):req([dict(operation_id=1,name='A'),dict(operation_id=1,name='B')])
 def test_entity_ids_are_exact_and_unique(self):
  req=dict(action='mp.reverse_normals',expected_document='test.mcam',entity_ids=[1],parameters={})
  for ids in ([1,1],[True],[],['1']):
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**req,'entity_ids':ids})
 def test_interactive_panels_are_exact_existing_ft_routes(self):
  panels=json.loads((ROOT/'ai/workflows/interactive-panels.json').read_text())['panels']
  routes=json.loads((ROOT/'ai/catalog/capabilities.json').read_text('utf-8-sig'))['routes']
  self.assertEqual(len(panels),8)
  for app,function in panels.values():self.assertEqual(sum(r['application']==app and r['function']==function for r in routes),1)
  self.assertFalse(any('CIMCO' in a for a,f in panels.values()))
 def test_adapted_sources_match_recorded_provenance(self):
  import hashlib
  provenance=json.loads((ROOT/'ai/bridge/adapter-provenance.json').read_text())
  for f in provenance['files']:self.assertEqual(hashlib.sha256((ROOT/f['adapted']).read_bytes()).hexdigest(),f['adapted_sha256'])

if __name__=='__main__':unittest.main()
