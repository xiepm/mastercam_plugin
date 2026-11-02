import copy,json,sys,tempfile,unittest,zipfile,hashlib,importlib.util
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai'))
from portable import planning
from portable.common import load,sha,write_new
from portable.knowledge_bundle import export_bundle,import_bundle
from portable.planning_demo import make_knowledge


class PlanningPortable(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='planning space ');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.kb=make_knowledge(self.root/'kb')
        self.work=self.root/'private work';self.home=self.root/'codex'
    def install(self):
        result=planning.install(self.work,self.home,self.kb)
        return planning.config(result['planning_config'])
    def test_install_does_not_touch_other_codex_settings(self):
        self.home.mkdir();p=self.home/'config.toml';p.write_text('model="user-choice"\n','utf-8')
        self.install();before=(self.work/'planning-config.json').read_bytes();self.install()
        self.assertEqual(before,(self.work/'planning-config.json').read_bytes())
        self.assertEqual(p.read_text(),'model="user-choice"\n')
    def test_modified_skill_is_preserved(self):
        self.install();p=self.home/'skills/aicnc-plan-new-part/SKILL.md';p.write_text('customized','utf-8')
        with self.assertRaisesRegex(ValueError,'Custom skill preserved'):self.install()
        self.assertEqual(p.read_text(),'customized')
    def test_receipted_old_skill_is_backed_up(self):
        self.install();p=self.home/'skills/aicnc-plan-new-part/SKILL.md';p.write_text('previous managed version','utf-8')
        receipt=self.home/'skills/aicnc-plan-new-part/references/installed-files.json'
        r=load(receipt);r['files']['SKILL.md']=sha(p);receipt.write_text(json.dumps(r),'utf-8')
        digest=sha(p);self.install()
        self.assertEqual((self.work/'skill-backups'/digest/'SKILL.md').read_text(),'previous managed version')
        self.assertEqual(p.read_bytes(),(ROOT/'ai/skills/aicnc-plan-new-part/SKILL.md').read_bytes())
    def test_missing_knowledge_never_falls_back_to_demo(self):
        r=planning.install(self.work,self.home)
        c=planning.config(r['planning_config'])
        with self.assertRaisesRegex(ValueError,'unconfigured'):planning.knowledge(c)
        self.assertFalse((self.work/'planning').exists())
    def test_relocation_requires_local_reinstall(self):
        self.install();p=self.work/'planning-config.json';c=load(p);c['repository']=str(self.root/'another package');p.write_text(json.dumps(c),'utf-8')
        with self.assertRaisesRegex(ValueError,'Package moved'):planning.config(p)
        self.install();planning.config(p)
        self.assertTrue(list(self.work.glob('planning-config.before-*.json')))
    def test_start_extracts_real_pdf_and_preserves_originals(self):
        import pymupdf
        pdf=self.root/'draw.pdf'
        with pymupdf.open() as d:
            page=d.new_page();page.insert_text((72,72),'2 x D4 THRU; synthetic test');d.save(pdf)
        digest=sha(pdf);c=self.install()
        result=planning.start(c,'pdf-case',ROOT/'ai/samples/planning/plate.step',pdf)
        task=Path(result['directory'])
        self.assertEqual(sha(pdf),digest);self.assertIn('THRU',(task/'drawing-text.txt').read_text())
        self.assertTrue((task/'drawing-previews/page-1.png').exists())
        with self.assertRaises(FileExistsError):planning.start(c,'pdf-case',ROOT/'ai/samples/planning/plate.step',pdf)
    def test_task_output_cannot_escape_workspace(self):
        c=self.install()
        with self.assertRaisesRegex(ValueError,'outside workspace'):planning.scoped(self.root/'out.json',c)
        with self.assertRaises(ValueError):planning.start(c,'../escape',ROOT/'ai/samples/planning/plate.step',ROOT/'ai/samples/planning/drawing.svg')
    def test_bundle_roundtrip_and_hash_guard(self):
        result=export_bundle(self.kb,self.root/'references.zip')
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):import_bundle(result['path'],self.root/'bad','0'*64)
        moved=import_bundle(result['path'],self.root/'moved 中文',result['sha256'])
        self.assertEqual(moved['records'],3)
        self.assertEqual(planning.compile_index(self.kb/'catalog.json',self.kb/'merged/merge_plan.json'),planning.compile_index(Path(moved['knowledge_root'])/'catalog.json',Path(moved['knowledge_root'])/'merged/merge_plan.json'))
        with self.assertRaisesRegex(ValueError,'Destination exists'):import_bundle(result['path'],self.root/'moved 中文',result['sha256'])
    def test_bundle_traversal_rejected_before_writing(self):
        p=self.root/'unsafe.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('../escape.txt','not extracted')
        with self.assertRaisesRegex(ValueError,'Unsafe bundle path'):import_bundle(p,self.root/'destination',sha(p))
        self.assertFalse((self.root/'destination').exists());self.assertFalse((self.root/'escape.txt').exists())
    def test_bundle_entry_hash_mismatch_rejected(self):
        source=export_bundle(self.kb,self.root/'good.zip');p=self.root/'changed.zip'
        with zipfile.ZipFile(source['path']) as original,zipfile.ZipFile(p,'w') as changed:
            for name in original.namelist():changed.writestr(name,b'changed' if name=='catalog.json' else original.read(name))
        with self.assertRaisesRegex(ValueError,'entry hash mismatch'):import_bundle(p,self.root/'destination',sha(p))
        self.assertFalse((self.root/'destination').exists())
    def test_public_replay_and_negative_checks(self):
        spec=importlib.util.spec_from_file_location('accept_planning_test',ROOT/'ai/tools/accept_planning.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.run(self.root/'acceptance')
        self.assertTrue(result['passed']);self.assertEqual(len(result['negative_checks']),3)
        c=planning.config(self.root/'acceptance/private work/planning-config.json')
        task=self.root/'acceptance/private work/planning/synthetic-new-part'
        audit=planning.audit(c,task/'reference_run',task/'review.json',task/'positive-recheck.json')
        self.assertEqual(audit['status'],'complete_with_open_items')

if __name__=='__main__':unittest.main()
