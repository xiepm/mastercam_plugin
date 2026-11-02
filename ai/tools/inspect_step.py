"""Run only inside the pinned P01 runtime; no alternate geometry parser."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai/aicnc/projects/01_cad_core/src'))
from cad_core.core import CadDocument

def main():
    p=argparse.ArgumentParser();p.add_argument('--step',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    d=CadDocument.from_step(a.step);summary=d.summary()
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'cad_core.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
    (a.output/'face_bounds.json').write_text(json.dumps({f['face_id']:d.bounding_box_for_face_ids([f['face_id']]) for f in summary['faces']},indent=2),'utf-8')
    print(json.dumps({'faces':len(summary['faces']),'source':summary['source'],'aagnet_run':False}))
if __name__=='__main__':main()
