# 加工插件工作流知识

适用发布快照：2027.10.28.2；整理日期：2026-10-29。配套机器可读文件：[machining.json](machining.json)。8 个模块、58 个流程分组（27 typed_candidate / 25 interactive / 6 not_exposed）。

本文仅整理已读作者源码、当前 payload/catalog、公开文档及已有验收。没有启动宿主、执行加工/后处理、重新反向分析或修改插件。父端另行实现和验收的 MCP 工具，以其实际工具 schema 与测试记录为准；这里的候选分类不构成已实现 MCP 的声明。

## 使用与接口约定

- `typed_candidate`：存在公开参数化 C# 接口，适合评估固定类型封装；不意味着已有端点、无UI副作用或已完成所有宿主验收。
- `interactive`：当前推荐通过中文/原生窗口完成；`Main.Method(int p)` 的 p 是宿主入口参数，不是业务请求。仅打开窗口/FT返回成功不等于业务成功。
- `not_exposed`：诊断、历史底层、反射转发、注册或生命周期辅助，不推荐作为普通 MCP 加工工具。
- `api` 采用 `完整声明类型 :: 源码方法声明`；右侧由 Roslyn **仅语法解析现有源码**提取，保留参数类型、名称、默认值及泛型。不是反射加载产品DLL。DTO字段/单位见 inputs；SDK类型须由宿主解析。
- 所有宿主对象操作串行调度到 Mastercam UI 线程。外部请求传 operation ID、tool slot、view ID、数值和枚举，返回纯DTO；Chain/MCView/Operation/Action/Batch/PocketPlan 留在宿主会话，使用有文档/进程归属的不可猜测句柄。
- Prepare→展示差异→Apply→fresh readback→明确Rollback 是推荐适配方式；这是封装建议。现有只具失败恢复的方法不能冒称具备成功后显式回滚。
- 选择集是部分API的输入。适配层应检查文档、单位、活动组、目标ID及时间戳，并明确是否临时选择/恢复。禁止任意反射方法调用和任意文件路径写入。
- 长度通常为当前文档 mm/inch，平面坐标须说明原点和轴。刀具 Slot ≠ T Number ≠ H/D offset。进给数值按宿主原模式解释，除源码明确合同外不擅称 mm/min 或 mm/rev。
- 成功证据应包含状态、CreatedIds/读回差异、审计与恢复结果。再生须同时记录 raw 返回值及重新获取工序的 Dirty；不读缓存 wrapper 猜测成功。工序生成/再生不等于NC、仿真或碰撞验收。

## 优先建议

1. **P0：只读与纯逻辑**——Workshop ReadPlanes/ReadParameters，OperationTools Information，HSM参数fresh读回，AdvancedDrill DescribePlane/Rules.Plan，LittleBee Materials.Calculate。先固定坐标/单位与结果DTO。
2. **P1：现成批次闭环**——OperationTools Depth/Finish/Chamfer/ReplaceGeometry/Sequence/Drilling，HSM Prepare/Apply/Regenerate/Rollback，AD012 Prepare/Apply/Rollback/限定重试。外部Chain输入需完整独立原生链；保留状态和防重放守卫。
3. **P2：有额外约束的流程**——Porsche投影/复杂孔、AD013显式目标G84。SolidBoundary Create和Workshop写操作需补成功后的归属快照/回滚策略，不能复用通用“撤销最近操作”。
4. **保留交互**——Porsche特定构建补面、LittleBee原生编辑/导入/文件保存/批量文件测量/后处理，以及Workshop路由。诊断、历史ApplyOwned、任意ExistingModule和fixture不开放。

## 冻结版本与来源核对

当前8个业务DLL及8个FT的实际SHA-256均与 catalog/package.json 一致（16/16）。版本来自catalog；本次只算文件哈希，没有加载/重编产品。不要按同一程序集版本号推断字节一致。

| 模块 | 发布版本 | DLL SHA-256 |
|---|---|---|
| HSMRebuild2027 | 0.1.0.0 | `2862C7CD7E7203FE373F89EDDC1F58CB2627002CB94D224F9C383D98D30BC69C` |
| OperationTools2027 | 1.0.3.0 | `26074B7E8EEBEE2C6B2CA52D1ED9744F42DDC894D245B86B4610E71C656A4B50` |
| PorscheAdvanced2027 | 1.0.0.0 | `DA8E4F21100013EB766CB5C62DF47768A039E59A8CB5E986FB2D7A2FA2F231CE` |
| AdvancedDrill2027 | 0.1.2.0 | `BFE58820F988BEB388E9896EEFC06C970A5E056EEEEE071513EB016FC35DAA95` |
| AdvancedDrillTap2027 | 0.1.3.0 | `F1056CC3C252B3221BF99D6E5359BEBB4E70B5E8F179323E12D1048FC5CD92A6` |
| SolidBoundary2027 | 1.0.5.0 | `F887E35629305917BA6968E3E762D8DBEA2B61F2F2FEB73C0F69FE47035C591A` |
| LittleBee2027 | 2.0.0.0 | `52C059253E5E63DE87457B00DB3D552340B486C9C7950ED2BAFB1E0D1E538975` |
| Workshop2027 | 2.8.0.0 | `4E9B1E0836D46A69068FD3D5429A37551CA631CF3449E886D3CDE1C6F196E384` |

| 模块 | 作者源码 / dist差异处理 |
|---|---|
| HSMRebuild2027 | 作者root dist与payload DLL一致；FT已提升资源修复01，当前FT为8F751974…；旧freeze/build记录中的旧FT哈希只属历史。 |
| OperationTools2027 | 作者root dist与payload一致；使用1.0.3仿射范围修正与独立原生链输入合同。 |
| PorscheAdvanced2027 | Build.ps1从root src构建到candidates/1.0.0，候选DLL与payload一致；root dist为59D1FD3A…旧DLL，不能当发布版。 |
| AdvancedDrill2027 | 使用candidates/AD012/src及其dist；root dist为434C976A…旧版本；旧HANDOFF的pending/Off0被AD012独立验收补充取代。 |
| AdvancedDrillTap2027 | 使用tap-contract/candidates/AD013/src/dist；独立命名空间AdvancedDrillTap2027。Top G84后续验收补充取代早期compile-only状态。 |
| SolidBoundary2027 | 使用candidates/ExistingOutput105/src/dist；root dist为3EECF169…1.0.4。禁止把旧版新层策略混入当前已有可见层合同。 |
| LittleBee2027 | LittleBee2027-independent/dist与payload一致；10份src文件哈希均与其build-manifest一致；不是旧LittleBee2027兼容/反编译目录。 |
| Workshop2027 | 使用公开repo:src/Workshop；payload为2.8.0整合版；作者WorkshopTools2027根dist为CAC432B4…旧产物。 |

证据定位：`repo:` 相对于公开仓库根；`author:` 相对于开发工作区的“外挂插件”目录。作者源码/原始报告未全部随公开包发布，不能把这些定位符当成公开URL；JSON保留其SHA-256/行号与公开验收摘要。源码签名证明来自所读源码；未在本轮重编来证明完整二进制可重现。

验收等级：HSM三策略创建/回读，HighSpeed与恒定重叠螺旋再生，TrueSpiral未再生；OperationTools依据1.0.3补充验收；Porsche91项native与10项离线投影；AD012九链36次再生；AD013仅给定目标Top G84；Solid105限定凸多面体与已有可见层。LittleBee多数功能不能由四编辑窗口/单次复制元数据证据推广。每个evidence指向的验收只在其原报告范围内有效。

## 流程目录

| ID | 用途 | 自动化分类 |
|---|---|---|
| hsm.create | 单闭合边界新建高速/摆线挖槽 | typed_candidate |
| hsm.readback | 检查本批状态与当前挖槽参数 | typed_candidate |
| hsm.regenerate | 计算本批新建挖槽 | typed_candidate |
| hsm.rollback | 显式回滚本批工序 | typed_candidate |
| hsm.ui | 打开挖槽面板与创建表单 | interactive |
| op.finish | 粗加工参数转精光 | typed_candidate |
| op.chamfer | 2D轮廓转倒角 | typed_candidate |
| op.depth | 批量修改2D深度 | typed_candidate |
| op.replace_geometry | 替换2D轮廓/挖槽完整串连 | typed_candidate |
| op.detect_drill | 检测简单孔并按用户规则创建钻孔 | typed_candidate |
| op.sequence | 闭合边界粗轮廓→精光→倒角 | typed_candidate |
| op.information_reach | 读取时间/范围/轴向装刀下界 | typed_candidate |
| op.rollback | 回滚最近或持有的批次 | typed_candidate |
| op.ui_config | 加工面板与钻孔规则配置 | interactive |
| porsche.project | 实体投影分析与生成边界 | typed_candidate |
| porsche.boundary_sequence | 实体边界→粗/精/倒角三工序 | typed_candidate |
| porsche.holes | 孔特征识别→中心钻/钻孔/沉孔/沉头 | typed_candidate |
| porsche.heal | 按完整孔在独立实体副本上删孔补面 | interactive |
| porsche.session | 面板导航与回滚最近生成 | interactive |
| porsche.legacy_heal | 历史直接删孔辅助API（不开放自动化） | not_exposed |
| ad012.prepare_create | 计划并创建分阶段钻孔链 | typed_candidate |
| ad012.recovery | 批次回滚与限定重试 | typed_candidate |
| ad012.ui | 中文阶段表单、点来源与预览 | interactive |
| ad012.store_internal | 阶段存储低层接口（不直接暴露） | not_exposed |
| ad013.prepare_create | 计划并创建中心钻→预钻→公制右旋G84 | typed_candidate |
| ad013.recovery | 批次回滚与限定重试 | typed_candidate |
| ad013.ui | 中文阶段表单、点来源与预览 | interactive |
| ad013.store_internal | 阶段存储低层接口（不直接暴露） | not_exposed |
| solid_boundary.preview_create | 凸多面体边界预览→创建 | typed_candidate |
| solid_boundary.ui | 已有可见层边界表单 | interactive |
| solid_boundary.fixture | 内嵌诊断/fixture入口（不暴露） | not_exposed |
| bee.hub | 小蜜蜂功能集锦 | interactive |
| bee.edit | 编辑工序、刀具、几何与共同参数 | interactive |
| bee.copy_paste | 复制工序并粘贴到明确位置 | interactive |
| bee.rename | 群组与NCI程序名称预览重命名 | interactive |
| bee.follow_view | WCS跟随开关与立即切换坐标 | interactive |
| bee.save | 保存/另存为并可附现有毛坯尺寸 | interactive |
| bee.geometry | 坐标展开、旋转、对齐、图层与结果几何 | interactive |
| bee.toolsheet | 程序/刀具报告、工单模板与截图 | interactive |
| bee.materials_calc | 材料毛坯重量/成本计算与清单导入 | typed_candidate |
| bee.materials_ui_batch | 材料库维护及批量实体测量 | interactive |
| bee.machines | 机床/后处理/输出配置与适配合同 | interactive |
| bee.exchange | 导出/导入工序库与模板管理 | interactive |
| bee.post | 显式执行/后处理（仅交互流程） | interactive |
| bee.registration | 启动注册与跟随通知（不直接开放） | not_exposed |
| workshop.inspect | 读取所选工序三面与参数 | typed_candidate |
| workshop.parameters | 批量设置2D工序进给/转速/余量 | typed_candidate |
| workshop.planes | 将WCS/构图/刀具三面统一 | typed_candidate |
| workshop.groups | 批量创建刀路群组与插入位置 | typed_candidate |
| workshop.views | 最近世界正交视图、跟随选项与视图对正 | typed_candidate |
| workshop.stock | 设置矩形毛坯并回读 | typed_candidate |
| workshop.hub_templates | 工艺助手总面板、模板导入与使用目录 | interactive |
| workshop.route_machining | 加工业务路由 | interactive |
| workshop.route_bee | 小蜜蜂工序编辑路由 | interactive |
| workshop.route_geometry | 几何、夹具、链、曲面与MP路由 | interactive |
| workshop.route_reporting | 截图、程序单、电极报告与中键配置路由 | interactive |
| workshop.route_original | 15个X+原版入口路由 | interactive |
| workshop.registration | 页签注册与低层转发辅助（不做加工工具） | not_exposed |

## HSMRebuild2027

0.1.0：基于公开 PocketOperation 的真实高速/摆线、恒定重叠螺旋、TrueSpiral 挖槽编排；业务 DLL 冻结，FT资源修复已验收。

- HighSpeed 是 Pocket 的真实粗加工策略；PocketSubtype=Standard 并不等于 Dynamic Mill、OptiRough 或完整 HSM 内核。
- 径向步距与轴向层深控制不同方向；摆线环尺寸仅在 HighSpeed 下启用。
- 创建、回读、计算、回滚是不同步骤；创建成功不代表已有有效刀路。
- typed_candidate 仅表示适合将现有公开 C# 接口封装，本文没有实现任何 MCP。

### hsm.create · 单闭合边界新建高速/摆线挖槽

**typed_candidate** · 已有参考工序、边界及合格平底刀，需要明确参数的新 Pocket。

**输入与单位**：referenceId: int；已保存文档中当前机床组的一项未锁定二维 Contour/Pocket 参考工序。UI 要求恰选一项。；chains: Mastercam.Database.Chain[]；参考工序的完整原生链结果，恰一条闭合平面链；不要把多个原生链包装器过滤/截断后提交。；settings.Name: string，1–50可显示字符；settings.Metric: bool，必须等于文档；长度为 mm 或 inch，不自动转换；settings.ToolSlot: int，现有平底立铣刀内部槽号，不是 T 刀号；settings.ToolDiameter: double，与现有刀具一致；settings.Strategy: PocketStrategy: HighSpeed | ConstantOverlapSpiral | TrueSpiral；settings.Trochoid: TrochoidMode: Off=0 | FullMaterialOnly=1 | EntirePocket=2；非HighSpeed必须Off；settings.Entry: EntryChoice: Helix | Ramp；settings.Climb: bool，顺铣；settings.MinimizeBurial: bool；settings.SpiralOut: bool；settings.StepOver: double，0<径向步距<刀径；settings.StepDown: double，最大层深>0；settings.WallStock: double>=0；settings.FloorStock: double>=0且小于Top-Bottom；settings.Tolerance: double，0<容差<StepOver；settings.LoopRadius: double，摆线开启时>0；settings.LoopSpacing: double，摆线开启时0<间距<=2*LoopRadius；settings.SmoothingRadius: double>=0；settings.EntryMinimum: double>0；Helix半径/Ramp长度；settings.EntryMaximum: double>=EntryMinimum；settings.EntryAngle: double，度，0<角度<90；settings.EntryClearanceXY: double>=0；settings.EntryClearanceZ: double>=0；settings.Clearance: double，刀具平面绝对Z；settings.Retract: double，刀具平面绝对Z；settings.FeedPlane: double，刀具平面绝对Z；settings.Top: double，刀具平面绝对Z；settings.Bottom: double，刀具平面绝对Z；settings.Feed: double>0，宿主进给模式原始数值；settings.Plunge: double>0，同上；settings.RetractFeed: double>0，同上；settings.Rpm: int>0，rpm；settings.ReviewedCuttingData: bool=true，用户确认；不是模式设置开关。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文件；无其他撤销事务；链几何未改变，与参考刀具平面一致。；现有刀具在同机床组、单位/刀径相符、刃长覆盖总深度；参考非恒线速。；Clearance>=Retract>=FeedPlane>Top>Bottom；先确认全部切削数据。

