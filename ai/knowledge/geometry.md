# 几何与辅助插件知识（发布包 2027.10.28.2）

本手册与 [geometry.json](geometry.json) 覆盖21个知识条目、49个工作流。`typed_candidate` 表示存在可封装的业务方法；`interactive` 表示需要交互；`not_exposed` 表示没有证实的专用自动化接口。该分类不等于MCP注册清单：当前父端桥接源码已实现MP截面/拔模与创建/回滚映射，其余接口不能据此宣称已注册。实际能力以 [server.py](../mcp/server.py)、[models.py](../mcp/models.py) 和 [capabilities.json](../catalog/capabilities.json) 为准。

发布基线为 [catalog/package.json](../../catalog/package.json) 的2027.10.28.2；以发布DLL哈希为准，不能拿开发目录较新候选替代。所有界面初始数值仅是输入示例，不是加工默认值、推荐进给、推荐公差或安全高度。实际参数来自用户、零件要求、刀具和工艺依据。长度使用当前文档单位；方向/坐标系必须明确。`local-source: MC2027-PluginSuite/...` 是本机源码核对来源标记，不是公开repo中的可加载路径。

## MPRebuild2027：业务API与当前桥接

发布程序集1.0.1.0，SHA256 `6935E289BC9D8DC39EEB564A9723B5CAF574870C333D1492490B0F2635224564`；Core为`30CF0A6CA970D6AB5A129D78E92FB6DD26573B184DBD213AFE3DF3014A241B0C`。配套冻结Porsche只用于精确选择恢复。API29/SDK/MCCORE构建约束及实测范围见 docs/COMPATIBILITY.md、validation/mp-native-acceptance.json。

```csharp
// 这些是插件业务签名示意；MCP映射见下文。
MPRebuild2027.Dependencies.Ensure();
MPRebuild2027.AnalysisPlan p = MPRebuild2027.Workflows.Sections(
    int[] ids, MPRebuild2027.Core.Vec3 origin, MPRebuild2027.Core.Vec3 normal,
    int count, double spacing, double meshTolerance, double weldTolerance, string directory);
MPRebuild2027.AnalysisPlan p = MPRebuild2027.Workflows.Draft(
    int[] ids, MPRebuild2027.Core.Vec3 pull, double thresholdDegrees,
    double meshTolerance, double weldTolerance, bool transitionEdges, bool normalGlyphs,
    double glyphLength, int maximumGlyphs, string directory);
p.Verify();
MPRebuild2027.OutputRun run = MPRebuild2027.Workflows.Create(p, int level); // 可选，才创建原生线
run.Rollback(); // 同会话精确回滚；外部编辑会拒绝
```

上述代码块是签名示意，不是可原样执行脚本。宿主线程需运行在已打开的Mastercam文档内；明确传入世界坐标和当前文档长度单位。先加载配套Core/Porsche/MP程序集。桥接层保留plan/run活对象并返回会话句柄，限定目录，不暴露任意callback；不得通过反序列化构造假的计划。读取结果采用受控DTO，NaN面积明确标记无效，不转换为0。

| UI/FT入口 | 模式 | 精确业务映射 |
|---|---:|---|
| Sections | 0 | Sections(...,count:1,...) |
| SliceStack | 1 | Sections(...,count:SliceCount,spacing:SliceSpacing,...) |
| DraftAnalysis | 2 | Draft(...,transitionEdges:false,normalGlyphs:true,...) |
| PartingPreparation | 3 | Draft(...,transitionEdges:true,normalGlyphs:false,...) |
| FacetNormals | 4 | Draft(...,transitionEdges:false,normalGlyphs:true,...) |

**UI初始值示例，不是加工默认值或推荐参数**（GeometryWindow.Parameters）：Direction=(0,0,1)，Origin=(0,0,0)，SliceCount=5，SliceSpacing=1，MeshTolerance=.01，WeldTolerance=.0001，DraftThreshold=3°，GlyphLength=1，MaximumGlyphs=1000，OutputLevel=当前主层。UI在英制时仅将间距、两种公差、箭头长度除以25.4；直接调用Workflows不会自动换算。读取CPlane只复制ViewOrigin和ViewMatrix.Row3到输入，不改变CPlane。

