import copy
import json
from pathlib import Path
import tempfile
import unittest
from capp_planner.historical_reference_index import digest
from capp_planner.planning_reference_workflow import prepare,audit,read,validate,ROOT


class PlanningReferenceWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.kb=self.root/'kb';case=self.kb/'cases/synthetic'
        (case/'02_initial_plan').mkdir(parents=True)
        frozen=case/'02_initial_plan/独立工艺初稿.md';frozen.write_text('initial independent plan','utf8')
        lib=read(ROOT/'schemas/examples/historical_process_reference.example.json')
        lib['case_id']='synthetic';lib['source_step_sha256']='1'*64
        lib['frozen_initial_plan_sha256']=digest(frozen)
        lib['evidence']=[dict(path='02_initial_plan/独立工艺初稿.md',sha256=digest(frozen))]
        base=lib['templates'][0];lib['templates']=[]
        for name,kind in [('experience','agreement_refinement'),('conflict','historical_conflict'),('gap','missing_stage')]:
            t=copy.deepcopy(base);t.update(id=name,kind=kind,title='孔加工'+name,tags=['孔'])
            lib['templates'].append(t)
        self.libpath=case/'05_templates/reference_library.json';self.libpath.parent.mkdir()
        self.write(self.libpath,lib)
        self.entry=dict(case_id='synthetic',title='synthetic',library='cases/synthetic/05_templates/reference_library.json',report='cases/synthetic/report.md',library_sha256=digest(self.libpath),templates=3,status='reference_candidate')
        self.write(self.kb/'catalog.json',dict(schema_version='aicnc.local-reference-catalog/0.1',production_enabled=False,cases=[self.entry]))
        self.write(self.kb/'merged/merge_plan.json',dict(schema_version='aicnc.historical-reference-merge/0.1',production_enabled=False,families=[dict(id='holes',title='孔加工',summary='Conditional stages',members=['experience'])],conflicts=['conflict'],gaps=['gap']))
        (self.root/'part.step').write_bytes(b'synthetic-step-fixture')
        (self.root/'drawing.pdf').write_bytes(b'synthetic-drawing-fixture')
        self.intake=read(ROOT/'schemas/examples/planning_reference_intake.example.json')
        self.intake['sources'][0]['path']='part.step';self.intake['sources'][1]['path']='drawing.pdf'
        self.intake['requirements'][0]['tags']=['孔'];self.intake['known_unknowns']=[]
        self.inputpath=self.root/'intake.json';self.write(self.inputpath,self.intake)
        self.run=self.root/'run';prepare(self.inputpath,self.run,self.kb)
        (self.root/'plan.md').write_text('## P01 孔加工\nR01 through-hole route. family:holes selected source experience\n','utf8')
        evidence=[dict(source_id='drawing',locator='page 1 hole callout')]
        common=dict(reason='New drawing supports this condition; evaluated explicitly',requirement_ids=['R01'],plan_sections=['P01'],evidence=evidence)
        self.review=dict(schema_version='aicnc.planning-reference-review/0.1',packet_sha256=digest(self.run/'packet.json'),plan_path='plan.md',requirement_reviews=[dict(requirement_id='R01',status='addressed',reason='Hole route covered in the plan',plan_sections=['P01'],evidence=evidence)],reference_decisions=[dict(common,reference_id='family:holes',disposition='adapt',selected_source_ids=['experience']),dict(common,reference_id='conflict',disposition='not_applicable',selected_source_ids=[]),dict(common,reference_id='gap',disposition='unresolved',selected_source_ids=[])],additional_findings=[])
        self.reviewpath=self.root/'review.json'

    def write(self,p,data):
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf8')

    def check(self):
        self.write(self.reviewpath,self.review)
        return audit(self.run,self.reviewpath,self.kb)

    def test_prepare_auto_retrieves_and_audit_records_adoption(self):
        packet=read(self.run/'packet.json')
        self.assertEqual(packet['terms'],['孔']);self.assertEqual(len(packet['references']),3)
        result=self.check();self.assertEqual(result['status'],'complete_with_open_items')
        self.assertEqual(result['selected_template_ids'],['experience']);self.assertFalse(result['ready_for_cam_execution'])

    def test_missing_conflict_review_is_incomplete(self):
        self.review['reference_decisions'].pop(1)
        self.assertIn('unreviewed_reference: conflict',self.check()['errors'])

    def test_missing_requirement_is_incomplete(self):
        self.review['requirement_reviews']=[]
        self.assertIn('unreviewed_requirement: R01',self.check()['errors'])

    def test_claimed_coverage_without_requirement_in_plan_fails(self):
        (self.root/'plan.md').write_text('## P01 unrelated\nNo matching requirement here','utf8')
        self.assertIn('requirement_not_in_cited_plan_section: R01',self.check()['errors'])

    def test_cannot_adopt_conflicting_parameter_as_experience(self):
        self.review['reference_decisions'][1]['disposition']='adopt'
        self.assertIn('invalid_disposition_for_category: conflict',self.check()['errors'])

    def test_fabricated_template_id_fails(self):
        self.review['reference_decisions'][0]['selected_source_ids']=['invented']
        self.assertIn('unknown_selected_template: family:holes',self.check()['errors'])

    def test_changed_input_fails(self):
        source=read(self.run/'packet.json')['sources'][0]
        (self.run/source['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source_hash_mismatch'):self.check()

    def test_changed_packet_fails(self):
        p=read(self.run/'packet.json');p['terms']=['new'];self.write(self.run/'packet.json',p)
        with self.assertRaisesRegex(ValueError,'packet_hash_mismatch'):self.check()

    def test_same_step_excluded(self):
        lib=read(self.libpath);lib['source_step_sha256']=digest(self.root/'part.step');self.write(self.libpath,lib)
        self.entry['library_sha256']=digest(self.libpath)
        cat=read(self.kb/'catalog.json');cat['cases']=[self.entry];self.write(self.kb/'catalog.json',cat)
        prepare(self.inputpath,self.root/'another_run',self.kb)
        self.assertEqual(read(self.root/'another_run/packet.json')['references'],[])

    def test_knowledge_update_requires_new_snapshot(self):
        lib=read(self.libpath);lib['part_name']='revision';self.write(self.libpath,lib)
        self.entry['library_sha256']=digest(self.libpath)
        cat=read(self.kb/'catalog.json');cat['cases']=[self.entry];self.write(self.kb/'catalog.json',cat)
        with self.assertRaisesRegex(ValueError,'knowledge_changed'):self.check()

    def test_evidence_must_be_bound_to_input(self):
        self.review['reference_decisions'][0]['evidence'][0]['source_id']='unbound'
        with self.assertRaisesRegex(ValueError,'unknown_source_id'):self.check()

    def test_existing_run_not_overwritten(self):
        with self.assertRaisesRegex(ValueError,'run_directory_exists'):prepare(self.inputpath,self.run,self.kb)

    def test_original_unknowns_not_silently_cleared(self):
        self.intake['known_unknowns']=['actual stock unknown'];self.write(self.inputpath,self.intake)
        self.run=self.root/'run_unknown';prepare(self.inputpath,self.run,self.kb)
        self.review['packet_sha256']=digest(self.run/'packet.json')
        result=self.check();self.assertIn('input_unknown_001',[x['id'] for x in result['open_items']])

    def test_synthetic_contract_examples(self):
        for kind in ['intake','packet','review','audit']:
            validate(read(ROOT/f'schemas/examples/planning_reference_{kind}.example.json'),kind)
