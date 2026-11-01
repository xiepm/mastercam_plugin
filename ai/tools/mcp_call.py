"""Stdio fallback for the exported P08 runner; preserves the configured bridge."""
import asyncio,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import config,load
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def call(tool,args,c):
    u=c['upstream']
    async with stdio_client(StdioServerParameters(command=u['command'],args=u['args'],env={**os.environ,**u.get('env',{})},cwd=u.get('cwd'))) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize()
            result=await s.list_tools() if tool=='list' else await s.call_tool(tool,args)
            return result.model_dump(mode='json')

if __name__=='__main__':
    if len(sys.argv)<3 or sys.argv[1]!='mastercam':raise SystemExit('Usage: mcp_call.py mastercam <tool> [arguments.json]')
    result=asyncio.run(call(sys.argv[2],load(sys.argv[3]) if len(sys.argv)>3 else {},config()))
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(1 if result.get('isError') else 0)