**限制**：1～100个不同可见SolidGeometry ID；0<weld<=mesh；非零有限方向；count 1～200，多层spacing>weld；0<拔模阈值<90；启用箭头时长度>0、采样1～10000；每体50万片、合计100万片、片数×截面数<=2000万、新线<=5万。输出层须为已有可见层或当前主层，无其他活动撤销事务。

**实用顺序**：选实体→设置世界平面或pull→“分析并保存报告”→检查闭环/面积/法向及诊断→必要时“分析并生成几何”→用同一会话“回滚最近结果”。Sections/Draft只写STL/JSON/CSV；Create才产生线。报告默认目录为%LOCALAPPDATA%/MC2027Workshop/MPRebuild2027/run-*，包括analysis.json、selection-readbacks.json、solid-ID.stl及拔模CSV；Create另存created-geometry.json。回滚不删除报告文件。

**意义与边界**：截面是公差网格的直线轮廓；分模准备是类别交界网格边；负角不等于倒扣。没有完整B-rep分模、遮挡、电极或UV算法。模式2与4是相同Draft调用，不宣称两个不同曲面算法。公开face-map读会清选择，1.0.1已保护；不要自行绕过HostSession.Stamp。任一源/选择/工序/视图上下文变更会使旧计划无效。

证据：catalog/package.json，docs/HSM-MP.md，validation/mp-native-acceptance.json；开发源码来源MC2027-PluginSuite/MPRebuild2027/src/Host/{Workflows,NativeState,GeometryWindow,Main}.cs（业务源码不在此公开repo src内）。12组/11301原生断言通过；不外推全部工业模型。



### 当前MCP请求契约

已读取父端当前桥接源码；这里记录实现映射，不把插件既有原生测试当成新MCP写入测试。父端报告首个真实stdio `mc_inspect` 已通过；其他适配验收以父端独立测试结果为准。本知识整理没有启动或控制宿主。

| action | 顶层必填字段 | parameters必填字段 |
|---|---|---|
| `mp.sections` | `action, expected_document, solid_ids, output_level, parameters` | `origin:{x,y,z}, normal:{x,y,z}, count, spacing, mesh_tolerance, weld_tolerance` |
| `mp.draft` | 同上 | `pull:{x,y,z}, threshold_degrees, mesh_tolerance, weld_tolerance, transition_edges, normal_glyphs, glyph_length, maximum_glyphs` |

桥接不接收任意报告目录或回调。输出层必须已经存在且可见；实体ID唯一。长度值直接以文档单位传递。单截面count=1；多截面间距须大于焊接公差。启用法线时glyph_length>0、maximum_glyphs>=1；桥接模型的基础字段范围不能替代插件跨字段验证。两种拔模输出布尔值由实际任务决定，不把UI模式参数自动当作工程推荐值。

1. `mc_inspect()` 取得准确的已保存文档路径、单位与真实ID。
2. `mc_prepare_change(request)`：选择`mp.sections`或`mp.draft`，填入全部明确参数。此步写STL/JSON/CSV分析文件，尚未创建原生结果线。
3. 检查返回`preview`、`plan_id`、`preview_sha256`及报告。分析计划只有当前会话有效；15分钟到期，源对象/选择/上下文改变会失效。
4. 需要创建几何且已有该变更授权时，调用`mc_apply_plan(plan_id,preview_sha256,expected_document,request_id)`，核对状态与`created_ids`。
5. 需要撤销同一结果时，`mc_rollback_plan(plan_id,expected_document,request_id)`；未应用计划可`mc_discard_plan(plan_id)`，分析文件保留。
6. 调用超时先查`mc_request_status(request_id)`；unknown_or_running不是失败，不凭此重复写入。不要通过Mastercam重启来“恢复”旧计划。

### 选择哪一种几何流程