**流程**：1. 准备 settings 并 Validate；读取参考与完整单链。 2. Host.Prepare 获取会话内 PocketPlan，向用户展示计划。 3. 仅确认后 Apply；取 CreatedId、Status、Observations 与 AuditPath。

**输出**：一个真实 PocketOperation；严格字段/刀具/链回读；状态与审计JSON。

**副作用**：新增1工序，Posting=false、Dirty=true；继承参考的机床/坐标设置。；写 HSMREBUILD2027_DATA 或 %LOCALAPPDATA%/HSMRebuild2027 审计；不保存文档、不post。

**回滚/失败**：Apply失败执行自有对象清理；成功后用同一 PocketPlan.Rollback。人工编辑、文档/源/工具变化会阻止盲删。

**限制**：不支持岛屿、开放挖槽、残料模型、三维自适应、五轴或旧HSM格式。；宿主进给模式未由API自动设置；默认值不能当作切削建议。

**公开签名**：

```csharp
HSMRebuild2027.Host :: public static PocketPlan Prepare(int referenceId,Chain[] chains,PocketSettings settings)
HSMRebuild2027.PocketSettings :: public void Validate()
HSMRebuild2027.PocketSettings :: public PocketSettings Copy()
HSMRebuild2027.PocketPlan :: public void Apply()
```

**证据**：`author:MC2027-PluginSuite/HSMRebuild2027/src/Host.cs#L36`；`author:MC2027-PluginSuite/HSMRebuild2027/src/Core.cs#L49`；`author:MC2027-PluginSuite/HSMRebuild2027/src/Core.cs`；`repo:validation/hsm-native-acceptance.json`；`repo:validation/bundle-host-integration.json`。逐源SHA-256在JSON中。

### hsm.readback · 检查本批状态与当前挖槽参数

**typed_candidate** · 创建或重算后需要区分期望值、历史观察和fresh参数。

**输入与单位**：operationId: int=本批CreatedId；entry: EntryChoice，必须与计划入刀方式一致；plan: 同会话对象；读取Id/Document/Status/Error/CreatedId/Settings/Observations/AuditPath。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. UI Readback 展示最近计划及已记录观察。 2. typed适配应 Host.Read 后确认 PocketOperation，再 Host.Parameters；连同计划字段返回。

**输出**：参数字典、平面/链描述、状态、审计路径。

**副作用**：Read/Parameters本身只读；LastPlan是会话状态。

**回滚/失败**：只读无需回滚。

**限制**：UI Readback显示计划/历史观察，不等于每次重新比较数据库；typed层需明确fresh标记。

**公开签名**：

```csharp
HSMRebuild2027.Host :: public static int[] AllIds()
HSMRebuild2027.Host :: public static int[] SelectedIds()
HSMRebuild2027.Host :: public static Operation Read(int id)
HSMRebuild2027.Host :: public static object Frame(MCView v)
HSMRebuild2027.Host :: public static object ChainInfo(Chain[] chains)
HSMRebuild2027.Host :: public static Dictionary<string,object> Parameters(PocketOperation o,EntryChoice entry)
HSMRebuild2027.Main :: public MCamReturn Readback(int p)
```

**证据**：`author:MC2027-PluginSuite/HSMRebuild2027/src/Host.cs#L21`；`author:MC2027-PluginSuite/HSMRebuild2027/src/Main.cs#L23`；`repo:validation/hsm-native-acceptance.json`；`repo:validation/bundle-host-integration.json`。逐源SHA-256在JSON中。

### hsm.regenerate · 计算本批新建挖槽

**typed_candidate** · 已创建且尚未计算，用户明确要求计算。

**输入与单位**：plan: 同会话已Applied的PocketPlan。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；本批归属、工序参数和文档仍通过计划守卫。

**流程**：1. 显示新建工序ID并确认。 2. 调用 PocketPlan.Regenerate；保存raw结果与重新获取工序的Dirty和参数读回。

**输出**：原生计算观察及更新后的回滚检查点。

**副作用**：仅重算本批新工序，生成宿主刀路缓存；不post/NC、不保存文档。

**回滚/失败**：同计划 Rollback；不能用旧缓存包装器Dirty判断再生失败。

**限制**：HighSpeed与ConstantOverlapSpiral已native重算PASS；TrueSpiral只验证创建/回读。；raw=true及fresh Dirty=false不证明逐段轨迹、碰撞或机床安全。

**公开签名**：

```csharp
HSMRebuild2027.PocketPlan :: public void Regenerate()
HSMRebuild2027.Main :: public MCamReturn Recalculate(int p)
```

**证据**：`author:MC2027-PluginSuite/HSMRebuild2027/src/Host.cs#L209`；`author:MC2027-PluginSuite/HSMRebuild2027/src/Main.cs#L24`；`repo:validation/hsm-native-acceptance.json`；`repo:validation/bundle-host-integration.json`。逐源SHA-256在JSON中。

### hsm.rollback · 显式回滚本批工序

**typed_candidate** · 撤回本会话刚创建、且未被外部编辑的结果。

**输入与单位**：plan: 原PocketPlan对象，不是反序列化审计文件。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；回到同文档，保留会话计划；所有归属/时间戳/参数守卫通过。

**流程**：1. 展示CreatedId与归属。 2. 调用Rollback并读状态/审计。

**输出**：RolledBack或明确失败原因。

**副作用**：删除本批新工序；保留源工序/刀具/边界。

**回滚/失败**：回滚本身不提供redo；失败保留审计，不通过改守卫强制删除。

**限制**：进程关闭后不承诺恢复内存计划。

**公开签名**：

```csharp
HSMRebuild2027.PocketPlan :: public void Rollback()
HSMRebuild2027.Main :: public MCamReturn Rollback(int p)
```

**证据**：`author:MC2027-PluginSuite/HSMRebuild2027/src/Host.cs#L203`；`author:MC2027-PluginSuite/HSMRebuild2027/src/Main.cs#L25`；`repo:validation/hsm-native-acceptance.json`；`repo:validation/bundle-host-integration.json`。逐源SHA-256在JSON中。

### hsm.ui · 打开挖槽面板与创建表单

**interactive** · 使用中文属性界面检查参数。

**输入与单位**：p: int，FT宿主参数；不是业务参数；selection: 恰选一项参考工序。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 工艺助手 HsmPocket 或 HSMRebuild2027.CreatePocket；总面板 OpenHub。 2. 填写参数、预览、确认创建；另行计算或回滚。

**输出**：模态面板及用户确认后的上述结果。

**副作用**：仅打开/取消不应创建工序；提交才产生create流程效果。

**回滚/失败**：取消表单；已创建结果依照本批Rollback。

**限制**：FT依赖 Workshop2027.Resources.dll 与 dnRES_NAME Workshop2027.NETHook；FT SHA 8F751974...已通过安装重启UI验收。

**公开签名**：

```csharp
HSMRebuild2027.Main :: public MCamReturn OpenHub(int p)
HSMRebuild2027.Main :: public MCamReturn CreatePocket(int p)
```

**证据**：`author:MC2027-PluginSuite/HSMRebuild2027/src/Main.cs#L21`；`repo:validation/hsm-native-acceptance.json`；`repo:validation/bundle-host-integration.json`。逐源SHA-256在JSON中。

## OperationTools2027

1.0.3：现有2D工序参数转换、链替换、按规则钻孔、三轮廓编排，以及修正原点后的范围/时间/装刀下界报告。

- Finish/Chamfer/Depth/ReplaceGeometry直接修改所给现有工序；Sequence/Drilling创建新工序。
- Slot为刀具内部槽，Number为T号，LengthOffset/ DiameterOffset为H/D；不得混用。
- Information的时间是有效缓存刀路的SDK秒数；装刀长度只是轴向下界。
- 1.0.3读取的刀具平面范围已扣除平面原点在各轴投影，不把旋转世界坐标端点当局部端点。

### op.finish · 粗加工参数转精光

**typed_candidate** · 将Basic contour或Standard pocket改为明确刀具与零余量精光。

**输入与单位**：ids: int[]；config.Tool.ExistingSlot: int；内部槽号优先，不是刀号；config.Tool.CreateIfMissing: bool，必须显式允许；指定ExistingSlot时不可同时建刀；config.Tool.Kind: ToolKind: FlatEndMill | ChamferMill | Drill；config.Tool.Number: int；刀号；config.Tool.LengthOffset: int；H；config.Tool.DiameterOffset: int；D；config.Tool.Name: string；新刀必填；config.Tool.Diameter: double；当前文档长度单位；config.Tool.OverallLength: double；config.Tool.FluteLength: double；config.Tool.ShoulderLength: double；刃长<=肩长<=总长；config.Tool.ShankDiameter: double；config.Tool.TipAngleDegrees: double；0..180度的内部角；config.Tool.TipDiameter: double；0<=值<刀径；config.Tool.Flutes: short>=1；新刀必填；config.Cutting.Feed: double>0；宿主原进给模式数值；config.Cutting.Plunge: double>0；config.Cutting.Retract: double>0；config.Cutting.Rpm: int>0；config.Cutting.ConfirmOriginalFeedMode: bool=true；不切换每分/每转模式；config.Compensation: Computer|Control|Wear|ReverseWear；config.Side: Left|Right；config.UseDepthCuts: bool；config.MaximumStepDown: double>0，启用分层时。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。

**流程**：1. PrepareFinish预检并展示Batch.Plan。 2. 确认后Apply；核工具、H/D、零余量、精光次数、补偿、Dirty及审计。

**输出**：PreparedChange/ChangeBatch；逐字段读回。

**副作用**：改原工序，可能创建刀具；标记Dirty；写审计。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：仅Basic contour/Standard pocket；Pocket分支不能从Contour测试推广为全部已验收。

**公开签名**：

