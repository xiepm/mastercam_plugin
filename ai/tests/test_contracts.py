import asyncio,json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from pydantic import TypeAdapter,ValidationError
from models import ChangeRequest,ExistingTool,Cutting,Sections
from runtime import Runtime,process_guard,token

class Contracts(unittest.TestCase):
 def test_depth_contract(self):
  a=TypeAdapter(ChangeRequest).validate_python({'action':'operation.depth','expected_document':'test.mcam','operation_ids':[1],'parameters':{'Depth':-8,'Incremental':False,'DetachAssociativeDepth':False}})
  self.assertEqual(a.parameters.Depth,-8)
 def test_reject_invalid_requests(self):
  base={'action':'operation.depth','expected_document':'test.mcam','operation_ids':[1],'parameters':{'Depth':-8,'Incremental':False,'DetachAssociativeDepth':False}}
  for change in ({'operation_ids':[1,1]},{'operation_ids':[True]},{'operation_ids':[-1]},{'action':'run_arbitrary_code'},{'extra':'ignored?'}):
   with self.subTest(change=change),self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**base,**change})
  for depth in (float('nan'),float('inf')):
   with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**base,'parameters':{**base['parameters'],'Depth':depth}})
 def test_unknown_native_fields_rejected(self):
  with self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({'action':'operation.depth','expected_document':'test.mcam','operation_ids':[1],'parameters':{'Depth':1,'Incremental':False,'DetachAssociativeDepth':False,'Unexpected':1}})
 def test_path_tokens(self):
  for value in ('../escape','C:/escape','a'*81,'short','x\nlongpath'):
   with self.assertRaises(ValueError):token(value)
 def test_chamfer_requires_actual_angle(self):
  with self.assertRaises(ValidationError):ExistingTool(ExistingSlot=11,Diameter=6,Kind='ChamferMill')
  self.assertEqual(ExistingTool(ExistingSlot=11,Diameter=6,Kind='ChamferMill',TipAngleDegrees=45).TipAngleDegrees,45)
 def test_numeric_and_consent_types_are_strict(self):
  base={'action':'operation.depth','expected_document':'test.mcam','operation_ids':[1],'parameters':{'Depth':-8,'Incremental':False,'DetachAssociativeDepth':False}}
  for field,value in [('Depth',True),('Depth','-8'),('Incremental',0),('DetachAssociativeDepth',1),('DetachAssociativeDepth','true')]:
   with self.subTest(field=field,value=value),self.assertRaises(ValidationError):TypeAdapter(ChangeRequest).validate_python({**base,'parameters':{**base['parameters'],field:value}})
  for consent in (1,'true',False):
   with self.assertRaises(ValidationError):Cutting(Feed=100,Plunge=50,Retract=100,Rpm=1200,ConfirmOriginalFeedMode=consent)
  with self.assertRaises(ValidationError):ExistingTool(ExistingSlot=1,Diameter=6,Kind='FlatEndMill',CreateIfMissing=0)
 def test_mesh_tolerances_are_ordered(self):
  values=dict(origin=dict(x=0,y=0,z=3),normal=dict(x=0,y=0,z=1),count=1,spacing=0,mesh_tolerance=.01,weld_tolerance=.02)
  with self.assertRaises(ValidationError):Sections(**values)
  self.assertEqual(Sections(**{**values,'weld_tolerance':.001}).count,1)
 def test_process_lock(self):
  with tempfile.TemporaryDirectory() as d:
   with process_guard(Path(d)/'lock'):
    with self.assertRaises((RuntimeError,BlockingIOError)):
     with process_guard(Path(d)/'lock'):pass

class Broker(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.config=self.root/'config.json';self.config.write_text(json.dumps({'mastercam_root':str(self.root),'workspace':str(self.root),'upstream':{}}))
  self.calls=0
  async def backend(script):
   self.calls+=1;(script.parent/'result.json').write_text(json.dumps({'ok':True,'data':{'effect':'once'}}))
  self.runtime=Runtime(self.config,backend);self.runtime.check_dependencies=lambda c:[(self.root/'fake.dll','A'*64)]
 async def asyncTearDown(self):self.temp.cleanup()
 async def test_idempotent_request(self):
  first=await self.runtime.call('apply',{'plan_id':'fixture'},'repeat-1234')
  again=await self.runtime.call('apply',{'plan_id':'fixture'},'repeat-1234')
  self.assertEqual(first,again);self.assertEqual(self.calls,1)
 async def test_mismatched_reuse_rejected(self):
  await self.runtime.call('apply',{},'conflict-1234')
  with self.assertRaises(ValueError):await self.runtime.call('rollback',{},'conflict-1234')
 async def test_timeout_blocks_new_native_call_and_status_is_available(self):
  async def timeout(script):raise TimeoutError('unknown native outcome')
  self.runtime.backend=timeout
  result=await self.runtime.call('apply',{},'unknown-1234')
  self.assertEqual(result['state'],'unknown_or_running')
  self.assertEqual(self.runtime.status('unknown-1234'),result)
  with self.assertRaises(RuntimeError):await self.runtime.call('apply',{},'another-1234')
 async def test_restart_does_not_resubmit(self):
  await self.runtime.call('apply',{},'restart-1234')
  new=Runtime(self.config,lambda p:(_ for _ in ()).throw(AssertionError('must not execute')))
  result=await new.call('apply',{},'restart-1234');self.assertTrue(result['ok'])
 async def test_completed_unknown_releases_lock(self):
  async def unknown(script):pass
  self.runtime.backend=unknown
  await self.runtime.call('apply',{},'complete-1234')
  d=self.root/'plugin-ai/complete-1234';(d/'result.json').write_text('{"ok":true}')
  self.assertTrue(self.runtime.status('complete-1234')['ok'])
  # The broker may proceed after the native receipt actually appears.
  result=await self.runtime.call('inspect',{},'following-1234');self.assertEqual(result['state'],'unknown_or_running')
 async def test_invalid_dependencies_before_native_submission(self):
  def fail(c):raise RuntimeError('hash mismatch')
  self.runtime.check_dependencies=fail
  with self.assertRaises(RuntimeError):await self.runtime.call('apply',{},'hashfail-1234')
  self.assertEqual(self.calls,0);self.assertFalse((self.root/'plugin-ai/active.json').exists())
 async def test_script_write_failure_is_terminal_and_releases_lock(self):
  original=Path.write_text
  def write(path,*args,**kwargs):
   if path.name=='run.csx':raise PermissionError('injected script write failure')
   return original(path,*args,**kwargs)
  with patch.object(Path,'write_text',write):result=await self.runtime.call('apply',{},'not-submit-1234')
  self.assertEqual(result['state'],'not_submitted');self.assertEqual(self.calls,0)
  self.assertFalse((self.root/'plugin-ai/active.json').exists())
  self.assertEqual(await self.runtime.call('apply',{},'not-submit-1234'),result);self.assertEqual(self.calls,0)
  self.assertTrue((await self.runtime.call('inspect',{},'after-fail-1234'))['ok']);self.assertEqual(self.calls,1)

if __name__=='__main__':unittest.main()