| 需要 | 使用 | 核对重点 |
|---|---|---|
| 斜截面/某高度闭环 | MPRebuild Sections | 世界平面、网格弦差、焊接公差、闭环/分支诊断、面积有效性 |
| 连续高度切片 | MPRebuild SliceStack | 起点、方向、层数、正间距、逐实体结果 |
| 法向相对拉拔方向的区域 | MPRebuild Draft | 正负符号、近零阈值、绕序一致性；负角不等于倒扣 |
| 为人工分模提供区域边界 | MPRebuild PartingPreparation | 网格流形/绕序、类别交界；不是芯腔B-rep分离 |
| 翻转独立曲面方向 | MPDesignTools | 真正改变原曲面标志；与显示网格箭头不同 |
| 规则多面体所有直边/XY线框 | MPEdgeTools 0.1.0 | 全平面直边、单实体、投影坍缩及重合边 |
| 原生剪影/删除面 | GeometryTools.NativeCommands | 用户在原生面板完成；打开面板不算完成业务 |

## 曲面选择与有限直边

**MPDesignTools2027 1.0.0.0**：选独立可见曲面→反转法向→核对计划中的原/新方向→确认。实际操作为 `Mastercam.Database.SurfaceGeometry.IsNormalReversed` 切换并Commit；实体、线框和不可见对象会跳过。取消不写入；异常恢复已尝试曲面的原标志并报告恢复失败。成功后没有跨会话专用回滚收据。它不重建曲面、不改变UV，也不自动推断实体外侧。

**MPDesignSurfaceSelect2027 1.0.0.0**：打开类型列表→从实际`Available`类型选择→预览→接受。选择结果是原选择与命中可见独立曲面的并集；清预览/取消恢复。类型字符串来自当前文档，不能用固定猜测列表替代。不会把曲面变成另一类型，也不会选择实体内部的“曲面面片”。

**MPDesignRadiusSelect2027 1.0.0.0**：给定最多128个可见实体→勾选Cylinder/Sphere/TorusMinor/TorusMajor/ConeReference→输入闭区间半径→核对匹配面的PersistentId和BodyId→接受。最终选中的是所属整实体。ConeReference是解析锥面参考半径，不能解释为任意位置曲率半径；自由曲面和可变圆角不在范围内。

**MPEdgeTools2027 0.1.0.0**（源码目录MPDesignTools2027-edge）：单选全平面直边实体→选3D或世界XY投影及输出Z→选已有可见输出层→`EdgeTools.Preview`→核对Signature→`Create(request,Signature)`。创建时重新读取/计算，不接受调用方注入线数组。最多1024面/4096边、容差1e-9～.01。投影会去除坍缩竖边、合并相同端点边；没有遮挡、外轮廓并集或局部重叠裁剪。0.1.1圆弧候选不属于此发布包。失败精确清理自有对象；成功后没有独立Rollback方法。

## GeometryTools与ChainTools

GeometryTools2027 0.1.1.0 的确定性入口为 `HostGeometry.Prepare(ids,request)` →核对→`Execute(plan)`。当前选择须与ids一致，1～5000个可见有效对象，无其他活动事务；计划只能消费一次。修改源/选择后应重新准备。

| GeometryRequest.Command | 输入含义与实际效果 |
|---|---|
| CenterXY / CenterXYZ | 整体AABB中心移到Destination；XY保留Z。不是质量中心，也不改WCS |
| RotateX90 / RotateY90 / RotateZ90 | QuarterTurns为非零整数；绕整体包围盒中心的世界轴旋转 |
| AlignCplane | 含原点的完整仿射变换，把几何从构造平面变到世界XY |
| PaintZPlanes / PaintVerticalPlanes | 用AngleTolerance（度）判定Plane法向相对世界Z；写Color |
| AssignLevel | 写入已存在可见Level |
| DimensionBounds | TextHeight/DimensionOffset/Decimals生成线段数字和尺寸；非关联尺寸 |
| MergeCurves | 单连通无分支曲线组，按CurveTolerance形成一条新NURBS，原曲线保留 |
| ChamferEdges | 单实体、明确非空EdgeTags、等距ChamferDistance；无相切传播 |

