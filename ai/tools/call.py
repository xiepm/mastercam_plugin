"""Exercise the actual stdio MCP server before the AI client reloads its tools."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('tool');p.add_argument('--arguments');p.add_argument('--config');p.add_argument('--output');a=p.parse_args()
async def main():
    env={**os.environ,'PYTHONUTF8':'1'}
    if a.config:env['MC_PLUGIN_AI_CONFIG']=a.config
    args=json.loads(Path(a.arguments).read_text('utf-8-sig')) if a.arguments else {}
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'ai/mcp/server.py')],env=env)) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize()
            result=await s.list_tools() if a.tool=='list' else await s.call_tool(a.tool,args)
            value=result.model_dump(mode='json')
            if a.output:Path(a.output).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            data=value.get('structuredContent')
            if data is None and value.get('content'):
                try:data=json.loads(value['content'][0]['text'])
                except (ValueError,KeyError):pass
            if a.tool=='list':print(json.dumps({'count':len(value['tools']),'tools':[t['name'] for t in value['tools']]}))
            elif a.output:print(json.dumps({'saved':a.output,'isError':value.get('isError'),'ok':(data or {}).get('ok'),'request_id':(data or {}).get('request_id')}))
            else:print(json.dumps(value,ensure_ascii=True,indent=2))
            return 1 if value.get('isError') or (data or {}).get('ok') is False else 0
raise SystemExit(asyncio.run(main()))
