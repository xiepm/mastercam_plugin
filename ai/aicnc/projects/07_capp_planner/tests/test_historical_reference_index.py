import copy
import json
import unittest
from pathlib import Path
import test_historical_reference as fixtures
from capp_planner.historical_reference_index import compile_index, digest, retrieve_index, validate


class HistoricalReferenceIndexTest(unittest.TestCase):
    def setUp(self):
        fixtures.HistoricalReferenceTest.setUp(self)
        self.catalog_path = self.root/'catalog.json'
        self.plan_path = self.root/'merge_plan.json'
        self.entry = dict(case_id=self.data['case_id'], title=self.data['part_name'],
            library='05_templates/reference_library.json', report='report.md',
            library_sha256=digest(self.library), templates=len(self.data['templates']), status='reference_candidate')
        self.catalog = dict(schema_version='aicnc.local-reference-catalog/0.1', production_enabled=False, cases=[self.entry])
        self.plan = dict(schema_version='aicnc.historical-reference-merge/0.1', production_enabled=False,
            families=[], conflicts=[], gaps=[r['id'] for r in self.data['templates']])

    def save(self):
        fixtures.HistoricalReferenceTest.save(self)

    def build(self):
        self.catalog_path.write_text(json.dumps(self.catalog), 'utf-8')
        self.plan_path.write_text(json.dumps(self.plan), 'utf-8')
        return compile_index(self.catalog_path, self.plan_path)

    def family(self):
        self.data['templates'][0]['kind']='sequence_refinement'
        self.save(); self.entry['library_sha256']=digest(self.library)
        self.plan['families']=[dict(id='spot_chain',title='定位与钻削', summary='保留每个来源的条件，不复制固定数值',members=[self.data['templates'][0]['id']])]
        self.plan['gaps']=[]

    def test_gap_stays_separate_and_query_returns_context(self):
        result=retrieve_index(self.build(), ['螺纹'])
        self.assertFalse(result['families'])
        self.assertEqual(result['gaps'][0]['record']['conditions'], self.data['templates'][0]['conditions'])

    def test_conflict_cannot_be_promoted_by_merge(self):
        self.family();self.data['templates'][0]['kind']='historical_conflict'
        self.save();self.entry['library_sha256']=digest(self.library)
        with self.assertRaisesRegex(ValueError,'unresolved_issue_cannot_be_experience'):self.build()

    def test_duplicate_geometry_is_one_support_and_keeps_variants(self):
        self.family(); other=copy.deepcopy(self.data);other['case_id']='revision-two';other['templates'][0]['id']='revision-two-record'
        other['templates'][0]['conditions']=['Different material must be retained']
        path=self.library.parent/'revision.json';path.write_text(json.dumps(other),'utf-8')
        entry=dict(self.entry,case_id='revision-two',library='05_templates/revision.json',library_sha256=digest(path))
        self.catalog['cases'].append(entry)
        self.plan['families'][0]['members'].append('revision-two-record')
        family=self.build()['families'][0]
        self.assertEqual(family['distinct_geometry_count'],1)
        self.assertEqual(family['source_case_count'],2)
        self.assertEqual(family['variants'][1]['record']['conditions'],other['templates'][0]['conditions'])

    def test_changed_library_rejected_even_with_valid_evidence(self):
        self.data['part_name']='changed';self.save()
        with self.assertRaisesRegex(ValueError,'catalog_library_hash_mismatch'):self.build()

    def test_all_records_need_disposition(self):
        self.plan['gaps']=[]
        with self.assertRaisesRegex(ValueError,'undisposed_records'):self.build()

    def test_unknown_reference_rejected(self):
        self.plan['gaps']=['unknown']
        with self.assertRaisesRegex(ValueError,'unknown_reference_record'):self.build()

    def test_record_not_counted_twice(self):
        self.family();self.plan['gaps']=[self.data['templates'][0]['id']]
        with self.assertRaisesRegex(ValueError,'record_has_multiple_dispositions'):self.build()

    def test_catalog_path_containment(self):
        self.entry['library']='../outside.json'
        with self.assertRaisesRegex(ValueError,'catalog_path_outside_root'):self.build()

    def test_deterministic_and_no_default_for_unmatched_query(self):
        self.assertEqual(self.build(),self.build())
        self.assertFalse(retrieve_index(self.build(),['zzunmatchedzz'])['gaps'])

    def test_contract_examples(self):
        from capp_planner.historical_reference import SCHEMA
        for name in ['historical_reference_merge','historical_reference_index']:
            data=json.loads((SCHEMA.parent/'examples'/f'{name}.example.json').read_text('utf-8'))
            validate(data,name+'.schema.json')