几何倒角与MCP的 `operation.chamfer` 是不同业务；后者调整刀路参数，不能当作本表几何倒角已接入。 `MeasureSelected` 对部分类型会临时建包围框点再取消事务，不是任意线程可调用的纯getter。执行失败会尝试恢复并验证；成功后多数动作依宿主正常撤销，没有统一持久Rollback方法。

`RelatedLevels.InspectSelected/InspectSelectedJson` 读取选中工序链的线框及串连实体边所属体层号；不覆盖所有加工面、检查面、毛坯、外部引用。交互`Show`临时显示相关层，关闭恢复原可见性。

GeometryTools2027.NativeCommands 0.1.0.0 只发送原生 `sld_do_face_removal` 或 `create_SilhouetteBoundary`。前者由用户选面；后者使用当前构图平面/Z深度，具体设置在原生面板核对。它不是自动识孔删除或已完成剪影算法。

ChainTools2027 1.0.2.0：原生串连对话框选开/闭线框链→预览新增选择→确认并集。最多4096条链；排除点/曲面/实体。取消/Esc/异常恢复原Selected集合；不保证恢复所有临时高亮/视口。同步回调不跨MCP请求，不在回调内改几何。

## 夹具、刀柄与分度平面

**FixtureTools2027 Host1.1.1.0/Core1.1.0.0**有两条路径，不能混用其能力边界：

- 便携点线库：选普通点线→`FixtureApi.OpenSession`→`CaptureSelected(name,reference)`→`Preview(component,PlacementTransform,targetLevel)`→`Apply`。库声明mm/in且必须与文档一致；`LibraryJson.SaveNew`不覆盖已有文件。变换为`q=R*(p-reference)+target+translation`。JSON便携定义不包含任意B-rep或完整SMK格式。
- 原生复制：选择实体/曲线/点→明确reference、target、translation和世界Z的90°倍数→`NativeFixtureCopy.PlaceSelected`→核对新ID、属性和包围盒。保留源层与样式，副本不选中、不Blanked。若用`StageSelected`临时试摆，必须在同一同步宿主调用中Keep或Cancel，不能跨远程请求悬挂事务。

两者都不自动定义CAM检查体、机床夹具角色或碰撞关系。原生复制的包围盒验证不等于完整B-rep等价。成功后的撤销遵循宿主事务规则；报告不是跨文档删对象授权。

**HolderTools2027 0.1.0.0**：用上下直径/高度定义圆柱或圆台各段→核对单位→按需Split/Flip→选择.tooldb和审计目录→`Library.Create`→重新读库确认新GUID及截面。Split距离从段顶量；Flip逆序段并交换上下直径。只新增条目，不替换旧刀柄或工序刀柄。回滚用原`WriteReceipt`，遇库/条目冲突拒绝；仅保证逻辑删除该GUID，不保证数据库字节恢复。关闭界面保留已经保存的条目。未实现任意圆弧截面或从几何自动识别刀柄。

**HirthTools2027**：明确两个固定WCS轴方向、各轴范围和离散步长→选目标平面→`HostPlanes.PreviewCurrent/PreviewPlane`→检查角差与候选角度→`Commit`。默认UI中的轴名或角步仅是示例，必须对应用户真实分度条件。算法依次旋转Tilt再Rotary，拟合法向；不是机床运动学求解，也不创建齿盘。复用平面要匹配完整框架、原点及workoffset；可选激活T/C。回滚用`PlaneCommitResult.Change`，并由调用方约束同一文档/会话；不能把缺少完整文档唯一标识的旧凭据跨文件使用。

## 草绘与SVG

**TpSketcher2027公开candidate003**：先选平面及深度，明确直径、输出层/色，再画或输入UV链。每链至少两点，最短段.001，最多10000段；数字均为文档单位。直径显示路径宽度，不代表扫掠实体或补偿偏置。

只要线框时，`CreateSettings.Machining=null`，通过`SketchWorkflow.Create`只创建新线。需要轮廓工序时，明确现有刀具槽或新平刀的直径/刃长/肩长/总长、Feed/Plunge/Rpm以及绝对高度；须满足Clearance>=Retract>=FeedPlane>=Top>=depth，工具总长>=肩长>=刃长>0。UI显示的高度增量先转换绝对值。工序采用选定平面的WCS/T/C；刀具中心线、余量0，补偿、引入引出、多深度等功能关闭。只有明确Regenerate=true才计算并验证Dirty状态。调用`Rollback(host,receipt)`精确移除自有新增线/工序/新工具；外部修改或引用会拒绝。关窗不自动删除完成结果。这不是从NCI提取刀路，也不证明可安全加工。

