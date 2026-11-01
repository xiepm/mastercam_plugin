"""Evidence-scoped 80-rule audit; an adjunct to P08, not another CAM executor.

The automated criteria below are deliberately bound to the 20261024 stand trial.
User rule text remains a cited requirement, never an API name or executable code.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path

SOURCE_SHA = '68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429'
NAMES = ['S1_external','S1_through','S1_top_chamfer','S2_counterbore','S2_blind_14','S2_blind_16','S2_blind_18','S2_blind_20','S2_bottom_chamfer']
COUNTS = dict(M=6,W=6,S=6,T=7,H=10,C=6,G=6,P=6,D=8,F=6,O=6,V=7)
RULE_IDS = {f'{c}{i:02d}' for c,n in COUNTS.items() for i in range(1,n+1)}
HEIGHTS = ['Clearance','Retract','FeedPlane','TopStock','Depth']
STATES = ['pass','fail','blocked','not_applicable','not_run']

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def lookup(obj, path):
    for key in path.split('.'):
        if not isinstance(obj,dict) or key not in obj:
            return None
        obj = obj[key]
    return obj

def semantic_operation(op):
    """Ignore UI selection/display and generation timestamps, never machining values."""
    result=copy.deepcopy(op)
    def strip(x):
        if isinstance(x,dict):
            for key in ('TimeStamp','Selected','DisplayToolpath'):
                x.pop(key,None)
            for val in x.values(): strip(val)
        elif isinstance(x,list):
            for val in x: strip(val)
    strip(result)
    return result

def equal_axes(a,b):
    # Compare coordinates, not TOP labels or arbitrary plane IDs.
    return all(a.get(k)==b.get(k) for k in ('origin','x','y','z'))

def resolved_height(op,key):
    l,p=op['linking'],op['parameters']['WCS']
    value=l.get(key)
    # No invented universal interpretation of incremental or associative modes.
    if value is None or l.get(key+'Incremental') is not False or l.get(key+'Associative') is not False:
        return None
    return [p['origin'][i]+value*p['z'][i] for i in range(3)]

def return_point_matches(op):
    point=resolved_height(op,'Clearance')
    return point is not None and op['home'].get('Enabled') is True and all(abs(a-b)<1e-8 for a,b in zip(point,op['home'].get('Point',[]))) and len(op['home'].get('Point',[]))==3

def parameter_records(op,before):
    result=[]
    for key in HEIGHTS:
        l=op['linking']; value=l.get(key); enabled=l.get(key+'On',True)
        inc,assoc=l.get(key+'Incremental'),l.get(key+'Associative')
        mode='associative' if assoc is True else 'incremental' if inc is True else 'absolute' if inc is False and assoc is False else None
        record=dict(key='Linking.'+key,label=key,scope='operation',operation_id=op['cam_operation_id'],setup_id=op['group_id'],
            observed=dict(value=value,unit='mm',value_mode=mode,frame_ref=op['parameters']['WCS']['name'],reference_ref=l.get(key+'AssociativePoint'),enabled=enabled),
            resolved=dict(value=resolved_height(op,key),unit='mm',frame_ref='model_world',dependencies=['WCS',key+'Incremental',key+'Associative']),
            evidence=dict(state='observed' if value is not None else 'missing',sources=['native'],source_extent='CAM工程记录；不代表现场找正或避障已确认'),
            proposed=None,applied=dict(state='not_written'),checks=['H01','H02','H03','H04','H05','H06','H07'])
        result.append(record)
        previous=before.get('linking',{}).get(key)
        if previous!=value:
            record['applied']=dict(state='readback_verified',before=previous,after_readback=value,readback_status='pass',note='前后原生回读差异；执行来源见对应修改回执')
    result.append(dict(key='HomePosition',label='离线仿真返回点',scope='operation',operation_id=op['cam_operation_id'],setup_id=op['group_id'],
        observed=dict(value=op['home'].get('Point'),unit='mm',value_mode='absolute',frame_ref='model_world',reference_ref=None,enabled=op['home'].get('Enabled')),
        resolved=dict(value=[0,0,op['linking']['Clearance']],unit='mm',frame_ref=op['parameters']['WCS']['name'],dependencies=['WCS','Linking.Clearance']),
        evidence=dict(state='derived',sources=['native','before'],source_extent='本独立试验的虚拟返回点；不定义实机换刀点/G28/G53'),
        proposed=dict(resource_status='simulation_only',point=resolved_height(op,'Clearance')),
        applied=dict(state='readback_verified' if return_point_matches(op) else 'written',before=before['home'],requested=resolved_height(op,'Clearance'),after_readback=op['home'],readback_status='pass' if return_point_matches(op) else 'fail'),checks=['H10','V01']))
    fields=['parameters.WCS','parameters.ToolPlane','parameters.ConstructionPlane','parameters.ProgramNumber','parameters.LengthOffset','parameters.DiameterOffset',
      'parameters.SpindleSpeed','parameters.FeedRate','parameters.PlungeRate','parameters.RetractRate','parameters.DrillCycle','parameters.BreakThrough','parameters.Peck1','parameters.Peck2','parameters.PeckClearance','parameters.ChipBreak','parameters.Dwell',
      'parameters.CutParams','parameters.CutterComp','parameters.DepthCuts','parameters.Chamfer','parameters.LeadInOut','parameters.Roughing','parameters.Finishing',
      'tool','reference_points','chains']
    for path in fields:
        value=lookup(op,path)
        result.append(dict(key=path,label=path,scope='operation',operation_id=op['cam_operation_id'],setup_id=op['group_id'],
            observed=dict(value=value,unit='rpm' if path.endswith('SpindleSpeed') else None,value_mode=None,frame_ref=None,reference_ref=None,enabled=None),
            evidence=dict(state='observed' if value is not None else 'missing',sources=['native'],source_extent='原生字段；空值不解释为零/关闭/不适用'),proposed=None,applied=dict(state='not_written'),checks=[]))
    return result

# Every result carries actual operation-specific field values, including inactive values.
FIELDS = {
 'M':'parameters.Type parameters.FeedRate parameters.SpindleSpeed',
 'W':'parameters.WCS parameters.ToolPlane parameters.ConstructionPlane',
 'S':'parameters.DrillPoints chains',
 'T':'tool parameters.LengthOffset parameters.DiameterOffset',
 'H':'linking home reference_points parameters.DepthCuts',
 'C':'parameters.SpindleSpeed parameters.FeedRate parameters.PlungeRate parameters.RetractRate parameters.Coolant tool',
 'G':'chains parameters.DrillPoints parameters.CutterComp parameters.PocketRoughEntry parameters.LeadInOut',
 'P':'parameters.CutterComp parameters.CutParams parameters.DepthCuts parameters.Roughing parameters.Finishing parameters.ArcFilter parameters.Smoothing',
 'D':'parameters.DrillCycle parameters.DrillPoints parameters.BreakThrough parameters.Peck1 parameters.Peck2 parameters.PeckClearance parameters.ChipBreak parameters.Dwell linking tool',
 'F':'parameters.CutParams parameters.Chamfer tool linking',
 'O':'parameters.ProgramNumber parameters.Posting parameters.Selected parameters.Dirty parameters.OperationTool.Number',
 'V':'parameters.Dirty extents cycle_seconds home',
}
MISSING = {
 'M01':'需要当前版本API字段映射和实际生成证据。','M02':'缺该工件绑定的具体机床/控制器型号；历史850/新代仅为未确认候选。','M03':'缺机床运动学、安装变换、行程及软限位。','M04':'CAM为毫米；最终NC单位和进给模式尚未验证。','M05':'缺目标机床/刀具/刀柄转速、进给及附件限制。','M06':'当前为GENERIC FANUC 3X MILL；没有针对目标机床的适配证据。',
 'W01':'模型原点可读；缺现场找正、对刀与基准方案。','W02':'原生偏置0/1已读；G54/G55输出和控制器映射未经最终NC验证。','W03':'需核对数值变换和刀轴。','W04':'已读取平面及链首实体/钻点；完整选择实体到STEP面的逐项关联未验证。','W05':'两组刚体变换已读；缺真实翻面夹具、基准传递与找正依据。','W06':'只解析有明确定义的绝对非关联高度。',
 'S01':'STEP版本已绑定；没有对应图纸、公差/粗糙度等技术要求。','S02':'ALUMINUM mm - 2024为工程模板值；真实材料及状态未确认。','S03':'18×18×10为离线候选毛坯，非现场下料确认。','S04':'缺两次装夹真实夹具、压板、螺钉和垫块几何。','S05':'已检查候选刀具组件与毛坯；真实夹具/机床避让集合缺失。','S06':'已计算余料；夹持支撑、外轮廓切穿后的固定方式未确认。',
 'T01':'SIMULATION_ONLY刀具为候选，缺实际厂家型号与刀具版本。','T02':'候选几何可读；真实刃形、中心切削和允许入口能力未确认。','T03':'候选刃长与刀路可读；实际刃段/肩部和受力可达性未确认。','T04':'Length=40是候选API长度；未确认实物伸出量、规长及安装定义。','T05':'候选20×40刀柄已参与检查；真实夹头/螺母/接杆完整包络缺失。','T06':'T/H数值可读；实机刀表及后处理长度补偿行为未核验。','T07':'D与CAM刀补模式可读；实机磨损值和控制器解释未核验。',
 'H01':'安全高度已解析；缺实际障碍包络，不能确认现场避障。','H02':'需验证首尾开关及原生运动。','H03':'退刀高度可读；真实跨越障碍和夹具未定义。','H04':'进给平面可读；在候选毛坯内验证，实际余料/障碍未知。','H05':'检查每次装夹表面坐标。','H06':'检查局部负向深度及钻尖/倒角语义。','H07':'检查每字段绝对、增量、关联模式。','H08':'原生运动及NoCollisionChecking标记已记录；未验证最终NC快速定位/机床运动学。','H09':'保持低位字段可读；真实台阶/压板避障仍缺输入。','H10':'250mm默认点已替换为装夹中心局部Z+10的离线返回点；实际机床换刀/G28/G53及中间点未验证。',
 'C01':'3000rpm/150进给/60下刀为离线模板参数，无材料与厂家推荐依据。','C02':'缺真实刀具有效切径、主轴及刀柄上限。','C03':'进给数值可读；材料/刀具工况及最终NC进给模式未确认。','C04':'下刀/进退刀值可读；刀具垂直下刀和入口推荐参数缺失。','C05':'CAM冷却为关；实际转向、冷却能力和后处理行为未验证。','C06':'缺实际材料、刀具负载和拐角参与量依据。',
 'G01':'保留链首实体ID或钻点；未证明完整所选实体与目标面逐项一致。','G02':'检查闭合连续链及边界尺寸。','G03':'实际链方向和补偿侧可读；受限材料仿真不代替完整接触侧审查。','G04':'边界/刀心语义和有限网格验证已记录；未完成精确边界接触审查。','G05':'实际刀具中心切削/斜插能力未知；候选入口不放行至实机。','G06':'引入/引出与连接可读；实际刀补建立及表面接刀要求未验证。',
 'P01':'读取实际刀补承担方。','P02':'没有最终NC，不能核验控制器补偿建立/取消。','P03':'模型到尺寸的候选侧壁/底面留量检查。','P04':'分层/步距是候选模板；真实材料刀具允许切深尚缺。','P05':'终加工/重复走刀参数已读；缺图纸公差和真实前置余量。','P06':'过滤/平滑设置已读；NC圆弧支持和图纸误差预算未核验。',
 'D01':'候选孔特征已与STEP绑定；孔公差和图纸工艺要求缺失。','D02':'逐个核验钻点，无遗漏重复。','D03':'按118度候选钻头分开计算钻尖总深与完整孔径深度。','D04':'突破量和钻尖深度可算；底部夹具空间未确认。','D05':'CAM为Drill；控制器循环输出和材料排屑需求未验证。','D06':'当前Drill无啄钻参数执行。','D07':'每工序一个孔；循环孔间/孔内返回的最终NC语义未验证。','D08':'实际钻头是否需要定位/预钻以及停留单位缺厂家和控制器依据。',
 'F01':'候选倒角宽0.2、刀尖平口0.5及角度可读；真实刀具/图纸尚未确认。','F02':'区分0.2倒角宽/深度和0.5刀尖偏移；候选接触结果由材料仿真限定。','F03':'当前工序没有攻丝或螺纹铣；不推断未提供图纸没有螺纹要求。','F04':'当前工序不是攻丝，无同步退刀动作。','F05':'当前工序不是铰孔或镗孔；不代表钻孔已达精孔公差。','F06':'未执行特殊孔/枪钻；孔底连接和实物刀具需求仍待核对。',
 'O01':'双装夹顺序已读且余料连续计算；实际夹持/基准前提未落实。','O02':'逐工序检查已生成状态与仿真覆盖。','O03':'程序1001/1002仅为CAM分组；没有最终NC文件映射。','O04':'未生成本版本最终NC，未做模态跟踪。','O05':'未生成最终NC，未验证M代码、换刀、冷却与返回。','O06':'没有本版本最终NC；旧source.NC名称不能作为输出证据。',
 'V01':'必须比较写后/重开语义和重生成状态。','V02':'已做有界材料去除/网格过切残料；无图纸验收公差，连接/实际NC与初始化跳转仍有限制。','V03':'已记录刀柄/刀杆/肩部对毛坯检查；缺夹具、机床且部分初始化移动标记NoCollisionChecking。','V04':'未执行最终NC解释。','V05':'未执行目标整机运动学仿真。','V06':'新工程哈希已绑定；现场记录未执行，旧证据不可直接沿用。','V07':'按80规则、9工序输出全部状态、来源与缺项。'
}

def motion_summary(receipt):
    if receipt.get('ok') is not True: raise ValueError('motion receipt failed')
    rows=[]
    for stream in receipt['streams']:
        pts=[]; axes=[]; local=[]; unchecked=[]
        for i,m in enumerate(stream['moves']):
            data=m['move_data']
            if data.get('has_value') is not True: raise ValueError('missing native motion')
            cnc=data['value']['CNCData'];p=cnc['Position'];a=cnc['Orientation']
            pts.append([p[k] for k in 'XYZ']);axes.append([a[k] for k in 'XYZ'])
            info=m['move_info'];lp=info.get('value',{}).get('toolplaneCoordinates') if info.get('has_value') else None
            local.append([lp[k] for k in 'XYZ'] if lp else None)
            if 'NoCollisionChecking' in m['scalars']['Flags']: unchecked.append(i)
        rows.append(dict(operation_no=stream['operation_info']['OperationNo'],count=len(pts),
            world_point_min=[min(p[i] for p in pts) for i in range(3)],world_point_max=[max(p[i] for p in pts) for i in range(3)],
            tool_axes=sorted(set(tuple(a) for a in axes)),first_local=local[0],last_local=local[-1],no_collision_check_indices=unchecked))
    return dict(scope='原生Verify离散运动终点，非圆弧全包络或最终NC；NoCollisionChecking不得忽略',operations=rows,total_moves=sum(r['count'] for r in rows),no_collision_check_moves=sum(len(r['no_collision_check_indices']) for r in rows))

def validate_simulation(sim,binding):
    if sim.get('ok') is not True or sim.get('motion',{}).get('completed') is not True:raise ValueError('Simulation incomplete')
    if sim.get('target_sha256')!=binding.get('target_sha256'):raise ValueError('Target hash mismatch')
    if sim.get('report_groups')!=[]:raise ValueError('Native reports require review')
    if sim.get('checks')!={'enabled':True,'between_moves':True}:raise ValueError('Missing collision check configuration')
    vs=sim.get('verifiers',[])
    if len(vs)!=1:raise ValueError('Unexpected verifier count')
    v=vs[0]
    if v.get('gouges')!=[] or v.get('excess')!=[]:raise ValueError('Gouge/excess not clear')
    for key,val in [('gouge_threshold_mm',-.02),('excess_threshold_mm',.02),('collision_tolerance_mm',.02),('holder_tolerance_mm',.02),('cutting_tolerance_mm',.005)]:
        if not isinstance(v.get(key),(float,int)) or abs(v[key]-val)>1e-6:raise ValueError('Tolerance mismatch '+key)
    if not 0<v.get('precision_mm',0)<=.0051:raise ValueError('Precision not established')
    for part in ('holder','shaft','arbor'):
        if v.get(part,{}).get('IsCollisionChecked') is not True or v.get(part,{}).get('RapidCollisionReportSuppressed') is not False:raise ValueError('Tool assembly checks incomplete')

def build_report(spec,native,before,reopened,binding,sim,motion):
    if {r['rule_id'] for r in spec['rules']}!=RULE_IDS or len(spec['rules'])!=80:raise ValueError('Expected all 80 unique rules')
    if binding.get('source_sha256')!=SOURCE_SHA:raise ValueError('Unsupported source; this audit profile is bound to stand')
    for r in (native,before,reopened):
        if r.get('ok') is not True or [o['name'] for o in r['operations']]!=NAMES:raise ValueError('Native identity/coverage failed')
    if native['model_sha256']!=reopened['model_sha256']:raise ValueError('Reopen file hash mismatch')
    # GetViewSheetData reports an active unsaved orbit as GraphicsPlaneID=-1.
    # Compare stored setup identity/planes, and independently require cold-open TOP restoration.
    sheet_core=lambda s:{k:v for k,v in s.items() if k!='graphics_plane_id'}
    sheets_equal=[sheet_core(s) for s in native['view_sheets']]==[sheet_core(s) for s in reopened['view_sheets']]
    views_restored=all(s['graphics_plane_id']==s['tool_plane_id'] for s in reopened['view_sheets'])
    reopened_equal=all(semantic_operation(a)==semantic_operation(b) for a,b in zip(native['operations'],reopened['operations'])) and native['stock']==reopened['stock'] and sheets_equal and views_restored
    if not reopened_equal:raise ValueError('Reopened configuration differs')
    validate_simulation(sim,binding)
    normalize=lambda s:str(s).replace('\\','/').casefold()
    if normalize(sim.get('model_path'))!=normalize(reopened['model']) or normalize(motion.get('model_path'))!=normalize(reopened['model']):raise ValueError('Simulation document mismatch')
    ms=motion_summary(motion)
    if ms['total_moves']!=sim['motion']['num_moves'] or len(ms['operations'])!=9:raise ValueError('Motion coverage differs')
    checks=[]; params=[]; operation_summaries=[]
    bmap={o['name']:o for o in before['operations']}
    for idx,o in enumerate(native['operations']):
        p,t,l=o['parameters'],o['tool'],o['linking']; is_drill=o['type']=='Mastercam.Operations.DrillOperation'; is_chain=o.get('chains') is not None
        is_chamfer=lookup(p,'CutParams.ContourSubtype')=='Chamfer2D'; original=bmap[o['name']]
        params.extend(parameter_records(o,original))
        calc={}
        if is_drill and t.get('TipAngle')==118 and t.get('Diameter') is not None:
            tip=t['Diameter']/2/math.tan(math.radians(t['TipAngle']/2))
            calc=dict(tip_length_mm=tip,tip_total_depth_mm=-l['Depth'],full_diameter_depth_mm=-l['Depth']-tip,
                extra_full_diameter_breakthrough_mm=(-l['Depth']-tip-10) if o['name']=='S1_through' else 0,
                dependencies=['candidate drill diameter','candidate 118 degree included point angle','absolute setup depth'],resource_status='simulation_only')
        op_summary=dict(id=o['cam_operation_id'],name=o['name'],setup_id=o['group_id'],group=o['group_name'],tool_number=t['Number'],tool_diameter_mm=t['Diameter'],planes={k:p[k] for k in ('WCS','ToolPlane','ConstructionPlane')},heights_mm={k:l[k] for k in HEIGHTS},home_world_mm=o['home']['Point'],drill_depth_calculation=calc)
        operation_summaries.append(op_summary)
        for rule in spec['rules']:
            rid=rule['rule_id'];status='blocked';note=MISSING[rid]
            if rid in ('O04','O05','O06','V04','V05'):status='not_run'
            if rid=='M01':status='pass';note='已绑定Mastercam 2027/NETHook 29.x原生字段、具体工序类型和本次生成回读；不推断额外许可。'
            if rid=='W03':
                sign=1 if idx<3 else -1
                valid=equal_axes(p['WCS'],p['ToolPlane']) and p['ToolPlane']['z']==[0,0,sign] and p['UseWCS'] and p['UseToolPlane']
                status='pass' if valid else 'fail';note='本三轴固定刀轴试验按数值坐标及刀轴核对；不以平面名称相等作为通用规则。'
            if rid in ('W06','H07'):
                status='pass' if all(resolved_height(o,k) is not None for k in HEIGHTS) else 'blocked'
                note='五个高度均按该工序自身WCS解析；保留各自增量/关联开关和参考对象。'
            if rid=='H02':
                status='pass' if l.get('ClearanceStartEndOnly') is False and l.get('ClearanceOn') is True else 'blocked'
                note='原生ClearanceOn=true、ClearanceStartEndOnly=false；不据此宣称全部连接已避让真实夹具。'
            if rid=='H05':
                expected=10 if idx<3 else 0
                status='pass' if l.get('TopStock')==0 and p['WCS']['origin']==[0,0,expected] else 'fail'
                note='本候选毛坯正面世界Z10、翻面世界Z0；两个装夹各自局部表面Z0。'
            if rid=='H06':
                expected=[-10.05,-12,0,-6.4,-8.11588213450325,-8.11588213450325,-8.11588213450325,-8.11588213450325,0][idx]
                status='pass' if abs(l['Depth']-expected)<1e-6 else 'fail'
                note='核对本STEP绑定候选深度；倒角Width/Depth/TipOffset另存，不将Linking.Depth=0当作零切深。'
            if rid=='H10':
                note=f"返回点位于当前装夹中心局部Z+{l['Clearance']:g}mm，与原生Clearance一致；实际机床换刀/G28/G53未验证。"
                if not return_point_matches(o):status='fail';note='原位点不符合本离线试验派生位置；禁止接受未解释的远距离返回。'
            if rid=='G02' and is_chain:
                status='pass' if len(o['chains'])==1 and o['chains'][0]['IsClosed'] and o['chains'][0]['IsFlat'] else 'fail'
                note='原生读取闭合平面链、首实体ID、曲线数、方向、周长与面积；不把链首ID误称完整实体列表。'
            if rid.startswith('G') and is_drill and rid in ('G02','G03','G04','G06'):
                status='not_applicable';note='本工序为单点钻孔，不执行轮廓链方向、边界偏置或轮廓引入。钻孔连接仍按D/H规则核验。'
            if rid=='P01' and is_chain:
                comp=lookup(p,'CutterComp.Type') or lookup(p,'Finishing.CutterComp')
                status='pass' if comp=='CutterCompComputer' else 'blocked';note='原生模式为Computer，由CAM计算候选刀径偏置；D映射和最终NC仍另验。'
            if rid=='P03' and is_chain:
                stock=lookup(p,'CutParams.LeaveStock');status='pass' if stock and stock.get('OnWalls')==0 and stock.get('OnFloors')==0 else 'blocked'
                note='本离线到模型尺寸方案侧壁/底面留量均为0；不等于图纸公差或现场尺寸已验收。'
            if rid in ('P01','P02','P03','P04','P05') and is_drill:
                status='not_applicable';note='本工序为普通钻孔，不执行轮廓半径补偿、侧壁留量、多重轮廓切削或铣削精加工。'
            if rid.startswith('D') and not is_drill:
                status='not_applicable';note='本工序为轮廓/挖槽/外轮廓倒角，不执行钻孔固定循环；本结果不宣称零件不存在孔。'
            if rid=='D02' and is_drill:
                pts=p.get('DrillPoints',[]);expected=binding['operations'][idx]['origin']
                point=pts[0].get('PointData') if len(pts)==1 else None;plane=p['ToolPlane']
                actual=[plane['origin'][i]+sum(point[j]*plane[k][i] for j,k in enumerate(('x','y','z'))) for i in range(3)] if point else None
                cutting=[m['move_data']['value']['CNCData']['Position'] for m in motion['streams'][idx]['moves'] if m['move_data']['has_value'] and not m['move_data']['value']['CNCData']['IsRapid']]
                matches=actual is not None and all(abs(x-y)<1e-7 for x,y in zip(actual,expected)) and bool(cutting) and all(abs(q['X']-expected[0])<1e-6 and abs(q['Y']-expected[1])<1e-6 for q in cutting)
                status='pass' if matches else 'fail'
                note='本版本DrillPoints.PointData按该工序TPlane转换到模型坐标，再与绑定孔位及原生Verify切削运动XY逐一比较；不将翻面局部Y误作世界Y。'
            if rid=='D03' and is_drill:
                valid=bool(calc) and (calc['full_diameter_depth_mm']>=10 if idx==1 else abs(calc['full_diameter_depth_mm']-7.5)<1e-6)
                status='pass' if valid else 'fail';note='候选118°钻头几何计算；贯穿孔另列完整孔径突破量，四盲孔完整孔径深度7.5mm。实际刀具/图纸仍未确认。'
            if rid=='D06' and is_drill and p.get('DrillCycle')=='Drill' and all(p.get(k)==0 for k in ('Peck1','Peck2','PeckClearance','ChipBreak')):
                status='not_applicable';note='原生Drill普通钻孔且啄钻字段均0，没有执行G73/G83；不套用Haas的Q/IJK规则。'
            if rid in ('F01','F02') and not is_chamfer:
                status='not_applicable';note='该工序没有启用Chamfer2D；即便对象有默认Chamfer字段，也不能视为生效。'
            if rid in ('F03','F04','F05'):
                status='not_applicable';note=MISSING[rid]+' 不代表缺失图纸的要求已经覆盖。'
            if rid=='O02':
                valid=p.get('Dirty') is False and p.get('Posting') is True and ms['operations'][idx]['count']>0
                status='pass' if valid else 'fail';note='当前工序刀路干净、原生Verify有非空运动；后处理选择和NC输出仍未执行。'
            if rid=='V01':
                status='pass' if return_point_matches(o) and not p['Dirty'] and reopened_equal else 'fail'
                note='九道工序已重生成，返回点写后回读与文件重开后的完整工艺语义一致。'
            if rid=='V07':status='pass';note='本报告保留全部80规则及9工序对应结果、来源、差异和缺项，不给出整体生产通过。'
            observed={path:lookup(o,path) for path in FIELDS[rid[0]].split()}
            if rid.startswith('M'):observed.update(machine=native['machine_name'],post=native['post_name'],metric=native['metric'],api=native['api_version'])
            if rid.startswith('S'):observed.update(stock=native['stock'],material_record=native['material'],material_actual=None,fixture_actual=None)
            if rid=='D03':observed['calculated']=calc
            checks.append(dict(result_id=f"{rid}:operation:{o['cam_operation_id']}",rule_id=rid,setting=rule['setting'],category=rule['category'],scope_type='operation',target_id=str(o['cam_operation_id']),setup_id=o['group_id'],operation_id=o['cam_operation_id'],affected_operation_ids=[o['cam_operation_id']],status=status,applicability_reason=note,criterion=rule['check_instruction'],observed_result=observed,evidence_refs=['native','before','reopened']+(['simulation','motion'] if rid[0] in 'HV' or rid=='O02' else []),dependencies=rule['required_evidence'],blocked_actions=['production_release'] if status in ('blocked','fail','not_run') else [],permitted_next_actions=['offline_review','supply_missing_evidence']))
    summary={s:sum(r['status']==s for r in checks) for s in STATES}
    return dict(schema_version='aicnc.mastercam.configuration-audit/0.1',profile='stand-20261024-software-only',production_released=False,rule_count=80,operation_count=9,check_count=len(checks),source_sha256=SOURCE_SHA,model_sha256=native['model_sha256'],rules_specification=spec['specification'],summary=summary,
        validation_layers=dict(configuration=dict(status='blocked',reason='存在真实资源与制造要求缺项；规则结果见逐项记录'),cam_toolpath=dict(status='pass',scope='候选毛坯/刀具的原生材料去除，233离散运动；不包含实际NC/夹具/整机/初始化跳转碰撞证明',gouge_excess_threshold_mm=.02),posted_nc=dict(status='not_run'),machine_simulation=dict(status='not_run'),on_machine_record=dict(status='not_run')),
        reopen=dict(status='pass',configuration_equal=reopened_equal,saved_sha256=native['model_sha256'],reopened_sha256=reopened['model_sha256'],view_sheets_before=native['view_sheets'],view_sheets_reopened=reopened['view_sheets'],view_note='比较装夹标签及WCS/C/T；保存前翻面临时观察视角graphics=-1，冷重开恢复命名俯视55，未声称临时屏幕视角逐值一致。'),operations=operation_summaries,parameters=params,checks=checks,motion=ms,
        missing_facts=dict(machine_exact=None,controller_exact=None,fixture_geometry_by_setup=None,material_confirmed=None,actual_tool_assemblies=None,drawing_tolerances=None,onsite_zero_and_workholding=None,validated_post=None),
        evidence_invalidation='工程/刀具/装夹/毛坯/后处理任一依赖改变，相关验证须重新执行；旧哈希的结果仅保留历史参考。')
