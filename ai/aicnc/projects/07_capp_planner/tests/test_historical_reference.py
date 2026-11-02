import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from jsonschema import ValidationError
from capp_planner.historical_reference import SCHEMA, read_library, retrieve


class HistoricalReferenceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.library=self.root/'05_templates/reference_library.json'
        self.library.parent.mkdir()
        self.data=json.loads((SCHEMA.parent/'examples/historical_process_reference.example.json').read_text(encoding='utf-8'))
        target=self.root/'02_initial_plan/独立工艺初稿.md'
        target.parent.mkdir();target.write_bytes(b'frozen independent planning')
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        self.data['evidence'][0]['sha256']=digest
        self.data['frozen_initial_plan_sha256']=digest
        self.save()

    def save(self):
        self.library.write_text(json.dumps(self.data),encoding='utf-8')

    def test_retrieval_keeps_conditions_and_candidate_status(self):
        rows=retrieve(read_library(self.library),['螺纹'])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'reference_candidate')
        self.assertFalse(rows[0]['production_enabled'])
        self.assertTrue(rows[0]['exclusions'])
        self.assertEqual(rows[0]['applicability'],'must_compare_conditions')

    def test_changed_frozen_evidence_fails(self):
        (self.root/'02_initial_plan/独立工艺初稿.md').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'evidence_hash_mismatch'):read_library(self.library)

    def test_no_promotion_to_production(self):
        self.data['templates'][0]['production_enabled']=True;self.save()
        with self.assertRaises(ValidationError):read_library(self.library)

    def test_unknown_evidence_is_rejected(self):
        self.data['templates'][0]['evidence_paths']=['unproven.json'];self.save()
        with self.assertRaisesRegex(ValueError,'template_evidence_missing'):read_library(self.library)

    def test_outside_case_file_is_rejected(self):
        self.data['evidence'][0]['path']='../../outside.txt';self.save()
        with self.assertRaisesRegex(ValueError,'evidence_path_outside_case'):read_library(self.library)

    def test_ambiguous_duplicate_template_id_is_rejected(self):
        self.data['templates'].append(copy.deepcopy(self.data['templates'][0]));self.save()
        with self.assertRaisesRegex(ValueError,'duplicate_template_id'):read_library(self.library)

    def test_no_hit_does_not_return_a_default_strategy(self):
        self.assertEqual(retrieve(read_library(self.library),['不存在的工艺']),[])


if __name__=='__main__':unittest.main()