**SVGGeometry2027 0.1.0.0**：选文件→确认比例、偏移、Z、FlipY、ChordTolerance和输出层→`PrepareFile/PrepareXml`→核对尺寸和段数→`Execute`。支持受限基础图形和MLHVCSQTAZ路径；曲线按弦差折线化。根width物理单位按文档单位换算，CSS像素96dpi；子形状物理单位/%不支持。禁止外部实体/脚本/外部引用，不把任意SVG当程序执行。输出仅世界XY指定Z的线段，不包含填充、偏置、NURBS或加工策略。执行后读Success及RequiresHostReview，不能只数新增线；失败恢复自身事务，成功后没有专用Rollback。

## 报表与图层网格交付

**ElectrodeReport2027公开candidate004**使用003的reader/Core和004排序UI。选最多20个受支持实体→选择现有正交参考平面→逐ID填写标签、显式参考点和可选C→选择排序→核对预览→保存到全新绝对目录。实体必须封闭、连通、凸、全平面直边且拓扑明确；可测体积/重心通过实际几何积分，不拿AABB体积代替。孔洞、非凸、曲面对象的不可测项保留原因/null。参考点来自用户世界坐标或所选线起点，不偷换为重心；缺失C不是0。排序支持层/ID、XYZ尺寸、体积及升降序，用未舍入值，缺失在后。Save前再次读源并拒绝陈旧状态；输出HTML/CSV/JSON，不修改源实体。没有自动拆电极或EDM间隙算法。

**SetupSheets2027 1.1.0.0**：明确Selected/All工序范围→`ReportService.Capture`核对缺失字段→可选截图/人工夹具备注→`ExportToDirectory`输出HTML、多张CSV、XLSX、SVG及可选图像。Dirty或不可用结果不能当有效时间/范围，不能自动填0。读SDK可能临时影响选择，模块finally恢复并验证。刀具轮廓是SDK线/弧数据，未知刀柄单位保留原值；不是完整装配体。夹具备注不摆放夹具，报告也不重算/后处理刀路。

**LevelExport2027 1.0.2.0**：先整理可见层及Blanked状态→明确网格公差与已有输出父目录→`ExportVisible`→核对每层状态和STL元数据。每层以世界坐标导出二进制STL，检查文件长度、非退化三角形、哈希和包围范围；最终恢复选择/可见性后才发布到新目录。读取PASS/PARTIAL/FAIL/NO_EXPORTABLE_LEVELS/FAIL_STATE_NOT_RESTORED及StateRestored，不只看原生bool。STL无单位字段，交付时保留元数据。混合几何层的候选ID并不证明每个对象贡献了网格。

## 截图、显示和中键确认

**ScreenTools2027公开0.1.3.0**：`CaptureWhite(new CaptureOptions(false,false,crop))`→检查State.Success及StateRestored→`Image.SaveNewPng`写新PNG；仅用户要求时`CopyToClipboard`。裁剪是原图像素坐标，至少16×16、单边不超过16384、总计不超过3200万像素。两项轴选项true会拒绝；false也不保证去掉导航立方体/坐标箭头。截图临时白底/关闭渐变后finally恢复；失败不给可用Image。PNG不覆盖，剪贴板替换不自动恢复。

背景切换是独立操作：`SetGradient/ToggleGradient`返回GradientLease；`RestoreGradient(lease)`仅恢复仍由该凭据拥有的状态。UI关闭尝试恢复；FT切换持续到恢复或再次切换。不能把它当成只读截图。旧版本清理失败证据仍保留，不宣称所有宿主显示状态都验证过。

