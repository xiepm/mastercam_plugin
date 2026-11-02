"""Portable planning entry: start from STEP/drawing paths, prepare, audit."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable import planning


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['install','doctor','start','geometry','prepare','audit'])
    p.add_argument('--config');p.add_argument('--workspace');p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    p.add_argument('--knowledge-root');p.add_argument('--python');p.add_argument('--p01-python');p.add_argument('--p01-distro',default='Ubuntu-22.04')
    for name in ['task-id','step','drawing','task','intake','run-dir','review','output']:p.add_argument('--'+name)
    a=p.parse_args()
    def require(*names):
        for name in names:
            if not getattr(a,name):p.error('--'+name.replace('_','-')+' is required')
    try:
        if a.action=='install':
            require('workspace')
            result=planning.install(a.workspace,a.codex_home,a.knowledge_root,a.python,a.p01_python,a.p01_distro)
        else:
            require('config');c=planning.config(a.config)
            if a.action=='doctor':
                planning.verify_snapshot()
                planning.knowledge(c)
                result={'passed':True,'knowledge_configured':True,'geometry_configured':c['p01'] is not None,'native_tested':False}
            elif a.action=='start':
                require('task_id','step','drawing');result=planning.start(c,a.task_id,a.step,a.drawing)
            elif a.action=='geometry':
                require('task');result=planning.geometry(c,a.task)
            elif a.action=='prepare':
                require('intake','run_dir');result=planning.prepare(c,a.intake,a.run_dir)
            else:
                require('run_dir','review','output');result=planning.audit(c,a.run_dir,a.review,a.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result.get('status')=='incomplete' else 0
    except Exception as e:
        print(json.dumps({'status':'error','error_type':type(e).__name__,'message':getattr(e,'message',str(e))},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
