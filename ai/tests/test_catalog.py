import hashlib,json,subprocess,sys,tempfile,tomllib,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai/mcp'))
from models import ChangeRequest
from pydantic import TypeAdapter
load=lambda p:json.loads(p.read_text('utf-8-sig'))

class Catalog(unittest.TestCase):
 def test_modules_and_routes(self):
  c=load(ROOT/'ai/catalog/capabilities.json');modules=load(ROOT/'catalog/modules.json')
  ids=[r['id'] for r in c['capabilities']]
  self.assertEqual(len(ids),len(set(ids)))
  self.assertEqual({m['id'] for m in modules},{r['module'] for r in c['capabilities'] if r['id'].startswith('module.') and r['module']!='CIMCO'})
  for r in c['routes']:
   content=(ROOT/'payload'/r['ft']).read_text('utf-8-sig')
   self.assertIn('APPLICATION "'+r['application']+'"',content)
   self.assertIn('FUNCTION '+r['kind']+' "'+r['function']+'"',content)
 def test_typed_matches_input_contract(self):
  schema=TypeAdapter(ChangeRequest).json_schema()
  actual=set(schema['discriminator']['mapping'])
  c=load(ROOT/'ai/catalog/capabilities.json')
  typed={r['action'] for r in c['capabilities'] if r['automation']=='typed'}
  self.assertEqual(actual,typed);self.assertEqual(len(typed),28)
  ids={r['id'] for r in c['capabilities']}
  for r in c['capabilities']:
   if r['automation']=='typed':self.assertIn(r['business_contract'],ids)
 def test_bridge_identity(self):
  identity=load(ROOT/'ai/bridge/identity.json')
  self.assertEqual(hashlib.sha256((ROOT/'ai/bridge/bin'/identity['file']).read_bytes()).hexdigest().upper(),identity['sha256'])
 def test_local_setup_preserves_other_configuration(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);cfg=d/'config.toml';cfg.write_text('[mcp_servers.mastercam]\ncommand="python"\nargs=["bridge.py"]\n[mcp_servers.keep]\ncommand="untouched"\n[mcp_servers.keep.tools.x]\napproval_mode="approve"\n',encoding='utf-8')
   args=[sys.executable,str(ROOT/'ai/tools/local_setup.py'),'--mastercam-root',str(d/'Mastercam'),'--workspace',str(d/'workspace'),'--codex-config',str(cfg),'--register']
   p=subprocess.run(args,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
   value=tomllib.loads(cfg.read_text('utf-8'))
   self.assertEqual(value['mcp_servers']['keep']['tools']['x']['approval_mode'],'approve')
   first=cfg.read_bytes();p=subprocess.run(args,capture_output=True);self.assertEqual(p.returncode,0);self.assertEqual(cfg.read_bytes(),first)
 def test_skill_install_refuses_modified_skill(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);args=[sys.executable,str(ROOT/'ai/tools/install_skill.py'),'--config',str(d/'runtime.json'),'--skills-root',str(d/'skills')]
   p=subprocess.run(args,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
   skill=d/'skills/mastercam-plugin-suite/SKILL.md';skill.write_text('user custom text',encoding='utf-8')
   p=subprocess.run(args,capture_output=True);self.assertNotEqual(p.returncode,0);self.assertEqual(skill.read_text(),'user custom text')
 def test_relative_workspace_registers_absolute_config(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);cfg=d/'config.toml';cfg.write_text('[mcp_servers.mastercam]\ncommand="python"\nargs=["bridge.py"]\n',encoding='utf-8')
   args=[sys.executable,str(ROOT/'ai/tools/local_setup.py'),'--mastercam-root',str(d/'Mastercam'),'--workspace','relative-workspace','--codex-config',str(cfg),'--register']
   p=subprocess.run(args,cwd=d,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
   config=Path(tomllib.loads(cfg.read_text('utf-8'))['mcp_servers']['mastercam-plugins']['env']['MC_PLUGIN_AI_CONFIG'])
   self.assertTrue(config.is_absolute());self.assertEqual(config,d/'relative-workspace/plugin-ai-config.json');self.assertTrue(config.is_file())
 def test_checkout_workspace_is_rejected_without_writing(self):
  with tempfile.TemporaryDirectory() as d:
   cfg=Path(d)/'config.toml';cfg.write_text('[mcp_servers.mastercam]\ncommand="python"\n',encoding='utf-8');before=cfg.read_bytes()
   target=ROOT/'ai/private-output-test-must-not-exist'
   self.assertFalse(target.exists())
   p=subprocess.run([sys.executable,str(ROOT/'ai/tools/local_setup.py'),'--mastercam-root',str(Path(d)/'Mastercam'),'--workspace',str(target),'--codex-config',str(cfg),'--register'],capture_output=True)
   self.assertNotEqual(p.returncode,0);self.assertFalse(target.exists());self.assertEqual(cfg.read_bytes(),before)

if __name__=='__main__':unittest.main()