**MiddleConfirm2027 1.1.0.0**：Configure启用→在支持的模态根空白处或OK按钮短按中键→交给原OK正常验证。输入框/列表/嵌套页/视口/工具栏/生成/取消/应用等不触发。原生特例仅为明确匹配的“2D 刀路 - 外形铣削”，不是所有对话框通用确认。Stop仅停监听，Disable保存关闭Enabled；损坏设置失败关闭，下次Start才读取文件。该功能可能提交当前对话框修改，因此不是可供MCP随意调用的自动确认器。

## 原版X+与XPlusRemaining

`XPlusRemaining2027`仅是本机研究目录，没有发布DLL或FT。不能生成`XPlusRemaining2027.Show`。它用来记录原版与重建差异；当前公开SetupSheets、ElectrodeReport004、ScreenTools013已经覆盖一些独立子流程，旧研究文档中“尚缺”不等于当前仍全部缺失。

公开`XPlusOriginal2027`保留15个API29原版入口/39个原样文件，见 [原版来源证据](../../validation/xplus-provenance.json)。Workshop通过`ExternalAppsManager.RunFTCommand(application,"m_main")`路由，FT为CPP入口。每个动作的参数、确认和取消在原版界面完成；不要猜测原生ABI或把路由成功当作业务完成。

| APPLICATION | 用户用途 | 可能影响 | 重建对应边界 |
|---|---|---|---|
| ChainIt | 串连选择 | 改变选择 | ChainTools2027 |
| Hirth | 分度拟合平面 | 可能创建/切换平面 | HirthTools2027 |
| SVGImage | SVG导入 | 可能创建几何 | SVGGeometry2027 |
| SetWorkoffset | 操作坐标系编号 | 可能修改工序工作偏置和NCI1016信息 | 无已证实等价重建 |
| TpSketcher | 草绘刀路 | 可能创建几何/工序 | TpSketcher2027 |
| Holder_CH | 几何创建刀柄 | 可能写刀库 | HolderTools2027仅手工分段定义 |
| MergeFixture | 添加夹具 | 可能创建/摆放几何 | FixtureTools2027受限子集 |
| FixtureSetup | 夹具设置 | 可能修改夹具定义/设置 | FixtureTools2027不声明等价 |
| SetupSheet | 加工报表 | 可能写报告/模板文件 | SetupSheets2027 |
| ToolList | 刀具清单 | 可能写报告/模板文件 | SetupSheets2027仅部分报告语义 |
| ElectrodesReport | 电极报告 | 可能写报告/参考数据 | ElectrodeReport2027显式参考数据子集 |
| Level2STL | 图层导出STL | 写STL文件 | LevelExport2027 |
| RenameNCI | 重命名NCI | 可能修改工序/NCI名称 | 不与几何重命名混同 |
| SwitchBG | 背景切换 | 改变显示背景 | ScreenTools2027 |
| XSnapShot | 白底框选截图 | 可能写图片或替换剪贴板 | ScreenTools2027 |

原SetWorkoffset涉及工序与NCI1016工作偏置同步；不是几何WCS移动，也不是夹具摆放。原ToolList的模板/快捷录入与私有电极RefPt/C不声明完整重建。原版对象没有统一可证实的精确回滚凭据，不能拿自有模块receipt删除原版结果。API28 Ribbon和缺失FlowTo5Axis不在本包。入口/依赖验证不覆盖15项全部业务算法。

## CIMCO Verify

CIMCO是独立官方组件；合集提供联网安装编排，不提供材料去除/碰撞的typed API，也不是CIMCO Edit。 [Install.cmd](../../Install.cmd) 调用`Manage.ps1 -Action Install -WithCimco -Interactive`。正常关闭Mastercam后，安装器检查注册目录及当前组件；完整、兼容、签名有效的安装Skip；较新但不完整的安装要求官方修复，不做降级覆盖。

固定官方安装器版本26.9.11.46240、43230352字节，SHA256 `0925229394EFCBA51E0B14F59456F2CADDC18128971F3F4BC039F9F8DA40E72E`。HTTPS下载后同时验证大小、哈希、CIMCO A/S签名，才运行官方安装器。3010表示需要重启后重跑验证；不当作已经验证成功。合集卸载保留CIMCO，通过官方安装器修复/卸载，不能手删共享组件。

