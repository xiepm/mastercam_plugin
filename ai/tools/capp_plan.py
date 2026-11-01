"""Run the existing exported P07 planner on explicit features/context."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT,load,sha,write_new
sys.path.insert(0,str(ROOT/'ai/aicnc/projects/07_capp_planner/src'))
from capp_planner.planner import build_cam_plan

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--features',required=True);p.add_argument('--context',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    features=Path(a.features).resolve();context=Path(a.context).resolve();out=Path(a.output).resolve()
    manifest=load(ROOT/'ai/aicnc/source-manifest.json')
    result=build_cam_plan(load(features),load(context),features_path=os.path.relpath(features,out.parent),features_sha256=sha(features),context_path=os.path.relpath(context,out.parent),context_sha256=sha(context),code_commit=manifest['upstream_base_commit'])
    write_new(out,result)
    print(json.dumps({'path':str(out),'status':result['status'],'setups':len(result['setups']),'operations':sum(len(s['operations']) for s in result['setups']),'unplanned_features':result['unplanned_features'],'native_executed':False},ensure_ascii=False))
    return 1 if result['unplanned_features'] else 0
if __name__=='__main__':raise SystemExit(main())
