"""Reconcile an abandoned IPC marker after all Mastercam hosts have exited.

The outcome remains unknown. This does not approve replay or machining.
"""
import argparse,csv,io,json,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import config,load,token,write_new
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from runtime import process_guard

def reconcile(c,request_id,reason):
    token(request_id)
    if len(reason.strip())<5:raise ValueError('A reconciliation reason is required')
    base=Path(c['workspace'])/'mastercam'
    with process_guard(base/'native.lock'):
        active=load(base/'active.json')
        if active['request_id']!=request_id:raise ValueError('Request changed; inspect it again')
        result=subprocess.run(['tasklist','/FI','IMAGENAME eq Mastercam.exe','/FO','CSV','/NH'],capture_output=True,text=True,encoding='mbcs',errors='strict',timeout=10,check=True)
        if any(r and r[0].lower()=='mastercam.exe' for r in csv.reader(io.StringIO(result.stdout))):
            raise ValueError('Mastercam still running; reconcile the host first, never force replay')
        record={'request_id':request_id,'previous':active,'outcome':'unknown',
                'host_exited':True,'reason':reason,'replay_authorized':False}
        write_new(base/'requests'/request_id/('reconciliation-'+uuid.uuid4().hex+'.json'),record)
        (base/'active.json').unlink()
        return record

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--request-id',required=True);p.add_argument('--reason',required=True)
    a=p.parse_args();print(json.dumps(reconcile(config(a.config),a.request_id,a.reason),ensure_ascii=False))
if __name__=='__main__':main()
