import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.knowledge_bundle import export_bundle,import_bundle

def main():
    p=argparse.ArgumentParser(description='Local private-reference export/import; no network upload')
    sub=p.add_subparsers(dest='action',required=True)
    ex=sub.add_parser('export');ex.add_argument('--knowledge-root',required=True);ex.add_argument('--output',required=True)
    im=sub.add_parser('import');im.add_argument('--archive',required=True);im.add_argument('--destination',required=True);im.add_argument('--sha256',required=True)
    a=p.parse_args()
    result=export_bundle(a.knowledge_root,a.output) if a.action=='export' else import_bundle(a.archive,a.destination,a.sha256)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
