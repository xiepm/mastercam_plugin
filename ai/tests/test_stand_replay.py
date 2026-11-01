"""Adversarial receipt checks; these synthetic fixtures are NOT native evidence."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai/aicnc/projects/08_mastercam_bridge/src'))
from mastercam_bridge import stand_replay as s


class StandReplay(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.d=Path(self.temp.name)
        (self.d/s.MODEL).write_bytes(b'synthetic MCAM test placeholder')
        (self.d/'target.stl').write_bytes(b'synthetic target test placeholder')
        self.labels=('initial','cold1','cold2')
        for i,label in enumerate(self.labels):
            state=dict(pid=i+1,model_sha256=s.p.digest(self.d/s.MODEL),machine_name='synthetic',
                       stock={},operations=[{'tool_diameter':4}],view_sheets=[])
            self.write(label+'-readback',state)
            assembly=dict(IsCollisionChecked=True,RapidCollisionReportSuppressed=False,RemovesMaterial=False)
            final=dict(ok=True,pid=i+1,model_path=str(self.d/s.MODEL),target_sha256=s.p.digest(self.d/'target.stl'),
                motion=dict(completed=True,input_complete=True,is_running=False,is_busy=False,operation_count=9,num_moves=233,position={'Index':232}),
                checks=dict(enabled=True,between_moves=True),quality_policy=dict(adaptive_quality_disabled=True,allow_auto_adjust_precision=False),
                report_groups=[],collision_options={'CheckStockAgainstMillingHolder':True},stock_to_world=[],
                verifiers=[dict(precision_mm=.005,cutting_tolerance_mm=.005,collision_tolerance_mm=.02,holder_tolerance_mm=.02,
                    gouges=[],excess=[],target_count=1,gouge_threshold_mm=-.02,excess_threshold_mm=.02,
                    holder=assembly,shaft=assembly,arbor=assembly)])
            self.write(label+'-export',final)
            (self.d/(label+'-ipw.stl')).write_bytes(b'identical synthetic remainder')
    def write(self,name,value):
        (self.d/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    def mutate(self,name,fn):
        value=s.p.load(self.d/(name+'.json'));fn(value);self.write(name,value)
    def test_equivalence_contract(self):
        self.assertTrue(s.verify_replays(self.d)['passed'])
    def test_changed_model_rejected(self):
        (self.d/s.MODEL).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'MCAM changed'):s.verify_replays(self.d)
    def test_warm_reopen_rejected(self):
        self.mutate('cold1-readback',lambda x:x.update(pid=1))
        with self.assertRaisesRegex(ValueError,'distinct processes'):s.verify_replays(self.d)
    def test_tool_drift_rejected(self):
        self.mutate('cold1-readback',lambda x:x['operations'][0].update(tool_diameter=10))
        with self.assertRaisesRegex(ValueError,'parameters changed'):s.verify_replays(self.d)
    def test_material_drift_rejected(self):
        (self.d/'cold2-ipw.stl').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'material result differs'):s.verify_replays(self.d)
    def test_disabled_holder_rejected(self):
        self.mutate('cold1-export',lambda x:x['verifiers'][0]['holder'].update(IsCollisionChecked=False))
        with self.assertRaisesRegex(ValueError,'Assembly collision'):s.verify_replays(self.d)
    def test_gouge_rejected(self):
        self.mutate('cold1-export',lambda x:x['verifiers'][0].update(gouges=[{'synthetic':True}]))
        with self.assertRaisesRegex(ValueError,'deviation report'):s.verify_replays(self.d)
    def test_collision_rejected(self):
        self.mutate('cold2-export',lambda x:x.update(report_groups=[{'synthetic':True}]))
        with self.assertRaisesRegex(ValueError,'collision report'):s.verify_replays(self.d)
    def test_incomplete_motion_rejected(self):
        self.mutate('cold1-export',lambda x:x['motion'].update(num_moves=232))
        with self.assertRaisesRegex(ValueError,'coverage changed'):s.verify_replays(self.d)
    def test_target_binding_rejected(self):
        self.mutate('cold1-export',lambda x:x.update(target_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'Target changed'):s.verify_replays(self.d)
    def test_precision_drift_rejected(self):
        self.mutate('cold1-export',lambda x:x['verifiers'][0].update(precision_mm=.1))
        with self.assertRaisesRegex(ValueError,'Tolerance readback'):s.verify_replays(self.d)


if __name__=='__main__':unittest.main()