```csharp
OperationTools2027.Host :: public static PreparedChange PrepareFinish(int[] ids,FinishConfig config)
OperationTools2027.PreparedChange :: public void Apply()
OperationTools2027.Main :: public MCamReturn Finish(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/HostCommands.cs#L99`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L23`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.chamfer · 2D轮廓转倒角

**typed_candidate** · 明确边缘宽度与刀尖偏移后将轮廓工序改为Chamfer2D。

**输入与单位**：ids: int[]；config.Tool.ExistingSlot: int；内部槽号优先，不是刀号；config.Tool.CreateIfMissing: bool，必须显式允许；指定ExistingSlot时不可同时建刀；config.Tool.Kind: ToolKind: FlatEndMill | ChamferMill | Drill；config.Tool.Number: int；刀号；config.Tool.LengthOffset: int；H；config.Tool.DiameterOffset: int；D；config.Tool.Name: string；新刀必填；config.Tool.Diameter: double；当前文档长度单位；config.Tool.OverallLength: double；config.Tool.FluteLength: double；config.Tool.ShoulderLength: double；刃长<=肩长<=总长；config.Tool.ShankDiameter: double；config.Tool.TipAngleDegrees: double；0..180度的内部角；config.Tool.TipDiameter: double；0<=值<刀径；config.Tool.Flutes: short>=1；新刀必填；config.Cutting.Feed: double>0；宿主原进给模式数值；config.Cutting.Plunge: double>0；config.Cutting.Retract: double>0；config.Cutting.Rpm: int>0；config.Cutting.ConfirmOriginalFeedMode: bool=true；不切换每分/每转模式；config.Compensation: Computer|Control|Wear|ReverseWear；config.Side: Left|Right；config.Width: double>0；倒角宽；config.ToolTipOffset: double>=0；config.ChamferDepth: double>=0。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。

**流程**：1. PrepareChamfer，明确真实ChamferMill刀。 2. Apply后以CutParams.ContourSubtype回读，不能只读顶层缓存Subtype。

**输出**：改为Chamfer2D的现有Contour及审计。

**副作用**：换刀绑定、清零壁/底余量、关闭多重径向与深度分层；标Dirty。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：不是挖槽转倒角；挖槽边缘须明确新建Contour。

**公开签名**：

```csharp
OperationTools2027.Host :: public static PreparedChange PrepareChamfer(int[] ids,ChamferConfig config)
OperationTools2027.Main :: public MCamReturn Chamfer(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/HostCommands.cs#L121`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L24`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.depth · 批量修改2D深度

**typed_candidate** · 数值修改所选工序连接深度。

**输入与单位**：ids: int[]；config.Depth: double有限；文档单位，按原生Linking深度坐标语义；config.Incremental: bool；设置原生DepthIncremental，不是把输入加到原深度；config.DetachAssociativeDepth: bool；原有深度关联时需显式true。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。

**流程**：1. PrepareDepth检查关联。 2. 确认绝对/增量模式后Apply并fresh回读。

**输出**：更新Depth、DepthIncremental、DepthAssociative=false。

**副作用**：改原工序、解除被明确许可的关联、Dirty。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：不是图形拾点；不自动检查夹具或刀柄碰撞。

**公开签名**：

```csharp
OperationTools2027.Host :: public static PreparedChange PrepareDepth(int[] ids,DepthConfig config)
OperationTools2027.Main :: public MCamReturn Depth(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/HostCommands.cs#L138`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L25`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.replace_geometry · 替换2D轮廓/挖槽完整串连

**typed_candidate** · 目标工序应使用另一条明确边界。

**输入与单位**：ids: int[]；chains: Chain[]；同平面有效完整独立原生链；Pocket必须闭合；链View与ToolPlane.ViewNumber相同。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。

**流程**：1. 交互重选完整链，或构建独立原生链列表；不要LINQ过滤共享原生链包装器。 2. PrepareReplaceGeometry预览来源ID/时间戳后Apply；比较新链与目标，保留原链快照。

**输出**：精确新链成员/顺序/方向读回与回滚快照。

**副作用**：改现有工序关联并Dirty；不改输入几何。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：外部数组隔离不是当前预检可证明的条件；typed层必须自己建立完整链或限制交互获取。；独立Contour A→B→A已验收，不能推广所有Pocket、多链、多目标组合。

**公开签名**：

```csharp
OperationTools2027.Host :: public static PreparedChange PrepareReplaceGeometry(int[] ids,Chain[] chains)
OperationTools2027.Main :: public MCamReturn ReplaceGeometry(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/HostCommands.cs#L146`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L29`；`author:MC2027-PluginSuite/OperationTools2027/evidence/API-CHAIN-INPUT-CONTRACT.md`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.detect_drill · 检测简单孔并按用户规则创建钻孔

**typed_candidate** · 已选实体简单孔、完整圆或点，需要真实DrillOperation。

**输入与单位**：referenceId: int，未锁定2D参考；selection: 预选非隐藏实体/完整圆/PointGeometry；选区参与检测；config.Metric: bool，匹配文档；config.ClearanceAboveTop: double>0；config.RetractAboveTop: double>0；config.FeedAboveTop: double>0；config.WireframeDepth: double>0，点/圆需要；config.PointDiameter: double>0，点需要；config.IgnoreColor: int，-1不忽略；config.Rules: DrillRule[]；闭区间MinDiameter/MaxDiameter不得重叠；每条Label、Tool、Cutting、Cycle(Drill|PeckDrill|ChipBreak)、Peck、PeckClearance、ChipBreak、DwellSeconds、AddTipDepth、ThroughDistance。Tool与Cutting结构同op.finish。。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。；当前机床组=参考工序组；工具直径匹配孔径；刃长覆盖总加工深度。

**流程**：1. DetectSelectedHoles返回Holes/Skipped/SourceTimestamps；核对被跳过项。 2. 确认DrillConfig；PrepareDrilling重新检测，按规则和精确Top/Bottom分组。 3. Apply；核DrillPoints局部坐标、循环、深度、刀具、Posting=false/Dirty=true。

**输出**：HoleReport或新建DrillOperation批次。

**副作用**：创建工序，必要时建刀；写审计；不自动再生/NC。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：实体仅单圆柱Simple、正当前刀轴；复合/斜向不匹配孔跳过。；AddTipDepth显式加 D/(2*tan(夹角/2))，通孔额外量另加；实体盲孔不允许ThroughDistance>0。；不识别螺纹、不按材料表自动填安全参数。

**公开签名**：

```csharp
OperationTools2027.Host :: public static HoleReport DetectSelectedHoles(int referenceId,DrillConfig config)
OperationTools2027.Host :: public static PreparedChange PrepareDrilling(int referenceId,DrillConfig config)
OperationTools2027.Main :: public MCamReturn Drill(int p)
OperationTools2027.Main :: public MCamReturn DetectHoles(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/Drilling.cs#L33`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L26`；`author:MC2027-PluginSuite/OperationTools2027/src/Drilling.cs`；`author:MC2027-PluginSuite/OperationTools2027/src/Core.cs`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.sequence · 闭合边界粗轮廓→精光→倒角

**typed_candidate** · 有用户确认的2D完整闭合链，需要三道顺序工序。

**输入与单位**：referenceId: int；chains: 完整独立原生Chain[]，闭合共面且与参考刀具平面一致；config.RoughTool.ExistingSlot: int；内部槽号优先，不是刀号；config.RoughTool.CreateIfMissing: bool，必须显式允许；指定ExistingSlot时不可同时建刀；config.RoughTool.Kind: ToolKind: FlatEndMill | ChamferMill | Drill；config.RoughTool.Number: int；刀号；config.RoughTool.LengthOffset: int；H；config.RoughTool.DiameterOffset: int；D；config.RoughTool.Name: string；新刀必填；config.RoughTool.Diameter: double；当前文档长度单位；config.RoughTool.OverallLength: double；config.RoughTool.FluteLength: double；config.RoughTool.ShoulderLength: double；刃长<=肩长<=总长；config.RoughTool.ShankDiameter: double；config.RoughTool.TipAngleDegrees: double；0..180度的内部角；config.RoughTool.TipDiameter: double；0<=值<刀径；config.RoughTool.Flutes: short>=1；新刀必填；config.RoughCutting.Feed: double>0；宿主原进给模式数值；config.RoughCutting.Plunge: double>0；config.RoughCutting.Retract: double>0；config.RoughCutting.Rpm: int>0；config.RoughCutting.ConfirmOriginalFeedMode: bool=true；不切换每分/每转模式；config.RoughCompensation: Compensation；config.RoughSide: CompSide；config.RoughWallStock: double>=0；config.RoughFloorStock: double>=0；config.RoughPasses: short>=1；config.RoughPassSpacing: double>0；config.RoughMaximumStepDown: double>0；config.Finish: FinishConfig，见op.finish；config.Chamfer: ChamferConfig，见op.chamfer；config.TopStock: double；config.Bottom: double；config.Clearance: double；config.Retract: double；config.FeedPlane: double；均刀具平面绝对高度。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。；Clearance>=Retract>=FeedPlane>TopStock>Bottom；新刀号不可冲突。

**流程**：1. PrepareSequence展示3阶段和刀具计划。 2. Apply；核三Contour的切削、补偿、几何、坐标和Post/Dirty。

**输出**：粗轮廓、精光、倒角3个真实Contour工序。

**副作用**：创建工序/可选刀具；保留参考与几何；Posting=false、Dirty=true。

**回滚/失败**：保留 PreparedChange.Batch 句柄；Apply失败会显式恢复所触及参数并清理自建工序/未被引用的自建刀具。成功后 Batch.Rollback 按时间戳/字段/源链守卫恢复；刀路仍需重算，遇 RestoreIncomplete 不可自动重复执行。

**限制**：不是Pocket/HSM、体积清料或自动实体投影；三阶段默认不自动重算。

**公开签名**：

```csharp
OperationTools2027.Host :: public static PreparedChange PrepareSequence(int referenceId,Chain[] chains,SequenceConfig config)
OperationTools2027.Main :: public MCamReturn AutoProgram(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/Sequence.cs#L41`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L32`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.information_reach · 读取时间/范围/轴向装刀下界

**typed_candidate** · 需要可审计刀路信息或同刀平面的下界估算。

**输入与单位**：ids: int[]；reach: 可null；ReachConfig{ObstacleTopInToolPlane:double,ClearanceMargin:double>=0}，同刀具平面局部Z/文档单位。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；Reach时全部工序同ToolPlane；原选择必须可由托管API读取以保证恢复。

**流程**：1. Information(ids,null)读信息；需要Reach则明确障碍最高Z与净空。 2. 返回每行Unavailable/Dirty/有效范围/raw秒数，禁止把null解释为0加工时间。

**输出**：类型、刀具、机床/三面、世界/局部/原始范围、有效时间累计、可选AxialStickoutLowerBound。

**副作用**：原生查询可能临时改选择；finally恢复并核对；不重算、不保存。

**回滚/失败**：选择自动恢复；只读业务参数无需回滚。

**限制**：max(0,障碍最高Z-局部刀尖最低Z)+净空；不是最短安全装刀长度、碰撞检查或实际节拍保证。；Dirty/无有效NCI时不返回有效时间或装刀估算。

**公开签名**：

```csharp
OperationTools2027.Host :: public static LocalExtentRange LocalToolPlaneExtents(OperationExtentsData e,MCView plane)
OperationTools2027.Host :: public static object Information(int[] ids,ReachConfig reach=null)
OperationTools2027.Host :: public static Operation Read(int id)
OperationTools2027.Host :: public static Operation ReadEditable(int id)
OperationTools2027.Host :: public static Operation[] Selected()
OperationTools2027.Main :: public MCamReturn Information(int p)
OperationTools2027.Main :: public MCamReturn Reach(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/Reports.cs#L22`；`author:MC2027-PluginSuite/OperationTools2027/src/Transactions.cs#L149`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L30`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.rollback · 回滚最近或持有的批次

**typed_candidate** · 需要恢复上述修改或删除本批新增对象。

**输入与单位**：batch: PreparedChange.Batch会话对象；UI使用内部LastBatch。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档；工序ID非空、唯一、未锁定；无其他Undo事务；平面与机床组符合该操作。

**流程**：1. 先核Status=Applied与后续编辑守卫。 2. ChangeBatch.Rollback并检查Status/Error/Readbacks/AuditPath。

**输出**：恢复参数/原链或移除本批对象的记录。

**副作用**：恢复后仍Dirty；只清理未被其他工序引用的自建刀。

**回滚/失败**：会话内一次回滚；不保证跨重开恢复。

**限制**：Host.LastBatch是internal，typed外部应保存Prepare返回的Batch，不能直接调用internal成员。

**公开签名**：

```csharp
OperationTools2027.ChangeBatch :: public void Rollback()
OperationTools2027.Main :: public MCamReturn Rollback(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/Transactions.cs#L116`；`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L33`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

### op.ui_config · 加工面板与钻孔规则配置

**interactive** · 交互编辑规则JSON和预览各项业务操作。

**输入与单位**：p: int，宿主入口参数；不是配置JSON。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. OpenHub选择功能；DrillConfig编辑/保存明确钻孔规则，再DetectHoles/Drill。

**输出**：规则配置文件与交互预览。

**副作用**：保存用户配置；业务提交效果见对应流程。

**回滚/失败**：取消配置窗口；恢复旧配置需用户备份，批次Rollback不撤销磁盘配置。

**限制**：FT共享Workshop资源；JSON工具字段不等于已适配的MCP schema。

**公开签名**：

```csharp
OperationTools2027.Main :: public MCamReturn OpenHub(int p)
OperationTools2027.Main :: public MCamReturn DrillConfig(int p)
```

**证据**：`author:MC2027-PluginSuite/OperationTools2027/src/Main.cs#L22`；`repo:validation/README.md`；`author:MC2027-PluginSuite/OperationTools2027/HANDOFF-1.0.3.md`。逐源SHA-256在JSON中。

## PorscheAdvanced2027

1.0.0发布候选：实体投影边界与三轮廓工序、完整孔副本补面、孔段识别到分阶段工序。发布DLL来自candidates/1.0.0，不是根dist。

- 投影使用三角网格并集，支持凹轮廓/内环/分离区域；结果是有容差的折线，不是精确B-rep silhouette。
- 复杂孔流程按真实入口、轴与孔段编排；轴向可达不代表碰撞检查。
- 副本补面保留源实体；私有特定构建桥接是现有实现事实，不可包装成通用公开SDK。
- 默认HoleSettings.Regenerate=true；这些流程与HSM/AD012的仅创建行为不同。

### porsche.project · 实体投影分析与生成边界

**typed_candidate** · 将一个或多个可见实体投影到指定加工平面，保留凹形/孔环。

**输入与单位**：solidIds: int[]，非空不重复可见SolidGeometry；frame: PlaneFrame(V3 Origin,V3 X,V3 Y,V3 Z)，右手正交；世界原点/单位轴；tolerance: double>0，文档长度单位；height: double?，平面局部Z；null使用MaximumZ；outputLevel: int>=1；directory: 受控可写导出目录。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；匹配冻结OperationTools2027 1.0.3、AdvancedDrill2027 AD012依赖；已保存文件。；选择保护/补面桥接须匹配docs/COMPATIBILITY.md中的SDK/MCCORE/MCGeomSld/PSKERNEL哈希。

**流程**：1. BoundaryHost.Analyze导出STL并计算ProjectionResult；检查环数、孔环、Z范围与容差。 2. 明确高度/层后Create或CreateCurves。 3. typed层立即保存CurveIds并用SessionChanges.GeometryUndo生成归属清理句柄；UI已注册会话栈。

**输出**：ProjectionResult(Loops、MinimumZ/MaximumZ、Tolerance、MeshTriangles)；BoundaryOutput及逐环CurveIds。

**副作用**：Analyze也写projection-*.stl并临时改几何选择后恢复。；Create生成原生线段，外环色10/内环12；不生成工序。

**回滚/失败**：创建中失败清理自有线；成功后GeometryUndo返回Action，调用前核时间戳/属性/引用；源或结果改变应拒绝。

**限制**：CreateCurves对调用方传入DTO依赖较强；typed候选应把Analyze结果留在会话，禁止任意伪造ProjectionResult。；不跨进程序列化Chain/MCView或Action。

**公开签名**：

```csharp
PorscheAdvanced2027.BoundaryHost :: public static PlaneFrame FrameOf(MCView view)
PorscheAdvanced2027.BoundaryHost :: public static ProjectionResult Analyze(int[] solidIds,PlaneFrame frame,double tolerance,string outputDirectory)
PorscheAdvanced2027.BoundaryHost :: public static BoundaryOutput Create(int[] solidIds,PlaneFrame frame,double tolerance,double? height,int outputLevel,string directory)
PorscheAdvanced2027.BoundaryHost :: public static BoundaryOutput CreateCurves(ProjectionResult result,PlaneFrame frame,double height,int outputLevel)
PorscheAdvanced2027.SessionChanges :: public static Action GeometryUndo(int[] ids)
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/BoundaryHost.cs#L32`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Window.cs#L27`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

### porsche.boundary_sequence · 实体边界→粗/精/倒角三工序

**typed_candidate** · 需要从实体直接完成投影与轮廓工序编排。

**输入与单位**：sourceIds: int[]；plane: MCView，通过稳定ViewID在宿主解析；seedId: 当前机床组未锁定、平底刀Basic contour；c: BoundarySettings{Tolerance,OutputLevel,IncludeInnerLoops,RoughDiameter,FinishDiameter,ChamferDiameter,WallStock,FloorStock,RadialPasses(short),RadialSpacing,StepDown,ChamferWidth,ChamferTipOffset,Feed,Plunge,Rpm(int),ClearanceAbove,RetractAbove,FeedAbove,UseModelBottom,Bottom,ToolLength,FluteLength,FeedModeReviewed,Regenerate}；长度用文档单位，安全高度为模型顶面以上量；Feed/Plunge为宿主模式数值；directory: 受控审计目录。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；匹配冻结OperationTools2027 1.0.3、AdvancedDrill2027 AD012依赖；已保存文件。；选择保护/补面桥接须匹配docs/COMPATIBILITY.md中的SDK/MCCORE/MCGeomSld/PSKERNEL哈希。

**流程**：1. 分析投影并核内环是否参与。 2. 核刀具、层深、底面来源、安全高度、进给模式，调用BoundarySequence.Apply。 3. 读取Output与Created.Operations、Readbacks；默认执行原生再生。

**输出**：BoundaryRun、投影曲线、3道真实Contour工序、可选新刀与审计。

**副作用**：新增边界/工序/缺失刀具；Regenerate=true时计算刀路；保留源实体/参考。

**回滚/失败**：BoundaryRun.Rollback先核输出曲线，调用Created.Rollback移除自建工序/刀具，再删本批曲线；不接受外部编辑。

**限制**：不是任意实体三维清料；外轮廓与内环的刀侧需用户复核。；原生边界/序列fixture验收通过，不代表任意零件全部策略通过。

**公开签名**：

```csharp
PorscheAdvanced2027.BoundarySequence :: public static BoundaryRun Apply(int[] sourceIds,MCView plane,int seedId,BoundarySettings c,string directory)
PorscheAdvanced2027.BoundaryRun :: public void Rollback()
PorscheAdvanced2027.Main :: public MCamReturn Boundary(int p)
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/BoundarySequence.cs#L101`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Main.cs#L18`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

### porsche.holes · 孔特征识别→中心钻/钻孔/沉孔/沉头

**typed_candidate** · 从实体完整孔段、轴线和入口自动组织可达轴向加工。

**输入与单位**：solidIds: int[]；alignment: V3，孔轴优先方向；settings: HoleSettings{MinimumDiameter,MaximumDiameter,CenterDiameter,CenterDepth,ThroughExtraDepth,DrillTipAngle(度),Feed,Plunge,RetractFeed,Rpm,Clearance,Retract,FeedPlane,ToolLength,FluteLength,ShoulderLength,CreateMissingTools,FeedModeReviewed,Regenerate}；长度文档单位；三高度相对孔口；进给宿主模式；referenceId: 同活动机床组的参考工序，提供组/WCS；directory: 受控审计目录。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；匹配冻结OperationTools2027 1.0.3、AdvancedDrill2027 AD012依赖；已保存文件。；选择保护/补面桥接须匹配docs/COMPATIBILITY.md中的SDK/MCCORE/MCGeomSld/PSKERNEL哈希。

**流程**：1. Recognize返回RecognizedPlan[]，审阅每孔轴、入口、阶段、深度与Evidence。 2. 核对源时间戳、刀具长度与进给；Apply。 3. 读回新工具/孔轴平面/工序；默认逐工序再生并核fresh状态和有效行程。

**输出**：HoleRun的Operations/Tools/Planes/Readbacks/Status/AuditPath。

**副作用**：匹配或按明确许可建刀；复用或新建孔轴平面；临时参考工序在创建完成后删除；生成并可重算DrillOperation。；恢复原工序/几何选择，保留源实体。

**回滚/失败**：HoleRun.Rollback按最终状态核工序/刀具/平面并逆序清理；失败路径尝试清理，受外部引用的对象不能盲删。

**限制**：支持已识别的Cylinder、正向锥形、平底/点底等组合；拒绝内扩大/倒扣、未知过渡或轴线不符。；不从孔径推断螺纹；此流程不自动生成Tap阶段。；通孔ThroughExtraDepth显式；闭钻尖锥保留证据，不自动追加钻尖长度。

**公开签名**：

```csharp
PorscheAdvanced2027.HoleHost :: public static RecognizedPlan[] Recognize(int[] solidIds,V3 alignment,HoleSettings settings)
PorscheAdvanced2027.HoleHost :: public static HoleRun Apply(RecognizedPlan[] plans,HoleSettings settings,int referenceId,string directory)
PorscheAdvanced2027.HolePlanning :: public static RecognizedPlan Plan(int sourceId,DateTime stamp,HoleFact h,HoleSettings c)
PorscheAdvanced2027.HoleRun :: public void Rollback()
PorscheAdvanced2027.Main :: public MCamReturn Holes(int p)
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/HoleHost.cs#L62`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/HolePlanning.cs#L59`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Main.cs#L20`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

### porsche.heal · 按完整孔在独立实体副本上删孔补面

**interactive** · 需要保留源实体并得到无指定孔特征的副本。

**输入与单位**：sourceId: int SolidGeometry；UI可多选后逐一执行；minimumRadius: double>=0；maximumRadius: double>minimumRadius；C#接口为半径，UI MinimumDiameter/MaximumDiameter会除2。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；匹配冻结OperationTools2027 1.0.3、AdvancedDrill2027 AD012依赖；已保存文件。；选择保护/补面桥接须匹配docs/COMPATIBILITY.md中的SDK/MCCORE/MCGeomSld/PSKERNEL哈希。

**流程**：1. 先在Healing页识别孔范围；检查主圆柱孔径。 2. 执行CreateHealedFaceCopy；验证副本独立面标签、原生状态、面数减少、源时间戳/面集未变、目标孔消失。 3. 保存HealingResult，注册GeometryUndo副本句柄。

**输出**：HealingResult(SourceId,OutputId,NativeResult,NativeHoleCount,FacesBefore,FacesAfter)。

**副作用**：新增同位置/图层实体副本，扁平化其历史并删除整组孔面/原生延伸补面；源保持。

**回滚/失败**：失败尝试删除本次副本；成功后会话GeometryUndo按源外的输出ID守卫清理；回滚不会还原一个被直接修改的源。

**限制**：当前优先交互使用；桥接调用固定已验构建，不推荐首批公开typed MCP。；没有完整孔或剩余目标孔时失败，不承诺任意单圆柱面/复杂相交孔可补。

**公开签名**：

```csharp
PorscheAdvanced2027.HoleHealing :: public static HealingResult CreateHealedFaceCopy(int sourceId,double minimumRadius,double maximumRadius)
PorscheAdvanced2027.Main :: public MCamReturn Healing(int p)
PorscheAdvanced2027.SessionChanges :: public static Action GeometryUndo(int[] ids)
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/HoleHealing.cs#L113`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Main.cs#L19`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Window.cs#L27`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

### porsche.session · 面板导航与回滚最近生成

**interactive** · 使用三标签页或撤回最近输出。

**输入与单位**：tab: Show/Boundary=0，Healing=1，Holes=2；selection: 面板左侧勾选可见实体；可读取当前选择/全部可见；并明确平面和参考工序。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；匹配冻结OperationTools2027 1.0.3、AdvancedDrill2027 AD012依赖；已保存文件。；选择保护/补面桥接须匹配docs/COMPATIBILITY.md中的SDK/MCCORE/MCGeomSld/PSKERNEL哈希。

**流程**：1. 打开对应FT；先预览，再生成。 2. 点回滚最近一次生成，调用SessionChanges.Rollback。

**输出**：本会话生成栈Last与操作结果。

**副作用**：打开/预览可写STL/日志；生成与回滚效果见对应流程。

**回滚/失败**：SessionChanges.Rollback仅同文档/同会话，调用成功后才出栈；重开不保留。

**限制**：typed层不得暴露任意Action参数的SessionChanges.Add；仅由固定工作流内部登记。

**公开签名**：

```csharp
PorscheAdvanced2027.Main :: public MCamReturn Show(int p)
PorscheAdvanced2027.SessionChanges :: public static void Add(string name,Action undo)
PorscheAdvanced2027.SessionChanges :: public static void Rollback()
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Main.cs#L17`；`author:MC2027-PluginSuite/PorscheAdvanced2027/src/Window.cs#L25`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

### porsche.legacy_heal · 历史直接删孔辅助API（不开放自动化）

**not_exposed** · 供开发者识别遗留公开方法，避免误用于源实体。

**输入与单位**：solidId: int；minRadius: double；maxRadius: double。

**前提**：仅查阅源代码；不作为分发MCP业务操作。

**流程**：1. 实际产品Healing按钮只调用CreateHealedFaceCopy。

**输出**：API范围识别。

**副作用**：ApplyOwned会直接修改所给实体；CreateHealedCopy走另一路原生检测/补面。

**回滚/失败**：ApplyOwned没有可依赖的源恢复句柄；不得作为用户实体默认流程。

**限制**：public可见性不等于推荐业务合同；历史接口不继承当前面复制验收。

**公开签名**：

```csharp
PorscheAdvanced2027.HoleHealing :: public static HealingResult ApplyOwned(int solidId,double minRadius,double maxRadius)
PorscheAdvanced2027.HoleHealing :: public static HealingResult CreateHealedCopy(int sourceId,double minimumRadius,double maximumRadius)
```

**证据**：`author:MC2027-PluginSuite/PorscheAdvanced2027/src/HoleHealing.cs#L82`；`repo:validation/business-acceptance.json`；`repo:docs/COMPATIBILITY.md`。逐源SHA-256在JSON中。

## AdvancedDrill2027

AD012/0.1.2：中心钻→钻孔→沉孔/轴向倒角；显式局部坐标与排序、严格fresh回读及归属回滚。

- 一个孔集合对应明确平面与点列表，每阶段创建一项DrillOperation；不是从点径自动识别螺纹。
- SelectionOrder46表示预览列表顺序，不承诺鼠标点击历史或已验证NCI访问顺序。
- world=Origin+X*local.X+Y*local.Y+Z*local.Z；基向量必须右手正交；不把ViewNumber当稳定ViewID。
- 产品只创建Posting=false、Dirty=true工序；native harness另行重算验证，不是产品自动重算API。
- 根src/dist 0.1.1与AD012不同；不能沿用Off=0排序或历史pending状态。

### ad012.prepare_create · 计划并创建分阶段钻孔链

**typed_candidate** · 需要稳定平面/已有刀具/明确点表的阶段编排。

**输入与单位**：request.Metric: bool；与当前文档一致；Tap必须true；request.Sets: HoleSet[1..100]，名称唯一；request.HoleSet.Name: string；request.HoleSet.Plane: PlaneChoice{ReferenceOperationId:int,ToolPlaneId:int,WcsId:int,ConstructionPlaneId:int,ExpectedToolFrame:Frame}；用DescribePlane取得并保持快照；request.HoleSet.LocalPoints: Vec[1..10000]，X/Y/Z为刀具平面局部坐标；全部Z=Top；拒绝重复，不隐式去重；request.HoleSet.Top: required double；局部绝对顶面；request.HoleSet.Stages: Stage[2..20]；首Center次Drill，再可选深化Drill/Counterbore/Chamfer；Tap创建拒绝；request.Stage.Name: string，组内唯一；request.Stage.Purpose: Center|Drill|Counterbore|Chamfer|Tap；request.Stage.Cycle: Drill|PeckDrill|ChipBreak|Tap；request.Stage.Sorting: SelectionOrder=46(默认)|XPlusYPlus=1|ZBidirectionalPlusCounterclockwise=45；JSON用名称，不接受0/任意数值；request.Stage.Tool: ToolChoice{Slot:int,Kind:ToolClass,Diameter:double,LengthOffset:int,DiameterOffset:int}，现有同组真实类型刀具；request.Stage.Cutting: Cutting{Feed:double,Plunge:double,Retract:double,Rpm:int,NativeFeedModeReviewed:bool}；三个进给为显式宿主原始数值，不设置模式；request.Stage.Depth: required double；刀具平面局部绝对值，低于Top；不自动钻尖补偿；request.Stage.Clearance: required double；request.Stage.Retract: required double；request.Stage.FeedPlane: required double；Clearance>=Retract>=FeedPlane>Top>Depth；request.Stage.Peck1: double，啄/断屑循环时>0，非使用时0；request.Stage.Peck2: double，同上；request.Stage.PeckClearance: double>=0；request.Stage.ChipBreak: double，ChipBreak循环时>0，其余0；request.Stage.Dwell: double>=0；原生Dwell数值；request.Stage.ThreadPitch: 仅描述，非Tap须0，不能据字段存在创建Tap；auditDirectory: 受控可写目录；不能接受任意远程调用者文件路径。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档、无其他事务；参考未锁定、活动机床组一致；刀槽、类型、H/D、单位、直径/刃长逐项核对。

**流程**：1. DescribePlane生成PlaneChoice；填完整Request；Rules.Plan纯逻辑预览局部/世界点和阶段。 2. Host.Prepare或PrepareJson生成一次性Batch；确认后Apply。 3. 读取CreatedIds、Status、Error、SelectionRestored、AuditJson；每阶段和整批都fresh比对。

**输出**：PlannedStage[]、Batch；真实阶段工序与逐字段审计。

**副作用**：仅新建DrillOperation；不新建工具/平面；不再生、不post/NC、不保存。；写审计，恢复原选择；失败按归属清理已提交对象。

**回滚/失败**：保留Batch对象；Apply失败可能RestoredAfterFailure/RestoreIncomplete。成功后Batch.Rollback；外部编辑/重算可使产品快照失效。

**限制**：AD012九条链/36次再生与fresh范围均已有native验收；不证明NCI逐孔顺序。；PrepareJson反序列化拒绝未知字段/数值枚举；typed协议应提供强类型输入而非任意C#脚本。

**公开签名**：

```csharp
AdvancedDrill2027.Host :: public static PlaneChoice DescribePlane(int referenceId)
AdvancedDrill2027.Host :: public static Batch Prepare(Request request,string auditDirectory)
AdvancedDrill2027.Host :: public static Batch PrepareJson(string json,string auditDirectory)
AdvancedDrill2027.Rules :: public static PlannedStage[] Plan(Request original)
AdvancedDrill2027.Rules :: public static void RequireExecutable(IEnumerable<PlannedStage> plan)
AdvancedDrill2027.Batch :: public void Apply()
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Host.cs#L22`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Core.cs#L132`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Core.cs`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/AD012-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad012.recovery · 批次回滚与限定重试

**typed_candidate** · 成功批次需撤销，或失败后清理/选择恢复未完成。

**输入与单位**：batch: 原会话Batch；不能从AuditJson重造句柄。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Applied或AppliedSelectionRestoreIncomplete才Rollback。 2. RestoreIncomplete才RetryCleanup；无选择恢复检查点时不得RetrySelection。 3. 再次核CreatedIds已删除/SelectionRestored及最终审计。

**输出**：RolledBack、CleanedAfterRetry或明确未恢复状态。

**副作用**：删除自有阶段工序、恢复本次选择；不删除原刀具/几何/平面。

**回滚/失败**：所有删除前执行归属、参数、时间戳守卫；错误保持可见，不放宽检查重复Apply。

**限制**：harness对自身受控Regenerate另立检查点；不能把它当成产品允许任意重算后回滚。

**公开签名**：

```csharp
AdvancedDrill2027.Batch :: public void Rollback()
AdvancedDrill2027.Batch :: public void RetryCleanup()
AdvancedDrill2027.Batch :: public void RetrySelection()
AdvancedDrill2027.Host :: public static Operation Read(int id)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Core.cs#L239`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Host.cs#L21`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/AD012-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad012.ui · 中文阶段表单、点来源与预览

**interactive** · 无需手写JSON，逐阶段选择现有刀具和明确参数。

**输入与单位**：p: int FT宿主参数；source: 当前选择的点/完整圆或手工局部点；参考工序/平面下拉；stages: 启用阶段，循环/排序/刀具/深度/安全高度/切削数值。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Show打开模态UI；选参考、刷新刀具、捕获点或输入局部坐标。 2. 先预览点表与阶段，再创建；需撤回时用窗口回滚。

**输出**：预览与批次审计。

**副作用**：打开/取消不创建；创建同上。

**回滚/失败**：取消表单或显式Batch回滚；保留后续编辑保护。

**限制**：FT共享Workshop资源；宿主测试证据等级须分清native业务与UI打开。

**公开签名**：

```csharp
AdvancedDrill2027.Main :: public MCamReturn Show(int p)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Main.cs#L13`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/AD012-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad012.store_internal · 阶段存储低层接口（不直接暴露）

**not_exposed** · 标记公开CreateStore的开发用途。

**输入与单位**：request: Request。

**前提**：仅供封装实现内部组合。

**流程**：1. 使用Host.Prepare统一预检、持久化、回读、清理；不把Allocate/DeleteOwned等低层阶段动作注册为任意工具。

**输出**：IStageStore实现细节。

**副作用**：绕过Batch会失去业务生命周期保护。

**回滚/失败**：只能在受控Batch内管理。

**限制**：public签名存在不等于适合独立MCP端点。

**公开签名**：

```csharp
AdvancedDrill2027.Host :: public static IStageStore CreateStore(Request request)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/src/Host.cs#L36`；`author:MC2027-PluginSuite/AdvancedDrill2027/candidates/AD012/AD012-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

## AdvancedDrillTap2027

AD013/0.1.3：与AD012并存的独立程序集，新增显式公制右旋G84阶段。

- 一个孔集合对应明确平面与点列表，每阶段创建一项DrillOperation；不是从点径自动识别螺纹。
- SelectionOrder46表示预览列表顺序，不承诺鼠标点击历史或已验证NCI访问顺序。
- world=Origin+X*local.X+Y*local.Y+Z*local.Z；基向量必须右手正交；不把ViewNumber当稳定ViewID。
- 产品只创建Posting=false、Dirty=true工序；native harness另行重算验证，不是产品自动重算API。
- 右旋TapRHTool、公制正螺距；进给原始数值必须用户确认；不自动乘RPM×pitch，也无刚性同步设置。

### ad013.prepare_create · 计划并创建中心钻→预钻→公制右旋G84

**typed_candidate** · 需要稳定平面/已有刀具/明确点表的阶段编排。

**输入与单位**：request.Metric: bool；与当前文档一致；Tap必须true；request.Sets: HoleSet[1..100]，名称唯一；request.HoleSet.Name: string；request.HoleSet.Plane: PlaneChoice{ReferenceOperationId:int,ToolPlaneId:int,WcsId:int,ConstructionPlaneId:int,ExpectedToolFrame:Frame}；用DescribePlane取得并保持快照；request.HoleSet.LocalPoints: Vec[1..10000]，X/Y/Z为刀具平面局部坐标；全部Z=Top；拒绝重复，不隐式去重；request.HoleSet.Top: required double；局部绝对顶面；request.HoleSet.Stages: Stage[2..20]；首Center次Drill，再可选深化Drill/Counterbore/Chamfer/最后Tap；request.Stage.Name: string，组内唯一；request.Stage.Purpose: Center|Drill|Counterbore|Chamfer|Tap；request.Stage.Cycle: Drill|PeckDrill|ChipBreak|Tap；request.Stage.Sorting: SelectionOrder=46(默认)|XPlusYPlus=1|ZBidirectionalPlusCounterclockwise=45；JSON用名称，不接受0/任意数值；request.Stage.Tool: ToolChoice{Slot:int,Kind:ToolClass,Diameter:double,LengthOffset:int,DiameterOffset:int}，现有同组真实类型刀具；request.Stage.Cutting: Cutting{Feed:double,Plunge:double,Retract:double,Rpm:int,NativeFeedModeReviewed:bool}；三个进给为显式宿主原始数值，不设置模式；request.Stage.Depth: required double；刀具平面局部绝对值，低于Top；不自动钻尖补偿；request.Stage.Clearance: required double；request.Stage.Retract: required double；request.Stage.FeedPlane: required double；Clearance>=Retract>=FeedPlane>Top>Depth；request.Stage.Peck1: double，啄/断屑循环时>0，非使用时0；request.Stage.Peck2: double，同上；request.Stage.PeckClearance: double>=0；request.Stage.ChipBreak: double，ChipBreak循环时>0，其余0；request.Stage.Dwell: double>=0；原生Dwell数值；request.Stage.ThreadPitch: double>0，Tap为公制mm螺距；其余0；request.Stage.TapTarget: TapTarget{MachineGroupId:int,MachineName:string,PostName:string,ExplicitFeedReviewed:bool=true}；CurrentTapTarget只读取身份，确认字段须显式设置；auditDirectory: 受控可写目录；不能接受任意远程调用者文件路径。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；已保存文档、无其他事务；参考未锁定、活动机床组一致；刀槽、类型、H/D、单位、直径/刃长逐项核对。；Tap最后，深度不得超过显式预钻深度；RH丝锥为顺时针，Threads与mm螺距一致。；Tap Feed=Plunge=Retract>0；Peck/ChipBreak/Dwell=0；创建前重新核目标机床/后处理。

**流程**：1. DescribePlane生成PlaneChoice；填完整Request；Rules.Plan纯逻辑预览局部/世界点和阶段。 2. CurrentTapTarget读取真实目标，用户确认后置ExplicitFeedReviewed=true。 3. Host.Prepare或PrepareJson生成一次性Batch；确认后Apply。 4. 读取CreatedIds、Status、Error、SelectionRestored、AuditJson；每阶段和整批都fresh比对。

**输出**：PlannedStage[]、Batch；真实阶段工序与逐字段审计。

**副作用**：仅新建DrillOperation；不新建工具/平面；不再生、不post/NC、不保存。；写审计，恢复原选择；失败按归属清理已提交对象。

**回滚/失败**：保留Batch对象；Apply失败可能RestoredAfterFailure/RestoreIncomplete。成功后Batch.Rollback；外部编辑/重算可使产品快照失效。

**限制**：仅Top G84固定目标的创建/一次再生范围已验收；倾斜G84、模式控制、刚性同步、NC和碰撞未由此证明。；PrepareJson反序列化拒绝未知字段/数值枚举；typed协议应提供强类型输入而非任意C#脚本。

**公开签名**：

```csharp
AdvancedDrillTap2027.Host :: public static PlaneChoice DescribePlane(int referenceId)
AdvancedDrillTap2027.Host :: public static Batch Prepare(Request request,string auditDirectory)
AdvancedDrillTap2027.Host :: public static Batch PrepareJson(string json,string auditDirectory)
AdvancedDrillTap2027.Rules :: public static PlannedStage[] Plan(Request original)
AdvancedDrillTap2027.Rules :: public static void RequireExecutable(IEnumerable<PlannedStage> plan)
AdvancedDrillTap2027.Batch :: public void Apply()
AdvancedDrillTap2027.Host :: public static TapTarget CurrentTapTarget()
AdvancedDrillTap2027.Rules :: public static void ValidateTap(Stage s)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Host.cs#L23`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Core.cs#L141`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Core.cs`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/AD013-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad013.recovery · 批次回滚与限定重试

**typed_candidate** · 成功批次需撤销，或失败后清理/选择恢复未完成。

**输入与单位**：batch: 原会话Batch；不能从AuditJson重造句柄。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Applied或AppliedSelectionRestoreIncomplete才Rollback。 2. RestoreIncomplete才RetryCleanup；无选择恢复检查点时不得RetrySelection。 3. 再次核CreatedIds已删除/SelectionRestored及最终审计。

**输出**：RolledBack、CleanedAfterRetry或明确未恢复状态。

**副作用**：删除自有阶段工序、恢复本次选择；不删除原刀具/几何/平面。

**回滚/失败**：所有删除前执行归属、参数、时间戳守卫；错误保持可见，不放宽检查重复Apply。

**限制**：harness对自身受控Regenerate另立检查点；不能把它当成产品允许任意重算后回滚。

**公开签名**：

```csharp
AdvancedDrillTap2027.Batch :: public void Rollback()
AdvancedDrillTap2027.Batch :: public void RetryCleanup()
AdvancedDrillTap2027.Batch :: public void RetrySelection()
AdvancedDrillTap2027.Host :: public static Operation Read(int id)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Core.cs#L260`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Host.cs#L22`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/AD013-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad013.ui · 中文阶段表单、点来源与预览

**interactive** · 无需手写JSON，逐阶段选择现有刀具和明确参数。

**输入与单位**：p: int FT宿主参数；source: 当前选择的点/完整圆或手工局部点；参考工序/平面下拉；stages: 启用阶段，循环/排序/刀具/深度/安全高度/切削数值。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Show打开模态UI；选参考、刷新刀具、捕获点或输入局部坐标。 2. 先预览点表与阶段，再创建；需撤回时用窗口回滚。

**输出**：预览与批次审计。

**副作用**：打开/取消不创建；创建同上。

**回滚/失败**：取消表单或显式Batch回滚；保留后续编辑保护。

**限制**：FT共享Workshop资源；宿主测试证据等级须分清native业务与UI打开。

**公开签名**：

```csharp
AdvancedDrillTap2027.Main :: public MCamReturn Show(int p)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Main.cs#L13`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/AD013-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

### ad013.store_internal · 阶段存储低层接口（不直接暴露）

**not_exposed** · 标记公开CreateStore的开发用途。

**输入与单位**：request: Request。

**前提**：仅供封装实现内部组合。

**流程**：1. 使用Host.Prepare统一预检、持久化、回读、清理；不把Allocate/DeleteOwned等低层阶段动作注册为任意工具。

**输出**：IStageStore实现细节。

**副作用**：绕过Batch会失去业务生命周期保护。

**回滚/失败**：只能在受控Batch内管理。

**限制**：public签名存在不等于适合独立MCP端点。

**公开签名**：

```csharp
AdvancedDrillTap2027.Host :: public static IStageStore CreateStore(Request request)
```

**证据**：`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/src/Host.cs#L37`；`author:MC2027-PluginSuite/AdvancedDrill2027/tap-contract/candidates/AD013/AD013-NATIVE-ACCEPTANCE.md`。逐源SHA-256在JSON中。

## SolidBoundary2027

1.0.5/ExistingOutput105：验证凸多面直边实体拓扑证书后，生成WorldXY单外环边界；只写入已有可见层。

- 先证明闭合凸多面体与直线边，再求投影凸包；不是把任意凹体近似为凸包。
- Preview进行真实宿主提边但回滚临时事务；Create另行重新核验并提交结果线。
- 成功创建没有公开持久回滚对象/按钮；失败清理与成功后显式撤销不能混为一谈。

### solid_boundary.preview_create · 凸多面体边界预览→创建

**typed_candidate** · 一个已选凸多面实体需要WorldXY单外边界。

**输入与单位**：request.SourceId: int，当前选择集合必须恰好是这个非blanked实体；request.Origin: V3(X,Y,Z)，世界坐标显式原点；request.Depth: double，带符号；输出世界Z=Origin.Z+Depth；request.Tolerance: double，1e-9..0.01，文档单位；无公英转换；request.OutputLevel: int 1..999999，Create要求已存在且可见；request.Clockwise: bool；从世界+Z看向XY定义CW/CCW。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；无其他Undo事务；CPlane方向为WorldXY；单选源实体。；源必须闭合、凸、全平面面、直且未拆分的边；无孔/内腔/共面面拆分/多体。；输出层取GetExistingVisibleOutputLevels，创建前与提边后均会再核。

**流程**：1. Preview返回纯BoundaryResult与审计，核面积、周长、体积、方向、世界Z。 2. 确认后Create重新验证源/选择/上下文/层准入，提交单闭合链。 3. 保留GeometryIds和Chains；fresh读回成员、坐标、面积/长度、深度、方向。

**输出**：BoundaryReceipt(Boundary,GeometryIds,Chains,Committed,Contract)；LastAudit。

**副作用**：Preview不保留输出几何；Create新增原生线；不创建工序/刀具/平面、不保存。；原选择/源几何/上下文严格核对；禁止新建或显示隐藏输出层。

**回滚/失败**：失败路径取消事务并按精确本次ID/线端点/属性清理。成功没有公开Rollback；用户可在宿主审阅后撤销，新MCP需另行实现带归属快照的回滚才可承诺事务闭环。

**限制**：不支持曲面/凹体/孔/多体/倾斜CPlane/极薄不确定几何。；新层恢复引擎问题未解决；不要用旧根dist 1.0.4替代。；native fixture已通过既有空/非空可见层与故障清理；不能扩展到任意实体或具名层/真实注册组所有场景。

**公开签名**：

```csharp
SolidBoundary2027.NativeBoundary :: public static BoundaryReceipt Preview(BoundaryRequest request)
SolidBoundary2027.NativeBoundary :: public static BoundaryReceipt Create(BoundaryRequest request)
SolidBoundary2027.NativeBoundary :: public static int[] GetExistingVisibleOutputLevels()
```

**证据**：`author:MC2027-PluginSuite/SolidBoundary2027/candidates/ExistingOutput105/src/NativeBoundary.cs#L24`；`author:MC2027-PluginSuite/SolidBoundary2027/qualifications/1.0.5-installed-native-20261028/README.md`。逐源SHA-256在JSON中。

### solid_boundary.ui · 已有可见层边界表单

**interactive** · 交互选择原点/深度/公差/方向并预览。

**输入与单位**：parameter: int宿主参数；selection: 恰一个支持的实体。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Show，刷新已有可见输出层，输入参数。 2. 计算预览，再创建已预览边界；读取Main.LastResultJson。

**输出**：模态预览、多边形图、结果ID/JSON。

**副作用**：创建前不保留新线；成功后线留文档。

**回滚/失败**：取消只取消未提交操作；成功没有面板回滚按钮。

**限制**：源码中native qualification pending提示是冻结时历史文字；后来native验收补充说明优先，UI验收等级另看父记录。

**公开签名**：

```csharp
SolidBoundary2027.Main :: public MCamReturn Show(int parameter)
```

**证据**：`author:MC2027-PluginSuite/SolidBoundary2027/candidates/ExistingOutput105/src/Entry.cs#L23`；`author:MC2027-PluginSuite/SolidBoundary2027/qualifications/1.0.5-installed-native-20261028/README.md`。逐源SHA-256在JSON中。

### solid_boundary.fixture · 内嵌诊断/fixture入口（不暴露）

**not_exposed** · 防止把公开测试入口误当生产业务。

**输入与单位**：parameter: int。

**前提**：不得在用户零件运行。

**流程**：1. 仅记录：Main.FixtureHarness是显式测试入口，生产FT不注册它。

**输出**：开发fixture报告。

**副作用**：可创建测试实体/哨兵并注入失败。

**回滚/失败**：fixture依赖自己严格清理，不属于业务撤销。

**限制**：不得注册为通用MCP命令或启动自动执行。；NativeEdgeProbe/NativeLevelProbe为历史显式诊断，包含源/新层探测，生产Preview/Create不调用；不封装为业务工具。

**公开签名**：

```csharp
SolidBoundary2027.Main :: public MCamReturn FixtureHarness(int parameter)
SolidBoundary2027.NativeEdgeProbe :: public static string RunSelectedSource(int sourceId,double tolerance=0.0001)
SolidBoundary2027.NativeLevelProbe :: public static LevelProbeResult RunNewOutputLevel(int target,bool allowMutation)
```

**证据**：`author:MC2027-PluginSuite/SolidBoundary2027/candidates/ExistingOutput105/src/Entry.cs#L29`；`author:MC2027-PluginSuite/SolidBoundary2027/qualifications/1.0.5-installed-native-20261028/README.md`；`author:MC2027-PluginSuite/SolidBoundary2027/candidates/ExistingOutput105/src/NativeEdgeProbe.cs#L24`；`author:MC2027-PluginSuite/SolidBoundary2027/candidates/ExistingOutput105/src/NativeLevelProbe.cs#L13`。逐源SHA-256在JSON中。

## LittleBee2027

2.0.0：小蜜蜂工序编辑/命名/复制保存，坐标图层、刀单、材料、机床配置与工序交换/显式后处理。

- Main的异常包装显示错误后仍可能返回MCamReturn.NoErrors；FT布尔返回不是业务成功证明。
- 默认数据目录为%LOCALAPPDATA%/LittleBee2027/Rebuilt；界面保存配置、模板与日志可能写磁盘。
- Main.ChangeView切换未来WCS跟随；Commands.ChangeView是立即选择工序并切换坐标的另一方法。
- 材料尺寸/密度/单价是用户资料或注明来源的测量；不是自动刀具进给推荐。
- 只有少数Materials纯逻辑/导入函数是公开typed候选；大量业务实现为private/internal UI流程。

### bee.hub · 小蜜蜂功能集锦

**interactive** · 选择坐标层别、刀单、材料、机床、执行、导入导出或命名。

**输入与单位**：parameter: int，FT宿主参数。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. LittleBee或Hub.Show打开功能集锦。 2. 选择功能；打开配置目录只显示本机文件夹。

**输出**：功能窗口。

**副作用**：打开目录可能启动资源管理器；具体写入由子流程决定。

**回滚/失败**：关闭面板。

**限制**：不要把总面板开放当作各业务已完成。

**公开签名**：

```csharp
LittleBee.Rebuilt.Main :: public MCamReturn LittleBee(int parameter)
LittleBee.Rebuilt.Hub :: public static void Show()
```

**证据**：`author:LittleBee2027-independent/src/Main.cs#L41`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.edit · 编辑工序、刀具、几何与共同参数

**interactive** · 需要Mastercam原生专用参数窗口。

**输入与单位**：selection: 至少一项工序；单项编辑多选时再选一项；parameter: int。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 打开EditOperation/EditTool/EditOperationGeometry，或EditCommonParameters批量共同参数。 2. 在原生窗口确认/取消；返回后核实际工序/刀具。

**输出**：原生编辑窗口及用户确认的参数修改。

**副作用**：原生对话框确认会提交；工具可能被多个工序引用；选择由保护流程恢复。

**回滚/失败**：未确认时原生取消；确认后无此模块公开批次Rollback，需原生编辑/撤销与回读。

**限制**：已有证据为四窗口打开/取消；不等于所有专用字段完整修改验收。

**公开签名**：

```csharp
LittleBee.Rebuilt.Commands :: public static void EditOperation()
LittleBee.Rebuilt.Commands :: public static void EditOperationGeometry()
LittleBee.Rebuilt.Commands :: public static void EditTool()
LittleBee.Rebuilt.Commands :: public static void EditCommonParameters()
LittleBee.Rebuilt.Main :: public MCamReturn EditOperation(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn EditTool(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn EditOperationGeometry(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn EditCommonParameters(int parameter)
```

**证据**：`author:LittleBee2027-independent/src/Commands.cs#L311`；`author:LittleBee2027-independent/src/Main.cs#L47`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.copy_paste · 复制工序并粘贴到明确位置

**interactive** · 复用当前宿主剪贴板中的工序。

**输入与单位**：selection: Copy至少一项；Paste最多一个目标工序，或无选中工序并激活刀路组。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. CopyOperation调用原生OMOnCopy。 2. 明确插入位置后PasteOperation调用OMOnPaste；核新增ID而非只看返回值。

**输出**：新增工序ID或无新增提示。

**副作用**：读写宿主剪贴板；Paste新增工序；恢复原选择。

**回滚/失败**：无公开归属回滚；用户核新增ID后通过原生管理器撤销/删除，不能清空全部新工序。

**限制**：已有样例仅核一个拷贝的19参数/20刀具字段；完整链、轨迹、持久性未由此证明。

**公开签名**：

```csharp
LittleBee.Rebuilt.Commands :: public static void CopyOperation()
LittleBee.Rebuilt.Commands :: public static void PasteOperation()
LittleBee.Rebuilt.Main :: public MCamReturn CopyOperation(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn PasteOperation(int parameter)
```

**证据**：`author:LittleBee2027-independent/src/Commands.cs#L338`；`author:LittleBee2027-independent/src/Main.cs#L51`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.rename · 群组与NCI程序名称预览重命名

**interactive** · 整理刀路树与程序分组命名。

**输入与单位**：scope: 打开时选择，可显式扩大到全文件勾选；prefix: 自定义/当前文件名；separator: string；start: int>=0；step: int非0；grouping: 每加工工序|连续同刀|刀路组编号|与刀路组同名。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. ReNameGroup或ChangeNci打开预览；核每行旧名→新名。 2. 应用预览；原工序选择恢复后检查结果。

**输出**：群组名/NCI名；设置与错误记录。

**副作用**：改组名/NCI名称及相关NCI路径，不重算或post；需保存文档才持久。

**回滚/失败**：提交失败尝试恢复原组名或NCI名称/路径；成功无公开Undo句柄。

**限制**：NCI名称不是NC输出；禁路径字符、设备名、.nci后缀。手动条目随邻近切削工序，不独占编号。

**公开签名**：

```csharp
LittleBee.Rebuilt.Commands :: public static void ReNameGroup()
LittleBee.Rebuilt.Commands :: public static void ChangeNci()
LittleBee.Rebuilt.Main :: public MCamReturn ChangeNci(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn ReNameGroup(int parameter)
```

**证据**：`author:LittleBee2027-independent/src/Commands.cs#L364`；`author:LittleBee2027-independent/src/Main.cs#L42`；`author:LittleBee2027-independent/src/RenameDialogs.cs`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.follow_view · WCS跟随开关与立即切换坐标

**interactive** · 查看选中工序的设置方向，或启用后续选中事件跟随。

**输入与单位**：mode: Main.ChangeView/ToggleFollow切换保存的Enabled；Commands.ChangeView立即从所选工序选WCS；FollowGraphicsView: 配置默认false，仅跟随设置开启时显式切图形视图。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 区分切换开关与立即切换；ToggleFollow不即时改变平面。 2. Enabled时未来OperationSelectionsChanged取宿主顺序首个有效WCS；WCS不同才赋值W/C/T。 3. 立即ChangeView选择一工序，设置W/C/T/G并刷新。

**输出**：跟随状态、LastFollowError或坐标变化。

**副作用**：Toggle写wcs-follow.json；通知可能改变当前W/C/T；不改工序选择。

**回滚/失败**：开关可再次关闭；切换异常尝试恢复旧平面；成功后的视图需用户切回，没有会话Rollback。

**限制**：当前WCS已相同则跟随不重设C/T；宿主自己的follow偏好仍有效。FollowNotification由生命周期调用，不供外部伪造事件。

**公开签名**：

```csharp
LittleBee.Rebuilt.Commands :: public static void ToggleFollow()
LittleBee.Rebuilt.Commands :: public static void ChangeView()
LittleBee.Rebuilt.Main :: public MCamReturn ChangeView(int parameter)
```

**证据**：`author:LittleBee2027-independent/src/Commands.cs#L42`；`author:LittleBee2027-independent/src/Main.cs#L46`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.save · 保存/另存为并可附现有毛坯尺寸

**interactive** · 用户明确要求写MCAM文件。

**输入与单位**：destination: SaveAs原生保存框；.mcam完整路径<260字符；stockNaming: 一个机床组且有有效现存StockSize时，可追加_size_大X中X小；已有_size_不重复。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. SaveFile计算建议文件名；无合法路径时转SaveAs。 2. 确认覆盖/另存位置，保存后核非空文件及CurrentFileName回读。

**输出**：MCAM磁盘文件与活动文件名。

**副作用**：真实保存、可改变当前文档路径；不新建机床组/毛坯，不手动清dirty标记。

**回滚/失败**：写文件不属于批次Rollback；覆盖前由用户决定，依赖文件备份恢复。

**限制**：适配器不得在普通查询/规划时隐式调用SaveFile。

**公开签名**：

```csharp
LittleBee.Rebuilt.Commands :: public static void SaveFile()
LittleBee.Rebuilt.Commands :: public static void SaveAs()
LittleBee.Rebuilt.Main :: public MCamReturn SaveFile(int parameter)
LittleBee.Rebuilt.Main :: public MCamReturn SaveAs(int parameter)
```

**证据**：`author:LittleBee2027-independent/src/Commands.cs#L164`；`author:LittleBee2027-independent/src/Main.cs#L44`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.geometry · 坐标展开、旋转、对齐、图层与结果几何

**interactive** · 把指定几何按源坐标框架整理到世界坐标及目标图层。

**输入与单位**：action: 移动|复制|只改层/颜色|创建包围矩形4线|创建命名坐标平面；input: 捕获选择|全图素含隐藏|全部实体含隐藏|可见未隐藏；boundary: 输入|输入实体|捕获选择仅作参考；sourceFrame: World|WCS|CPlane|图形视图；xy: 九点包围框锚或自定义参考点；z: 顶/中/底/参考点Z/保留源Z；rotation: 0|+90|-90|180度，绕世界+Z；target: 世界XYZ，文档单位；attributes: 目标层、层名、颜色0..255、显示层/设主层；plane: 名字<=39，当前图形方向或World，世界原点或参考点，可激活W/C/T。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. GeometryTools.Show，捕获输入并确认包含隐藏对象的范围。 2. 计算/更新预览；先展开源框架，再绕Z旋转并对齐；输入变化必须重新预览。 3. 执行后核输出数量/位置/图层；矩形和MCView含义不同。

**输出**：移动/复制结果、属性变更、4线矩形或命名视图。

**副作用**：可改几何、主层/层名/可见性与W/C/T/G；Plane是视图，不是实体面。

**回滚/失败**：失败取消事务、恢复层/平面，并显式清理本次MCView；成功几何用原生撤销，MCView不随几何撤销删除，需平面管理器处理。

**限制**：业务执行计划类为private，不存在公开参数化Move/Copy方法；不能编造typed签名。；尺寸为包围范围，不是精确实体剪影。

**公开签名**：

```csharp
LittleBee.Rebuilt.GeometryTools :: public static void Show()
```

**证据**：`author:LittleBee2027-independent/src/GeometryTools.cs#L29`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.toolsheet · 程序/刀具报告、工单模板与截图

**interactive** · 需要来源明确的刀路/刀具记录和打印。

**输入与单位**：job: 工单字段；用户填写工件信息；template: 页眉页脚、列显隐/排序/权重、字体、审计附录；snapshots: 用户触发捕获当前图形视图，独立时间戳；output: CSV完整字段/HTML打印/工单与模板JSON。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. ToolSheet.Show读取当前文件。 2. 核字段来源与未读状态，编辑工单/模板，可导入导出模板或设默认；必要时重新读取。 3. 保存工单/快照，导出完整CSV或打印HTML；可删除所选快照。

**输出**：报告、模板、PNG快照及来源/时间记录。

**副作用**：写本地工单/模板/图片/导出文件；浏览/打印可开外部浏览器；不自动重算。

**回滚/失败**：无文档加工修改；磁盘导出和模板更改不由CAM回滚。

**限制**：Capture/BuildCsv/BuildHtml为internal，不可作为现有公开typed API。；刀具工序快照与目录分别保留，不按T号盲合并；截图不自动切换视图。

**公开签名**：

```csharp
LittleBee.Rebuilt.ToolSheet :: public static void Show()
```

**证据**：`author:LittleBee2027-independent/src/ToolSheet.cs#L26`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.materials_calc · 材料毛坯重量/成本计算与清单导入

**typed_candidate** · 已有明确尺寸/单位/密度/价格，需要纯逻辑预算或整理待测文件。

**输入与单位**：stock: Materials.StockItem{Name,MaterialId,Shape(长方体|圆棒|圆管),Unit(mm|inch),X,Y,Z,AddX,AddY,AddZ:decimal,Quantity:int,IncludeInTotals,...}；material: MaterialDefinition{Id,Name,Density:decimal(g/cm³),PricePerKg:decimal,Currency,Reference}；files: IEnumerable<string>本地CAD文件，ImportSavedFiles只读文件元数据；manifest: CSV/TXT路径；必须明确unit与include标志，尺寸标记为用户清单值。

**前提**：Calculate/Validate为纯逻辑；导入需受控文件读权限；材料Id对应且尺寸合法。

**流程**：1. ValidateMaterial/Validate检查。 2. Calculate：先换mm，加量是总尺寸量；圆管内径=Z-AddZ；计算kg与币种金额。 3. ImportSavedFiles产生待填写条目；ImportFileManifest解析显式尺寸；均不打开CAD/测量实体。

**输出**：StockEstimate{FinishedXmm/Ymm/Zmm,VolumeCm3,EachKg,TotalKg,TotalCost,Formula}或List<StockItem>。

**副作用**：Calculate不调用宿主、不写库；导入读取文件，不隐式纳入缺尺寸条目。

**回滚/失败**：纯计算无需回滚；只有通过UI保存才写库。

**限制**：不按文件名推断尺寸；不是读取MCAM已保存毛坯或自动生成加工参数。

**公开签名**：

```csharp
LittleBee.Rebuilt.Materials :: public static StockEstimate Calculate(StockItem stock, MaterialDefinition material)
LittleBee.Rebuilt.Materials :: public static void ValidateMaterial(MaterialDefinition material)
LittleBee.Rebuilt.Materials :: public static void Validate(MaterialsData data)
LittleBee.Rebuilt.Materials :: public static List<StockItem> ImportSavedFiles(IEnumerable<string> files)
LittleBee.Rebuilt.Materials :: public static List<StockItem> ImportFileManifest(string path, IEnumerable<MaterialDefinition> materials)
```

**证据**：`author:LittleBee2027-independent/src/Materials.cs#L128`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.materials_ui_batch · 材料库维护及批量实体测量

**interactive** · 编辑材料/毛坯，或用户明确同意保存并切换临时文件测实体包围尺寸。

**输入与单位**：ui: 新增/删行、读取当前毛坯、计算、保存、JSON备份/导入、CSV/HTML/文件清单导出；batch: 用户选择文件、材料、长边排序、是否逐文件确认；只能UI发起。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Materials.Show维护资料；普通文件清单导入不测量。 2. 批量实体自动测量先显式保存当前文档，创建恢复副本和逐源哈希副本。 3. 模态窗关闭后才打开临时副本，新建临时铣削组和矩形毛坯SetToAllSolids测量；结束恢复原文档。

**输出**：尺寸、单位、实体数、来源SHA、BatchJournal及恢复状态；成功条目存材料库。

**副作用**：真实保存原文档并切换文档；临时文档创建组/毛坯；写恢复副本/日志，源测量文件不写回。

**回滚/失败**：finally尝试重开原文档；失败保留恢复副本并要求交互决定；不是保持所有内存会话状态的事务。

**限制**：RunBatchCore/RunInteractiveBatch不是公开typed API；首批MCP不封装文件切换测量。；只测导入后的实体；曲面/网格不冒充实体；包围尺寸不是净体积。

**公开签名**：

```csharp
LittleBee.Rebuilt.Materials :: public static void Show()
```

**证据**：`author:LittleBee2027-independent/src/Materials.cs#L22`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.machines · 机床/后处理/输出配置与适配合同

**interactive** · 建立可选择的机床配置档案与受控后处理选项。

**输入与单位**：profile: Machines.Profile：名称、控制器、可选MachineDefinition、PostFile(.pst)、ImageFile、OutputDirectories、TemplateDirectory/PreferredTemplate、NcExtension、日期/零件子目录、检查选项、Compatibility。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. Machines.Show新增/复制/编辑/删除并保存档案，检查文件路径。 2. PostDefault保留post默认；其他兼容选项必须有匹配post哈希/依赖的适配器映射。

**输出**：machines.json中的Profile/Catalog与兼容检查。

**副作用**：修改本地配置；选择Profile本身不切换宿主机床组，不改机床定义。

**回滚/失败**：恢复用户配置备份；没有CAM批次Rollback。

**限制**：Load/Save/ResolveCompatibility是internal，不能把档案字段当公开执行API。；post选项不等于机床安全验证。

**公开签名**：

```csharp
LittleBee.Rebuilt.Machines :: public static void Show()
```

**证据**：`author:LittleBee2027-independent/src/Machines.cs#L67`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.exchange · 导出/导入工序库与模板管理

**interactive** · 保存可复用的工序库并按明确目标导入。

**输入与单位**：export: 选中工序；.lbmc ZIP按组打包原生工序库+JSON/CSV，或直接.mcam-operations；可选关联几何/配置引用快照；import: 来源.lbmc/.mcam-operations/.mcam；勾选工序；保留组、导入几何、用当前视图、清注释、单工序编辑、另存包内配置；templates: 记为机床模板、打开目录、归档模板文件。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. ShowExport核选择并导出。 2. ShowImport浏览并预览，核源哈希与活动目标机床组后逐工序导入。 3. 核新增ID/选择/日志，导入后用户检查几何并按需重算。

**输出**：工序包与附属清单；导入工序ID和日志。

**副作用**：导出写文件；导入可能新增工序、刀具、组/几何并选中结果；不自动计算进给转速；归档会移动模板文件。

**回滚/失败**：导入部分失败会保留新增工序并列出AddedIds，不自动撤销；须审阅日志和原生管理器处理。磁盘归档/导出另行管理。

**限制**：实现为private流程，未公开参数化Import/Export；配置快照仅文件引用，不打包通用机床环境。

**公开签名**：

```csharp
LittleBee.Rebuilt.Exchange :: public static void ShowImport()
LittleBee.Rebuilt.Exchange :: public static void ShowExport()
```

**证据**：`author:LittleBee2027-independent/src/Exchange.cs#L34`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.post · 显式执行/后处理（仅交互流程）

**interactive** · 用户明确要求对审核后的选中工序生成NC。

**输入与单位**：selection: 选中工序；单组或按所选工序涉及的多机床组；profile: 逐组已保存机床配置、确切post/依赖哈希、输出目录；confirm: 用户预览后勾选生成NC；可选已声明适配器的MI/MR参数准备。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. ShowExecute检查选中工序、工具/补偿/脏状态/行程与配置。 2. 需要参数准备时先备份原生工序包，写并回读20槽；不隐式重算。 3. 再次核目标与post，用户确认后生成；多组任一失败停止后续组。

**输出**：独立批次目录内NC和HTML/CSV/JSON、文件存在/哈希与恢复记录。

**副作用**：此流程确实生成NC；执行时临时使用所选post，结束恢复原post/活动组/选择。；可显式修改MI/MR并标需重算；不将语义选项直接改写post代码。

**回滚/失败**：恢复临时post和选择；已输出文件保留，部分失败目录保留；参数失败尝试恢复并保留备份，成功无统一公开Rollback。

**限制**：本文仅记录源码能力，没有执行post或宣称NC正确；native返回/文件存在不能证明NC语义、仿真或机床安全。；ExecutePost/ExecuteGroups/参数准备为private；不得暴露任意反射执行或把ShowExecute包装成无人值守typed成功。

**公开签名**：

```csharp
LittleBee.Rebuilt.Exchange :: public static void ShowExecute()
```

**证据**：`author:LittleBee2027-independent/src/Exchange.cs#L36`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

### bee.registration · 启动注册与跟随通知（不直接开放）

**not_exposed** · 覆盖源码公开的注册/事件动作；交给宿主生命周期。

**输入与单位**：parameter: int宿主参数；notification: MCamEvent，仅宿主通知。

**前提**：不作为普通加工任务调用；不得伪造宿主事件。

**流程**：1. Main.InstallRibbon/RibbonSetup.Install注册页签；FollowNotification由Main.Notify接入。

**输出**：界面注册与跟随事件状态。

**副作用**：可能注册UI或按跟随设置改变平面；没有加工输出。

**回滚/失败**：按宿主生命周期管理；不是CAM批次回滚。

**限制**：不要将任意事件/启动生命周期注册为公开MCP工具。

**公开签名**：

```csharp
LittleBee.Rebuilt.Main :: public MCamReturn InstallRibbon(int parameter)
LittleBee.Rebuilt.RibbonSetup :: public static bool Install()
LittleBee.Rebuilt.Commands :: public static void FollowNotification(MCamEvent notification)
```

**证据**：`author:LittleBee2027-independent/src/Main.cs#L38`；`author:LittleBee2027-independent/src/RibbonSetup.cs#L10`；`author:LittleBee2027-independent/src/Commands.cs#L74`；`author:LittleBee2027-independent/evidence/build-manifest.json`；`author:LittleBee2027-independent/evidence/toolbar-native-validation.md`。逐源SHA-256在JSON中。

## Workshop2027

2.8.0公开仓库整合版：批量参数/三面/群组、视图与毛坯有本模块实现；其余57个Forward方法是目标模块路由。

- public Work/Workflow提供部分真实typed候选；Main(int p)通常打开模态UI或转发。
- 三面=WCS工作坐标、ConstructionPlane构图面、ToolPlane刀具平面；ID/原点/方向须一起理解。
- 批量参数/三面/毛坯只有失败恢复，没有成功后的统一公开回滚句柄。
- 当前源位于repo:src/Workshop；作者WorkshopTools2027根dist为旧CAC432B4...，不能代替发布4E9B1E08...。

### workshop.inspect · 读取所选工序三面与参数

**typed_candidate** · 批量修改前检查WCS/CPlane/TPlane及Feed/Spindle/余量。

**输入与单位**：ids: int[]；SelectedIds可读当前选择。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. ReadPlanes/ReadParameters按ID读取。 2. 检查Equal、Css、Locked、Dirty、Kind以及Wall/Floor可空。

**输出**：PlaneRow[]、ParameterRow[]。

**副作用**：只读；无自动重算或保存。

**回滚/失败**：无需回滚。

**限制**：三面ID相同只说明引用一致，不证明工艺或机床运动正确。

**公开签名**：

```csharp
Workshop2027.Work :: public static int[] SelectedIds()
Workshop2027.Work :: public static PlaneRow[] ReadPlanes(int[] ids)
Workshop2027.Work :: public static ParameterRow[] ReadParameters(int[] ids)
Workshop2027.Main :: public MCamReturn CheckPlanes(int p)
```

**证据**：`repo:src/Workshop/Workshop.cs#L53`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.parameters · 批量设置2D工序进给/转速/余量

**typed_candidate** · 选择原生Contour/Pocket/Facing，修改明确勾选字段。

**输入与单位**：ids: int[]非空不重复；feed: double?，null保留；>0，原工序模式；spindle: double?，null保留；有效整数rpm；wall: double?，null保留；>=0文档单位；floor: double?，null保留；>=0文档单位。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；未锁定且仅Contour/Pocket/Facing；至少一项非null；恒线速工序不能设rpm。；无活动Undo事务。

**流程**：1. 读取前值并展示差异。 2. SetParameters提交并fresh逐项回读。 3. 返回审计与Dirty状态；用户另行重算。

**输出**：已应用参数；Before/After审计JSON。

**副作用**：改原工序并MarkDirty；写MC2027Workshop审计。

**回滚/失败**：失败Cancel后显式恢复原值并回读；成功没有公开批次Rollback，typed候选需提供独立前值/时间戳守卫才可承诺显式撤回。

**限制**：不改原进给模式；不适用于所有工序类型。

**公开签名**：

```csharp
Workshop2027.Work :: public static void SetParameters(int[] ids,double? feed,double? spindle,double? wall,double? floor)
Workshop2027.Main :: public MCamReturn BatchParameters(int p)
```

**证据**：`repo:src/Workshop/Workshop.cs#L84`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.planes · 将WCS/构图/刀具三面统一

**typed_candidate** · 明确希望所选2D工序统一到一个现有平面。

**输入与单位**：ids: int[]；plane: MCView，UI取当前WCS；typed候选应按ViewID解析并读原点/矩阵。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。；未锁定Contour/Pocket/Facing；无Undo事务。

**流程**：1. ReadPlanes显示前值，确认目标平面。 2. SetPlanes设置三引用和Use flags，Commit(false)，验证ID并Dirty。

**输出**：三面ID一致的工序。

**副作用**：改工序坐标定义；不移动源几何，不自动计算。

**回滚/失败**：失败显式恢复各原平面和Use flags；成功无公开回滚句柄。

**限制**：坐标改变会影响加工，不能只据Equal=true判定刀路正确。

**公开签名**：

```csharp
Workshop2027.Work :: public static void SetPlanes(int[] ids,MCView plane)
Workshop2027.Main :: public MCamReturn MatchPlanes(int p)
```

**证据**：`repo:src/Workshop/Workshop.cs#L105`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.groups · 批量创建刀路群组与插入位置

**typed_candidate** · 整理机床/刀路树层次。

**输入与单位**：parentId: int，现有机床或刀路父组；UI用活动组；prefix: 1..40可见字符；start: int>=0，须满足start<=999999-count；count: int 1..200；insert: InsertAfter使用当前选中工序并调用原生OMarrowRight。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. CreateGroups生成prefix+两位起号名称，先拒绝冲突。 2. 核返回的组ID/名称；要调整插入箭头时用InsertAfter交互入口。

**输出**：新群组ID，或宿主插入箭头位置。

**副作用**：创建群组/刷新管理器；InsertAfter只转原生命令。

**回滚/失败**：创建中失败逆序删除本批组；成功没有公开Rollback；含后续工序的组不可盲删。

**限制**：InsertAfter仅interactive子动作，不是typed群组创建的一部分；没有公共数值式设置插入点接口。

**公开签名**：

```csharp
Workshop2027.Work :: public static int[] CreateGroups(int parentId,string prefix,int start,int count)
Workshop2027.Main :: public MCamReturn InsertAfter(int p)
Workshop2027.Main :: public MCamReturn BatchGroups(int p)
```

**证据**：`repo:src/Workshop/Workshop.cs#L114`；`repo:src/Workshop/Workflow.cs#L23`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.views · 最近世界正交视图、跟随选项与视图对正

**typed_candidate** · 将当前图形朝向吸附到24个世界正交旋转之一。

**输入与单位**：matrix: double[9]行主序、右手正交；NearestMatrix纯计算；options: ViewOptions(bool Construction=false,bool Tool=false,bool Wcs=false)；align: AlignView把GraphicsView设为当前CPlane并FitScreen。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 可纯计算OrthogonalCandidates/NearestMatrix。 2. LoadViewOptions/SaveViewOptions保存跟随选择；SnapView复用或创建零原点正交MCView。 3. 按options设置W/C/T并设置G；核回读。

**输出**：short ViewID、矩阵或view-options.json。

**副作用**：改当前视图；可能新建命名视图；可写用户跟随设置。

**回滚/失败**：SnapView失败恢复旧W/C/T/G并清理自建未被使用的视图；成功无Undo句柄，可手动切回；视图创建不等于几何可撤销。

**限制**：ViewOptions/AlignView为UI入口；typed适配需分别标出配置写入和视图变更。

**公开签名**：

```csharp
Workshop2027.Workflow :: public static ViewOptions LoadViewOptions()
Workshop2027.Workflow :: public static void SaveViewOptions(ViewOptions value)
Workshop2027.Workflow :: public static double[][] OrthogonalCandidates()
Workshop2027.Workflow :: public static double[] NearestMatrix(double[] matrix)
Workshop2027.Workflow :: public static short SnapView(ViewOptions options)
Workshop2027.Main :: public MCamReturn NearestView(int p)
Workshop2027.Main :: public MCamReturn ViewOptions(int p)
Workshop2027.Main :: public MCamReturn AlignView(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L79`；`repo:src/Workshop/Workshop.cs#L31`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.stock · 设置矩形毛坯并回读

**typed_candidate** · 当前铣削机床组需要明确矩形尺寸、原点和定位点。

**输入与单位**：groupId: int，已有可读MillStock组；size: Point3D正XYZ，文档单位；origin: Point3D有限XYZ，按StockOriginPosition定位语义；anchor: StockOriginPosition真实SDK枚举；不要用UI下拉序号冒充稳定值；planeId: short，已有平面ViewID。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 保存原MillStockData快照；明确尺寸/原点/锚点/平面。 2. SetRectangularStock写Rectangle、DisplayStock=true；读回尺寸/原点/锚点/平面。

**输出**：矩形毛坯设置。

**副作用**：修改组毛坯，刷新管理器/图形；不改变实体、不计算刀路。

**回滚/失败**：失败写回原Stock并验证；成功无公开回滚句柄，typed封装需另建守卫快照。

**限制**：不是自动实体测量或毛坯清料；尺寸/原点由用户明确。

**公开签名**：

```csharp
Workshop2027.Workflow :: public static MillStockData CloneStock(MillStockData source)
Workshop2027.Workflow :: public static void SetRectangularStock(int groupId,Point3D size,Point3D origin,StockOriginPosition anchor,short planeId)
Workshop2027.Main :: public MCamReturn StockSetup(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L147`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.hub_templates · 工艺助手总面板、模板导入与使用目录

**interactive** · 导航功能或打开LittleBee工序库导入。

**输入与单位**：p: int宿主参数。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. OpenHub选择功能（通过PostFTCommand排队）。 2. Templates/ImportOperations打开LittleBee.Rebuilt.Exchange.ShowImport；Usage打开安装目录。

**输出**：目标窗口/资源管理器。

**副作用**：总面板只排队命令；模板导入效果以bee.exchange为准。

**回滚/失败**：关闭窗口；已导入结果依照LittleBee的部分失败保留合同。

**限制**：总面板返回不证明排队命令业务完成；不能暴露ExistingModule任意type/method反射调用。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn ImportOperations(int p)
Workshop2027.Main :: public MCamReturn OpenHub(int p)
Workshop2027.Main :: public MCamReturn Templates(int p)
Workshop2027.Main :: public MCamReturn Usage(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L24`；`repo:src/Workshop/Workshop.cs#L25`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.route_machining · 加工业务路由

**interactive** · 进入本文对应模块的预览、创建、回读、计算或回滚。

**输入与单位**：p: int，宿主入口参数；{"entry":"PorscheBoundary","target":"PorscheAdvanced2027.Boundary"}；{"entry":"PorscheHealing","target":"PorscheAdvanced2027.Healing"}；{"entry":"PorscheHoles","target":"PorscheAdvanced2027.Holes"}；{"entry":"OperationTools","target":"OperationTools2027.OpenHub"}；{"entry":"SolidBoundary","target":"SolidBoundary2027.Show"}；{"entry":"AdvancedDrill","target":"AdvancedDrill2027.Show"}；{"entry":"TapDrill","target":"AdvancedDrillTap2027.Show"}；{"entry":"HsmPocket","target":"HSMRebuild2027.CreatePocket"}；{"entry":"HsmReadback","target":"HSMRebuild2027.Readback"}；{"entry":"HsmCalculate","target":"HSMRebuild2027.Recalculate"}；{"entry":"HsmRollback","target":"HSMRebuild2027.Rollback"}。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 按名称打开精确目标；跟随目标模块预览、输入和确认流程。 2. 返回后检查目标结果、ID、状态或文件；不只依赖RunFTCommand布尔值。

**输出**：目标入口返回值/窗口；无统一类型化业务结果。

**副作用**：参考工序/几何选择与参数以目标工作流为准；HsmCalculate和HsmRollback有实际计算/删除效果。

**回滚/失败**：目标模块自己的取消/回滚合同；路由层没有统一事务。

**限制**：这些是现有公开MCamReturn入口；并未实现新的MCP工具。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn PorscheBoundary(int p)
Workshop2027.Main :: public MCamReturn PorscheHealing(int p)
Workshop2027.Main :: public MCamReturn PorscheHoles(int p)
Workshop2027.Main :: public MCamReturn OperationTools(int p)
Workshop2027.Main :: public MCamReturn SolidBoundary(int p)
Workshop2027.Main :: public MCamReturn AdvancedDrill(int p)
Workshop2027.Main :: public MCamReturn TapDrill(int p)
Workshop2027.Main :: public MCamReturn HsmPocket(int p)
Workshop2027.Main :: public MCamReturn HsmReadback(int p)
Workshop2027.Main :: public MCamReturn HsmCalculate(int p)
Workshop2027.Main :: public MCamReturn HsmRollback(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L25`；`repo:docs/PLUGINS.md`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.route_bee · 小蜜蜂工序编辑路由

**interactive** · 使用已选工序编辑、复制、命名或跟随开关。

**输入与单位**：p: int，宿主入口参数；{"entry":"EditOperation","target":"LittleBee2027.EditOperation"}；{"entry":"EditTool","target":"LittleBee2027.EditTool"}；{"entry":"EditGeometry","target":"LittleBee2027.EditOperationGeometry"}；{"entry":"CommonParameters","target":"LittleBee2027.EditCommonParameters"}；{"entry":"FollowPlanes","target":"LittleBee2027.ChangeView"}；{"entry":"RenameNci","target":"LittleBee2027.ChangeNci"}；{"entry":"CopyOperations","target":"LittleBee2027.CopyOperation"}；{"entry":"PasteOperations","target":"LittleBee2027.PasteOperation"}。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 按名称打开精确目标；跟随目标模块预览、输入和确认流程。 2. 返回后检查目标结果、ID、状态或文件；不只依赖RunFTCommand布尔值。

**输出**：目标入口返回值/窗口；无统一类型化业务结果。

**副作用**：副作用/取消/回滚以bee.edit/copy_paste/rename/follow_view为准。

**回滚/失败**：目标模块自己的取消/回滚合同；路由层没有统一事务。

**限制**：这些是现有公开MCamReturn入口；并未实现新的MCP工具。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn EditOperation(int p)
Workshop2027.Main :: public MCamReturn EditTool(int p)
Workshop2027.Main :: public MCamReturn EditGeometry(int p)
Workshop2027.Main :: public MCamReturn CommonParameters(int p)
Workshop2027.Main :: public MCamReturn FollowPlanes(int p)
Workshop2027.Main :: public MCamReturn RenameNci(int p)
Workshop2027.Main :: public MCamReturn CopyOperations(int p)
Workshop2027.Main :: public MCamReturn PasteOperations(int p)
```

**证据**：`repo:src/Workshop/Workshop.cs#L32`；`repo:docs/PLUGINS.md`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.route_geometry · 几何、夹具、链、曲面与MP路由

**interactive** · 按需进入几何生成/选择/分析或夹具工具。

**输入与单位**：p: int，宿主入口参数；{"entry":"GeometryTools","target":"GeometryTools2027.Show"}；{"entry":"NativeGeometry","target":"GeometryTools2027.NativeCommands.Show"}；{"entry":"LevelExport","target":"LevelExport2027.Show"}；{"entry":"ChainTools","target":"ChainTools2027.Show"}；{"entry":"SvgGeometry","target":"SVGGeometry2027.Show"}；{"entry":"HirthTools","target":"HirthTools2027.Show"}；{"entry":"TpSketcher","target":"TpSketcher2027.Show"}；{"entry":"HolderTools","target":"HolderTools2027.Show"}；{"entry":"SurfaceNormals","target":"MPDesignTools2027.ReverseSelectedNormals"}；{"entry":"MPEdges3D","target":"MPEdgeTools2027.ShowEdges3D"}；{"entry":"MPEdges2D","target":"MPEdgeTools2027.ShowEdges2D"}；{"entry":"AnalyticRadius","target":"MPDesignRadiusSelect2027.SelectByAnalyticRadius"}；{"entry":"SurfaceTypes","target":"MPDesignSurfaceSelect2027.SelectVisibleSurfaceTypes"}；{"entry":"MpSections","target":"MPRebuild2027.Sections"}；{"entry":"MpSliceStack","target":"MPRebuild2027.SliceStack"}；{"entry":"MpDraft","target":"MPRebuild2027.DraftAnalysis"}；{"entry":"MpParting","target":"MPRebuild2027.PartingPreparation"}；{"entry":"MpNormals","target":"MPRebuild2027.FacetNormals"}；{"entry":"Fixtures","target":"FixtureTools2027.Show"}。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 按名称打开精确目标；跟随目标模块预览、输入和确认流程。 2. 返回后检查目标结果、ID、状态或文件；不只依赖RunFTCommand布尔值。

**输出**：目标入口返回值/窗口；无统一类型化业务结果。

**副作用**：可能创建几何/工序、改选择/法向/平面或写文件；本文只审计Workshop转发代码，目标细节见公开目录与相应知识模块。

**回滚/失败**：目标模块自己的取消/回滚合同；路由层没有统一事务。

**限制**：这些是现有公开MCamReturn入口；并未实现新的MCP工具。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn GeometryTools(int p)
Workshop2027.Main :: public MCamReturn NativeGeometry(int p)
Workshop2027.Main :: public MCamReturn LevelExport(int p)
Workshop2027.Main :: public MCamReturn ChainTools(int p)
Workshop2027.Main :: public MCamReturn SvgGeometry(int p)
Workshop2027.Main :: public MCamReturn HirthTools(int p)
Workshop2027.Main :: public MCamReturn TpSketcher(int p)
Workshop2027.Main :: public MCamReturn HolderTools(int p)
Workshop2027.Main :: public MCamReturn SurfaceNormals(int p)
Workshop2027.Main :: public MCamReturn MPEdges3D(int p)
Workshop2027.Main :: public MCamReturn MPEdges2D(int p)
Workshop2027.Main :: public MCamReturn AnalyticRadius(int p)
Workshop2027.Main :: public MCamReturn SurfaceTypes(int p)
Workshop2027.Main :: public MCamReturn MpSections(int p)
Workshop2027.Main :: public MCamReturn MpSliceStack(int p)
Workshop2027.Main :: public MCamReturn MpDraft(int p)
Workshop2027.Main :: public MCamReturn MpParting(int p)
Workshop2027.Main :: public MCamReturn MpNormals(int p)
Workshop2027.Main :: public MCamReturn Fixtures(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L29`；`repo:docs/PLUGINS.md`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.route_reporting · 截图、程序单、电极报告与中键配置路由

**interactive** · 打开报告/截图/确认设置窗口。

**输入与单位**：p: int，宿主入口参数；{"entry":"SetupSheet","target":"SetupSheets2027.Show"}；{"entry":"MiddleConfirm","target":"MiddleConfirm2027.Configure"}；{"entry":"ScreenTools","target":"ScreenTools2027.Show"}；{"entry":"ElectrodeReport","target":"ElectrodeReport2027.UI.Show"}。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 按名称打开精确目标；跟随目标模块预览、输入和确认流程。 2. 返回后检查目标结果、ID、状态或文件；不只依赖RunFTCommand布尔值。

**输出**：目标入口返回值/窗口；无统一类型化业务结果。

**副作用**：可能写报告/图像/配置；目标实现的验证等级各不相同。

**回滚/失败**：目标模块自己的取消/回滚合同；路由层没有统一事务。

**限制**：这些是现有公开MCamReturn入口；并未实现新的MCP工具。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn ScreenTools(int p)
Workshop2027.Main :: public MCamReturn ElectrodeReport(int p)
Workshop2027.Main :: public MCamReturn SetupSheet(int p)
Workshop2027.Main :: public MCamReturn MiddleConfirm(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L40`；`repo:src/Workshop/Workshop.cs#L41`；`repo:docs/PLUGINS.md`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.route_original · 15个X+原版入口路由

**interactive** · 启动已发布原版X+功能。

**输入与单位**：p: int，宿主入口参数；{"entry":"OriginalSwitchBG","target":"SwitchBG.m_main"}；{"entry":"OriginalChainIt","target":"ChainIt.m_main"}；{"entry":"OriginalHirth","target":"Hirth.m_main"}；{"entry":"OriginalSetupSheet","target":"SetupSheet.m_main"}；{"entry":"OriginalToolList","target":"ToolList.m_main"}；{"entry":"OriginalElectrodes","target":"ElectrodesReport.m_main"}；{"entry":"OriginalMergeFixture","target":"MergeFixture.m_main"}；{"entry":"OriginalFixtureSetup","target":"FixtureSetup.m_main"}；{"entry":"OriginalSketch","target":"TpSketcher.m_main"}；{"entry":"OriginalSnapshot","target":"XSnapShot.m_main"}；{"entry":"OriginalRenameNCI","target":"RenameNCI.m_main"}；{"entry":"OriginalHolder","target":"Holder_CH.m_main"}；{"entry":"OriginalSVG","target":"SVGImage.m_main"}；{"entry":"OriginalSTL","target":"Level2STL.m_main"}；{"entry":"OriginalOffset","target":"SetWorkoffset.m_main"}。

**前提**：Mastercam 2027/API29、Windows x64、.NET 10；已安装匹配 payload 与依赖。；宿主对象须在 Mastercam UI 线程串行调用；先核文档、单位、活动机床组与选择。

**流程**：1. 按名称打开精确目标；跟随目标模块预览、输入和确认流程。 2. 返回后检查目标结果、ID、状态或文件；不只依赖RunFTCommand布尔值。

**输出**：目标入口返回值/窗口；无统一类型化业务结果。

**副作用**：原版无本轮业务源码；仅路由/原件字节一致性，不能臆造参数化API或回滚。

**回滚/失败**：目标模块自己的取消/回滚合同；路由层没有统一事务。

**限制**：这些是现有公开MCamReturn入口；并未实现新的MCP工具。；原版15路大多数仅加载/打开证据；不得宣称完整业务验收。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn OriginalSwitchBG(int p)
Workshop2027.Main :: public MCamReturn OriginalChainIt(int p)
Workshop2027.Main :: public MCamReturn OriginalHirth(int p)
Workshop2027.Main :: public MCamReturn OriginalSetupSheet(int p)
Workshop2027.Main :: public MCamReturn OriginalToolList(int p)
Workshop2027.Main :: public MCamReturn OriginalElectrodes(int p)
Workshop2027.Main :: public MCamReturn OriginalMergeFixture(int p)
Workshop2027.Main :: public MCamReturn OriginalFixtureSetup(int p)
Workshop2027.Main :: public MCamReturn OriginalSketch(int p)
Workshop2027.Main :: public MCamReturn OriginalSnapshot(int p)
Workshop2027.Main :: public MCamReturn OriginalRenameNCI(int p)
Workshop2027.Main :: public MCamReturn OriginalHolder(int p)
Workshop2027.Main :: public MCamReturn OriginalSVG(int p)
Workshop2027.Main :: public MCamReturn OriginalSTL(int p)
Workshop2027.Main :: public MCamReturn OriginalOffset(int p)
```

**证据**：`repo:src/Workshop/Workflow.cs#L56`；`repo:docs/PLUGINS.md`；`repo:validation/xplus-provenance.json`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

### workshop.registration · 页签注册与低层转发辅助（不做加工工具）

**not_exposed** · 识别安装/生命周期能力，不当成加工结果。

**输入与单位**：p: int；type: string；method: string。

**前提**：由安装/启动流程维护；非普通加工MCP操作。

**流程**：1. InstallRibbon/Ribbon.Install注册功能区；ExistingModule反射转发给LittleBee。

**输出**：注册状态/目标窗口。

**副作用**：改变本次界面注册状态；任意反射入口不适合作为公开服务。

**回滚/失败**：遵循安装器/宿主生命周期；不定义加工Rollback。

**限制**：固定白名单业务入口可以交互使用，不能把type/method原样对外开放。

**公开签名**：

```csharp
Workshop2027.Main :: public MCamReturn InstallRibbon(int p)
Workshop2027.Ribbon :: public static bool Install()
Workshop2027.Workflow :: public static void ExistingModule(string type,string method)
```

**证据**：`repo:src/Workshop/Workshop.cs#L26`；`repo:src/Workshop/Workflow.cs#L81`；`repo:validation/bundle-host-integration.json`；`repo:validation/README.md`。逐源SHA-256在JSON中。

## 范围边界

覆盖所分配模块源码中的业务入口及其可操作子流程；Workshop全部57个Forward动作逐项映射到精确目标。Version/Init/Run/Notify/Close是NetHook生命周期，Run只是模块主窗口别名，不单独定义加工工作流。数学向量、序列化、格式化、UI控件构造等公共辅助方法不机械地注册为MCP工具；internal/private实现也不冒充公开API。

LittleBee功能面板的导出/导入/后处理、材料批量测量与报告已经按可用交互流程收录，不因缺少参数化公开方法而漏记。未来若要把这些业务改成typed工具，应单独设计明确输入/结果与副作用合同；本次没有修改其源码。
