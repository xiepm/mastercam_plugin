"""Exercise the real stdio endpoints and cross-session task recovery, without CAM edits."""
import argparse,asyncio,json,os,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT,config,scoped,write_new
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def request(c,tool=None,args=None,upstream=False):
    server=c['upstream'] if upstream else {'command':sys.executable,'args':[str(ROOT/'ai/mcp/server.py')],
        'env':{'MC_PLUGIN_AI_CONFIG':os.environ['MC_PLUGIN_AI_CONFIG']}}
    params=StdioServerParameters(command=server['command'],args=server['args'],env={**os.environ,**server.get('env',{})})
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as client:
            await client.initialize()
            if tool is None:return [t.name for t in (await client.list_tools()).tools]
            response=await client.call_tool(tool,args or {})
            if response.isError:raise RuntimeError(str(response))
            return response.structuredContent or json.loads(response.content[0].text)

async def run(c,d):
    checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    names=await request(c);check('plugin_mcp_19_tools',len(names)==19)
    names=await request(c,upstream=True);check('base_mcp_9_tools',len(names)==9)
    found=await request(c,'mc_knowledge_search',{'query':'5 mm','limit':8})
    check('knowledge_search_has_sources',bool(found['results']))
    doc=await request(c,'mc_knowledge_read',{'path':found['results'][0]['path']})
    check('knowledge_source_readback',bool(doc['text']))
    # Deliberately empty exchange file: tests the context ledger, not CAD validity.
    fixture=d/'ledger-only.step';fixture.write_text('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')
    task_id='acceptance-'+uuid.uuid4().hex[:12]
    task=await request(c,'mc_task_create',{'task_id':task_id,'source_path':str(fixture),
        'goal':'Test context persistence only; no machining','requirements':{'simulation_only':True}})
    check('task_source_copied',task['source_unchanged'])
    directory=Path(task['directory']);binding=directory/'binding.json';binding.write_text('{"revision":1}')
    proof=directory/'ledger-readback.json';write_new(proof,{'context_test_only':True})
    kwargs={'task_id':task_id,'event_id':'input-read','stage':'input','state':'pass',
        'summary':'Ledger-only input copy verified; geometry has not been parsed',
        'artifacts':[str(proof)],'bindings':{'plan':str(binding)},'next_action':'Supply a real CAD part for native acceptance'}
    first=await request(c,'mc_task_checkpoint',kwargs)
    check('checkpoint_saved',first['stages']['input']['state']=='pass')
    resumed=await request(c,'mc_task_resume',{'task_id':task_id})
    check('new_stdio_session_resume',resumed['stages']['input']['state']=='pass')
    check('unexecuted_material_stage_pending',resumed['stages']['material_simulation']['state']=='pending')
    binding.write_text('{"revision":2}')
    changed=await request(c,'mc_task_resume',{'task_id':task_id})
    check('changed_binding_invalidates_pass',changed['stages']['input']['state']=='unknown')
    check('production_not_released',changed['production_released'] is False)
    result={'passed':True,'checks':checks,'check_count':len(checks),'native_executed':False,'other_pc_tested':False}
    write_new(d/'stdio-acceptance.json',result);print(json.dumps(result))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--directory',required=True)
    a=p.parse_args();c=config(a.config);os.environ['MC_PLUGIN_AI_CONFIG']=a.config
    d=scoped(a.directory,c);d.mkdir(parents=True,exist_ok=False);asyncio.run(run(c,d))
if __name__=='__main__':main()
