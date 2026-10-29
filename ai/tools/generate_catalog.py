from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text('utf-8-sig'))
modules=read(ROOT/'catalog/modules.json')
manifest=read(ROOT/'catalog/package.json')
knowledge=[]
for path in sorted((ROOT/'ai/knowledge').glob('*.json')):knowledge.extend(read(path))
by_module={r['module']:r for r in knowledge}
doc=(ROOT/'docs/PLUGINS.md').read_text('utf-8-sig')
rows={m[0]:m[1:] for m in re.findall(r'^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|$',doc,re.M)}
caps=[];routes=[]
for m in modules:
    mid=m['id'];k=by_module.get(mid,{})
    display=rows.get(mid,[mid,'See published scope and evidence.'])
    owned=[]
    for rel in m['files']:
        if not rel.lower().endswith('.ft'):continue
        text=(ROOT/'payload'/rel).read_text('utf-8-sig')
        app=re.search(r'APPLICATION\s+"([^"]+)"',text)
        if not app:continue
        for kind,function,body in re.findall(r'FUNCTION\s+(NET|CPP)\s+"([^"]+)"(.*?)END_FUNCTION',text,re.S):
            label=re.search(r'FNAME\s+"([^"]+)"',body)
            r={'application':app[1],'function':function,'kind':kind,'title':label[1] if label else function,'ft':rel,'completion':'Interactive/native route; registration is not evidence of completed business work.'}
            owned.append(r);routes.append(dict(module=mid,**r))
    caps.append({'id':'module.'+mid,'module':mid,'title':display[0],'summary':k.get('summary',display[1]),'automation':'reference','concepts':k.get('concepts',[]),'routes':owned,'usage':k.get('workflows',[]),'scope':display[1],'files':m['files']})
    for w in k.get('workflows',[]):
        caps.append({'id':mid+'.'+w['id'],'module':mid,'title':w['title'],'summary':w['when'],'automation':'interactive' if w['automation']=='interactive' else 'reference','source_api_status':w['automation'],**{a:b for a,b in w.items() if a not in ('id','title','when','automation')}})
typed=[('operation.depth','OperationTools2027','工序深度','按明确的刀具平面绝对/增量深度修改工序。'),('operation.finish','OperationTools2027','2D 粗转精','现有平底刀、补偿侧、切削数据与分层参数明确后修改。'),('operation.chamfer','OperationTools2027','2D 倒角','现有倒角刀、角度、宽度与深度明确后修改。'),('hsm.pocket','HSMRebuild2027','新建原生挖槽','沿参考工序的完整单闭合平面链创建挖槽，不过滤原生链列表。'),('mp.sections','MPRebuild2027','任意平面截面/平行切片','以世界坐标平面和公差分析实体网格；确认后生成结果线。'),('mp.draft','MPRebuild2027','网格拔模分析/分区边/法线','分析绕序法向，不等同倒扣可见性或完整分模。')]
for action,module,title,summary in typed:
    caps.append({'id':'typed.'+action,'module':module,'title':title,'summary':summary,'automation':'typed','action':action,'tool':'mc_prepare_change','preconditions':['先 mc_inspect，核对已保存文档与单位、真实 ID。','只使用用户或工艺依据提供的参数。','填写完整类型化请求；先检查具体预览，再按授权执行。'],'steps':['mc_prepare_change','检查 preview 与源对象','mc_apply_plan','核对 ok、status、result','需要时 mc_rollback_plan'],'limits':['不自动保存、后处理或机床仿真。','原生计划仅当前宿主会话，预览 15 分钟有效。','参数回滚不恢复原刀路计算状态。'],'schema':'mc_prepare_change inputSchema request discriminator action','evidence':['validation/bundle-host-integration.json','validation/README.md'],'adapter_validation':'See ai/validation; existing plugin evidence alone does not validate this adapter.'})
    source={'operation.depth':'op.depth','operation.finish':'op.finish','operation.chamfer':'op.chamfer','hsm.pocket':'hsm.create','mp.sections':'mp_section','mp.draft':'mp_draft'}[action]
    caps[-1]['business_contract']=module+'.'+source
    if action.startswith('mp.'):
        caps[-1]['analysis_only_steps']=['mc_prepare_change','读取 preview 和 result.analysis_path；生成报告文件但不建图素','仅分析意图到此结束；可 discard 未执行计划']
        caps[-1]['steps']=['mc_prepare_change','读取分析报告；只有明确创建结果图素的意图才继续','mc_apply_plan','核对 ok、status、result.created_ids','需要时 mc_rollback_plan']
external=by_module.get('CIMCO',by_module.get('CIMCOVerify',{}))
caps.append({'id':'module.CIMCO','module':'CIMCO','title':'CIMCO Verify','summary':external.get('summary','官方 Mastercam 仿真插件；本合集提供联网安装，未提供其材料去除/碰撞的结构化调用 API。'),'automation':'interactive','usage':external.get('workflows',[]),'limits':['界面打开或安装验证不能声称仿真通过。','结果需读取真实仿真报告或明确界面证据。'],'routes':[{'application':'CIMCO','function':'UI','completion':'Use installed CIMCO Verify ribbon; no guessed FT command.'}]})
out=ROOT/'ai/catalog';out.mkdir(parents=True,exist_ok=True)
data={'version':'1.0.0','plugin_release':manifest['version'],'module_count':len(modules),'capability_count':len(caps),'ft_route_count':len(routes),'typed_actions':[r[0] for r in typed],'capabilities':caps,'routes':routes}
(out/'capabilities.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
identity=read(ROOT/'ai/bridge/identity.json')
assert identity['sha256']==hashlib.sha256((ROOT/'ai/bridge/bin'/identity['file']).read_bytes()).hexdigest().upper()
print(json.dumps({k:data[k] for k in ('module_count','capability_count','ft_route_count','typed_actions')}))
