import importlib.util,json,os,sys,tempfile,tomllib,unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai'))
from portable import context,knowledge
from portable.common import load,sha

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
installer=module('portable_installer',ROOT/'ai/tools/install_agent.py')
recovery=module('portable_recovery',ROOT/'ai/tools/recover_request.py')
ipc=module('portable_ipc',ROOT/'ai/upstream/ipc_client.py')

class Portable(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='Mastercam portable ')
        self.root=Path(self.tmp.name);self.mc=self.root/'Mastercam installed'
        for rel in ('Mastercam.exe','chooks/MCNetScripting/IPCServer.dll'):
            p=self.mc/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'test placeholder, never native evidence')
        self.workspace=self.root/'private workspace';self.home=self.root/'new codex home'
    def tearDown(self):self.tmp.cleanup()
    def setup(self):
        installer.install(self.mc,self.workspace,self.home,enable_startup=False)
        return str(self.workspace/'plugin-ai-config.json')
    def test_fresh_install_and_idempotency(self):
        self.home.mkdir();cfg=self.home/'config.toml'
        cfg.write_text('model="unchanged"\n[mcp_servers.keep]\ncommand="custom"\n[mcp_servers.keep.tools.x]\napproval_mode="approve"\n',encoding='utf-8')
        self.setup();first=cfg.read_bytes();self.setup();self.assertEqual(first,cfg.read_bytes())
        data=tomllib.loads(first.decode());self.assertEqual(data['model'],'unchanged')
        self.assertEqual(data['mcp_servers']['keep']['tools']['x']['approval_mode'],'approve')
        self.assertEqual(set(data['mcp_servers']),{'mastercam','mastercam-plugins','keep'})
        self.assertTrue((self.home/'skills/mastercam-project/references/connection.json').is_file())
    def test_conflict_is_non_destructive(self):
        self.home.mkdir();cfg=self.home/'config.toml';cfg.write_text('[mcp_servers.mastercam]\ncommand="my existing bridge"\n')
        before=cfg.read_bytes()
        with self.assertRaisesRegex(ValueError,'registration differs'):self.setup()
        self.assertEqual(before,cfg.read_bytes());self.assertFalse(self.workspace.exists())
    def test_modified_skill_is_preserved(self):
        self.setup();p=self.home/'skills/mastercam-project/SKILL.md';p.write_text('user custom skill')
        with self.assertRaisesRegex(ValueError,'skill differs'):self.setup()
        self.assertEqual(p.read_text(),'user custom skill')
    def task(self):
        cfg=self.setup();source=self.root/'new part.step';source.write_text('synthetic test only')
        result=context.create('part-001',str(source),'native project only',{'material':'unknown'},cfg)
        return cfg,Path(result['directory'])
    def test_new_conversation_recovers_and_invalidates_changed_plan(self):
        cfg,d=self.task();receipt=d/'native.json';receipt.write_text('{"ok":true}')
        plan=d/'cam_plan.json';plan.write_text('{"version":1}')
        r=context.checkpoint('part-001','native-1','toolpath','pass','Actual readback checked',[str(receipt)],{'plan':str(plan)},'save and reopen',cfg)
        self.assertEqual(r['stages']['toolpath']['state'],'pass')
        plan.write_text('{"version":2}')
        r=context.resume('part-001',cfg)
        self.assertEqual(r['stages']['toolpath']['state'],'unknown')
        self.assertIn('cam_plan.json',r['stages']['toolpath']['stale_references'])
    def test_source_change_invalidates_result(self):
        cfg,d=self.task();r=d/'readback.json';r.write_text('{}')
        context.checkpoint('part-001','e1','native_project','pass','checked',[str(r)],{},'',cfg)
        (d/'input.step').write_text('changed')
        self.assertFalse(context.resume('part-001',cfg)['source_unchanged'])
        self.assertEqual(context.resume('part-001',cfg)['stages']['native_project']['state'],'unknown')
    def test_no_fabricated_pass_or_production_pass(self):
        cfg,d=self.task()
        with self.assertRaisesRegex(ValueError,'evidence'):context.checkpoint('part-001','e1','toolpath','pass','no receipt',config_path=cfg)
        with self.assertRaisesRegex(ValueError,'production'):context.checkpoint('part-001','e2','production_release','pass','release',config_path=cfg)
    def test_path_traversal_and_foreign_evidence_rejected(self):
        cfg,d=self.task();p=self.root/'outside.json';p.write_text('{}')
        with self.assertRaises(ValueError):context.resume('../escape',cfg)
        with self.assertRaises(ValueError):context.checkpoint('part-001','e1','toolpath','pass','outside',[str(p)],config_path=cfg)
    def test_event_id_is_immutable_and_replay_is_idempotent(self):
        cfg,d=self.task()
        args=('part-001','e1','toolpath','unknown','waiting',[],{},'inspect',cfg)
        context.checkpoint(*args);context.checkpoint(*args)
        self.assertEqual(len(list((d/'events').glob('*.json'))),1)
        with self.assertRaisesRegex(ValueError,'already used'):context.checkpoint('part-001','e1','toolpath','fail','changed',config_path=cfg)
    def test_search_returns_source_and_rejects_unindexed_paths(self):
        r=knowledge.search('CIMCO');self.assertTrue(r)
        self.assertTrue(any('known-failures' in x['path'] for x in r))
        self.assertTrue(knowledge.read(r[0]['path'])['text'])
        with self.assertRaises(ValueError):knowledge.read('../../config.toml')
    def test_snapshot_hashes(self):
        for f in load(ROOT/'ai/aicnc/source-manifest.json')['files']:
            self.assertEqual(sha(ROOT/'ai/aicnc'/f['path']),f['distributed_sha256'],f['path'])
    def test_capp_is_actual_upstream_implementation(self):
        sys.path.insert(0,str(ROOT/'ai/aicnc/projects/07_capp_planner/src'))
        from capp_planner.planner import build_cam_plan
        base=ROOT/'ai/aicnc/schemas/examples'
        plan=build_cam_plan(load(base/'features.example.json'),load(base/'manufacturing_context.example.json'),features_path='features.json',features_sha256='a'*64,context_path='context.json',context_sha256='b'*64,code_commit='c'*40)
        self.assertEqual(plan['schema_version'],'1.1.0');self.assertTrue(plan['setups'])
    def test_examples_validate(self):
        context.validate(load(ROOT/'ai/context/task.example.json'),'task')
    def test_ipc_frames_every_tail_length_without_changing_command(self):
        for length in range(1,201):
            message='RUN D:/'+('a'*length)+'.csx';frame=ipc.encode_command(message)
            self.assertEqual(len(frame)%5,0);self.assertEqual(frame.decode('ascii').strip(),message)
    def test_ipc_rejects_unicode_wire_path_before_transmission(self):
        with self.assertRaisesRegex(ipc.MastercamIpcError,'ASCII'):
            ipc.encode_command('RUN D:/中文/job.csx')
    def test_chinese_sentence_retrieves_sources(self):
        self.assertTrue(knowledge.search('如何检查保存重开后的刀柄碰撞'))
    def active_request(self):
        d=self.workspace/'mastercam';d.mkdir(parents=True)
        (d/'active.json').write_text('{"request_id":"req-1","pid":123}')
        return d
    def test_recovery_refuses_live_host(self):
        d=self.active_request()
        with patch.object(recovery.subprocess,'run',return_value=SimpleNamespace(stdout='"Mastercam.exe","123"\n')):
            with self.assertRaisesRegex(ValueError,'still running'):
                recovery.reconcile({'workspace':str(self.workspace)},'req-1','inspected the native process')
        self.assertTrue((d/'active.json').exists())
    def test_recovery_never_promotes_unknown_to_pass(self):
        d=self.active_request()
        with patch.object(recovery.subprocess,'run',return_value=SimpleNamespace(stdout='INFO: no matching processes')):
            result=recovery.reconcile({'workspace':str(self.workspace)},'req-1','original process exited, evidence preserved')
        self.assertEqual(result['outcome'],'unknown');self.assertFalse(result['replay_authorized'])
        self.assertFalse((d/'active.json').exists());self.assertEqual(len(list((d/'requests/req-1').glob('reconciliation-*.json'))),1)
    def test_recovery_cannot_clear_different_request(self):
        d=self.active_request()
        with self.assertRaisesRegex(ValueError,'Request changed'):
            recovery.reconcile({'workspace':str(self.workspace)},'req-2','original process exited')
        self.assertTrue((d/'active.json').exists())

if __name__=='__main__':unittest.main()
