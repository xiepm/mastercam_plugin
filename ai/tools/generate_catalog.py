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
typed += [('porsche.project_boundary','PorscheAdvanced2027','保时捷实体自动轮廓/投影边界','按已有 ViewID 投影可见实体，保留凹形、内孔和分离区域；只生成闭合边界线。'),('porsche.contour','PorscheAdvanced2027','保时捷自动轮廓粗/精/倒角','实体投影后生成三道真实工序；可创建缺少刀具，并按显式 Regenerate 计算刀路。'),('porsche.heal_holes','PorscheAdvanced2027','保时捷自动删孔补面','按主孔半径闭区间选择完整孔，在独立实体副本上原生删面补面；保留原实体。'),('porsche.holes','PorscheAdvanced2027','保时捷复杂孔自动建工序','识别实际孔段，创建中心钻/钻孔/沉孔/沉头工序及缺少刀具、孔轴平面。')]
geometry_actions=read(ROOT/'ai/workflows/geometry-actions.json')
typed += [row[:4] for row in geometry_actions]
geometry_sources={row[0]:row[4] for row in geometry_actions}
for action,module,title,summary in typed:
    caps.append({'id':'typed.'+action,'module':module,'title':title,'summary':summary,'automation':'typed','action':action,'tool':'mc_prepare_change','preconditions':['先 mc_inspect，核对已保存文档与单位、真实 ID。','只使用用户或工艺依据提供的参数。','填写完整类型化请求；先检查具体预览，再按授权执行。'],'steps':['mc_prepare_change','检查 preview 与源对象','mc_apply_plan','核对 ok、status、result','需要时 mc_rollback_plan'],'limits':['不自动保存、后处理或机床仿真。','原生计划仅当前宿主会话，预览 15 分钟有效。','参数回滚不恢复原刀路计算状态。'],'schema':'mc_prepare_change inputSchema request discriminator action','evidence':['validation/bundle-host-integration.json','validation/README.md'],'adapter_validation':'See ai/validation; existing plugin evidence alone does not validate this adapter.'})
    source={**geometry_sources,'operation.depth':'op.depth','operation.finish':'op.finish','operation.chamfer':'op.chamfer','hsm.pocket':'hsm.create','mp.sections':'mp_section','mp.draft':'mp_draft','porsche.project_boundary':'porsche.project','porsche.contour':'porsche.boundary_sequence','porsche.heal_holes':'porsche.heal','porsche.holes':'porsche.holes'}[action]
    caps[-1]['business_contract']=module+'.'+source
    if action in ('mp.sections','mp.draft'):
        caps[-1]['analysis_only_steps']=['mc_prepare_change','读取 preview 和 result.analysis_path；生成报告文件但不建图素','仅分析意图到此结束；可 discard 未执行计划']
        caps[-1]['steps']=['mc_prepare_change','读取分析报告；只有明确创建结果图素的意图才继续','mc_apply_plan','核对 ok、status、result.created_ids','需要时 mc_rollback_plan']
    if action.startswith('porsche.'):
        caps[-1]['workflow_contract']='ai/workflows/porsche.json'
        caps[-1]['adapter_validation']='ai/validation/porsche-native-acceptance.json'
        caps[-1]['limits']+=['原生私有几何接口只接受已验证 API29/MCCORE/MCGeomSld/PSKERNEL 构建。','副本补面不覆盖原实体；完整孔筛选不是任意面删除。','轮廓是二维边界三阶段，不是完整三维清料；不推断螺纹或倒扣加工。','回滚要求应用后数据库对象/刀具/平面未改变，选择改变不单独构成冲突。']
    if action in geometry_sources:
        caps[-1]['workflow_contract']='ai/skills/mastercam-plugin-suite/references/geometry-xplus.md'
        caps[-1]['adapter_validation']='ai/validation/geometry-native-acceptance.json'
        caps[-1]['limits']+=['报告、截图及STL的回滚保留导出文件；刀柄回滚删除新增刀柄但保留空库。','几何副本编辑保留源对象；不提供任意实体倒角或自动修改原件。','工序链选择基于已有工序，不替代交互式任意链拾取。']
panels=read(ROOT/'ai/workflows/interactive-panels.json')['panels']
for panel,(app,function) in panels.items():
    found=[r for r in routes if r['application']==app and r['function']==function]
    assert len(found)==1,(panel,found)
    caps.append({'id':'panel.'+panel,'module':found[0]['module'],'title':found[0].get('label',panel),'summary':'交互面板入口，须观察界面并通过UI完成操作；排队回执不代表业务成功。','automation':'interactive','tool':'mc_open_panel','panel_id':panel,'route':found[0],'workflow_contract':'ai/workflows/interactive-panels.json'})
external=by_module.get('CIMCO',by_module.get('CIMCOVerify',{}))
caps.append({'id':'module.CIMCO','module':'CIMCO','title':'CIMCO Verify','summary':external.get('summary','官方 Mastercam 仿真插件；本合集提供联网安装，未提供其材料去除/碰撞的结构化调用 API。'),'automation':'interactive','usage':external.get('workflows',[]),'limits':['界面打开或安装验证不能声称仿真通过。','结果需读取真实仿真报告或明确界面证据。'],'routes':[{'application':'CIMCO','function':'UI','completion':'Use installed CIMCO Verify ribbon; no guessed FT command.'}]})
out=ROOT/'ai/catalog';out.mkdir(parents=True,exist_ok=True)
data={'version':'1.2.0','plugin_release':manifest['version'],'module_count':len(modules),'capability_count':len(caps),'ft_route_count':len(routes),'typed_actions':[r[0] for r in typed],'capabilities':caps,'routes':routes}
(out/'capabilities.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
identity=read(ROOT/'ai/bridge/identity.json')
assert identity['sha256']==hashlib.sha256((ROOT/'ai/bridge/bin'/identity['file']).read_bytes()).hexdigest().upper()
print(json.dumps({k:data[k] for k in ('module_count','capability_count','ft_route_count','typed_actions')}))
