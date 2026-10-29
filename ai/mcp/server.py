"""Mastercam plugin knowledge and typed execution MCP. Run with Python >=3.11."""
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from typing import Annotated, Literal
from models import ChangeRequest, Ids
from runtime import Runtime, ROOT, load

mcp=FastMCP('mastercam-plugins',instructions='Use mc_catalog and mc_capability to select verified plugin workflows. mc_inspect returns actual IDs/units. Typed writes are prepare -> review concrete preview -> apply -> inspect readback, with same-session explicit rollback. Only ok=true is success; unknown requests must be queried, never blindly repeated. No machining/post/collision certification is implied. UI-only functions are not headless actions.')
runtime=Runtime()
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=False)

def catalog():return load(ROOT/'ai/catalog/capabilities.json')

@mcp.tool(annotations=READ)
def mc_catalog(query:str='',automation:Literal['all','typed','interactive','reference']='all',offset:Annotated[int,Field(ge=0)]=0,limit:Annotated[int,Field(ge=1,le=100)]=30)->dict:
    """Search plugin meanings, use cases, supported limits and invocation routes without opening Mastercam."""
    data=catalog();q=query.casefold()
    rows=[r for r in data['capabilities'] if (not q or q in json.dumps(r,ensure_ascii=False).casefold()) and (automation=='all' or r['automation']==automation)]
    page=rows[offset:offset+limit]
    return {'catalog_version':data['version'],'count':len(rows),'returned':len(page),'next_offset':offset+limit if offset+limit<len(rows) else None,'capabilities':[{k:r[k] for k in ('id','module','title','summary','automation')} for r in page]}

@mcp.tool(annotations=READ)
def mc_capability(capability_id:str)->dict:
    """Get actual preconditions, parameter meanings, steps, effects, rollback and evidence for a capability. Interactive routes require UI work; an FT label is not a callable data API."""
    rows=[r for r in catalog()['capabilities'] if r['id']==capability_id]
    if len(rows)!=1:raise ValueError('Unknown capability; search mc_catalog first')
    return rows[0]

@mcp.tool(annotations=READ)
async def mc_inspect()->dict:
    """Read active saved path, units, native operation/tool IDs, ViewID frames, visible occupied levels, selected solids and up to 250 geometry records. Does not open/save a document."""
    return await runtime.call('inspect')

@mcp.tool(annotations=READ)
async def mc_operation_information(expected_document:str,operation_ids:Ids,obstacle_top:float|None=None,clearance_margin:float|None=None)->dict:
    """Read fresh cycle/extents information and optional axial reach lower bound. obstacle_top is local tool-plane Z; this is not collision checking. Restores operation selection."""
    if len(set(operation_ids))!=len(operation_ids):raise ValueError('Duplicate operation IDs')
    if (obstacle_top is None)!=(clearance_margin is None):raise ValueError('Provide both reach parameters or neither')
    reach=None if obstacle_top is None else {'ObstacleTopInToolPlane':obstacle_top,'ClearanceMargin':clearance_margin}
    if reach is not None:
        import math
        if not all(math.isfinite(x) for x in (obstacle_top,clearance_margin)) or clearance_margin<0:raise ValueError('Reach inputs must be finite and margin nonnegative')
    return await runtime.call('information',{'expected_document':expected_document,'operation_ids':operation_ids,'reach':reach})

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
async def mc_prepare_change(request:ChangeRequest)->dict:
    """Prepare ten typed workflows, including Porsche projection, contour machining, healed copies and complex holes, without applying database edits. Returns preview, plan_id and preview_sha256. Geometry analysis may write STL/JSON artifacts and restores source selection. Values must come from user/engineering context. Plans expire after 15 minutes and reject changed document/objects/selection/context."""
    return await runtime.call('prepare',request.model_dump())

@mcp.tool(annotations=WRITE)
async def mc_apply_plan(plan_id:str,preview_sha256:str,expected_document:str,request_id:str)->dict:
    """Apply an authorized preview once; repeat request_id returns its immutable receipt. Porsche contour/holes regenerate only when their explicit Regenerate parameter is true. Other actions do not regenerate. No posting, saving or collision certification. Read ok/status and actual native results."""
    return await runtime.call('apply',dict(plan_id=plan_id,preview_sha256=preview_sha256,expected_document=expected_document),request_id)

@mcp.tool(annotations=WRITE)
async def mc_rollback_plan(plan_id:str,expected_document:str,request_id:str)->dict:
    """Restore/delete only objects owned by an applied plan in the same host session. Refuses conflicting later edits or saved-file changes. Parameter rollback does not restore previously calculated toolpaths; recalculate as appropriate."""
    return await runtime.call('rollback',dict(plan_id=plan_id,expected_document=expected_document),request_id)

@mcp.tool(annotations=WRITE)
async def mc_regenerate_hsm_plan(plan_id:str,expected_document:str,request_id:str)->dict:
    """Regenerate only the new operation owned by an applied HSM plan. Native false remains failure; fresh Dirty and parameter checks must pass. Not a simulation or NC approval."""
    return await runtime.call('regenerate',dict(plan_id=plan_id,expected_document=expected_document),request_id)

@mcp.tool(annotations=READ)
async def mc_plan_status(plan_id:str)->dict:
    """Read native plan status and stored detailed readbacks. Plans do not survive Mastercam restart; call mc_request_status first after a timeout."""
    return await runtime.call('plan_status',{'plan_id':plan_id})

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
async def mc_discard_plan(plan_id:str)->dict:
    """Discard an unapplied preview; does not edit the Mastercam database or delete analysis artifacts."""
    return await runtime.call('discard',{'plan_id':plan_id})

@mcp.tool(annotations=READ)
def mc_request_status(request_id:str)->dict:
    """Read the immutable receipt for this request from disk, including after timeout or MCP restart. This is not the latest plan state; mc_plan_status reads that. unknown_or_running is not failure or permission to repeat a mutation."""
    return runtime.status(request_id)

@mcp.resource('mastercam-plugins://capabilities')
def capabilities_resource()->str:return json.dumps(catalog(),ensure_ascii=False)

if __name__=='__main__':mcp.run(transport='stdio')