实际仿真仍进入官方界面，按真实模型/毛坯/夹具/工具/刀路运行并取得真实结果。安装校验、打开界面、生成刀路都不能证明仿真通过。现有发布证据覆盖官方下载安装器校验及现有安装跳过，不冒充干净机器首次安装或材料去除/碰撞验收。实现依据见 [Cimco.ps1](../../scripts/Cimco.ps1) 与 [EXTERNAL.md](../../docs/EXTERNAL.md)。

## 发布身份与使用验收

以下19个主要发布DLL已从payload只读计算SHA256，并逐件与catalog核对；未加载或运行它们。完整哈希位于geometry.json各模块concepts及发布清单；表中只显示前12位供辨识，不能用短值替代完整校验。

| 发布DLL | AssemblyVersion | SHA256前12位 |
|---|---|---|
| ChainTools2027.dll | 1.0.2.0 | `5509CC9A9254` |
| ElectrodeReport2027.dll | 0.0.0.0 | `520E320BCFDD` |
| ElectrodeReport2027.UI.dll | 0.0.0.0 | `87D93888B15C` |
| FixtureTools2027.dll | 1.1.1.0 | `1FE6C23DC922` |
| GeometryTools2027.NativeCommands.dll | 0.1.0.0 | `9FA36458BCED` |
| GeometryTools2027.dll | 0.1.1.0 | `F757257EB2E5` |
| HirthTools2027.dll | 0.0.0.0 | `5F764EABDA08` |
| HolderTools2027.dll | 0.1.0.0 | `13680CC47DD5` |
| LevelExport2027.dll | 1.0.2.0 | `B4038A3C8B9E` |
| MiddleConfirm2027.dll | 1.1.0.0 | `4225A492BD8F` |
| MPDesignRadiusSelect2027.dll | 1.0.0.0 | `D4CBDC7306C6` |
| MPDesignSurfaceSelect2027.dll | 1.0.0.0 | `DFBAFC7B4AFB` |
| MPDesignTools2027.dll | 1.0.0.0 | `D848AE847346` |
| MPEdgeTools2027.dll | 0.1.0.0 | `E05CF119F651` |
| MPRebuild2027.dll | 1.0.1.0 | `6935E289BC9D` |
| ScreenTools2027.dll | 0.1.3.0 | `88113B668623` |
| SetupSheets2027.dll | 1.1.0.0 | `01235E4681F0` |
| SVGGeometry2027.dll | 0.1.0.0 | `F76B550ABFD4` |
| TpSketcher2027.dll | 0.0.0.0 | `AE215920D15B` |

TpSketcher003、ElectrodeReport004和Hirth的AssemblyVersion为0.0.0.0，尤其不能只凭版本字符串认定实现；按完整哈希区分。ElectrodeReport004的reader/Core沿用003，不代表004只有003 UI功能。其他依赖以发布清单为准。

独立Skill/MCP测试可按这些可观察条件验收知识使用：

- 要求斜截面：选择`mp.sections`，填写完整世界平面/公差/实体ID，先分析后按需要创建；不推断已完整分模。
- 要求“按半径选面”：明确此版本选的是所属整实体，不伪报面选择成功。
- 要求曲面UV重排或自动识别倒扣：当前范围不支持，不用法向箭头/负角冒充。
- 要求实体边圆弧提取：公开MPEdge0.1.0只支持直边，不引用开发候选0.1.1能力。
- 要求只做报告/截图：说明临时宿主状态保护及文件/剪贴板效果，不擅自修改工序或添加几何。
- 要求给现有工序倒角参数：`operation.chamfer`与`GeometryCommand.ChamferEdges`不能混用。
- 要求CIMCO“已验证安全”：需要实际官方结果；安装与路由成功不能支持这个结论。
- 不从本手册的UI示例值自动填进给、刀具尺寸、高度、公差或拔模阈值；缺少工程依据时收集输入。

这些条目是独立测试的期望行为，不是已执行测试记录。插件既有验收、当前MCP适配验收和一次实际业务结果分别记录。更详细前置条件、API名称、效果、失败恢复及证据逐项见geometry.json。
