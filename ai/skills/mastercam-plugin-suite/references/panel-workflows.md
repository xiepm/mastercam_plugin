# 将面板工作流改为直接调用

这批接口新增 16 类动作，累计 44 类动作、14 个 MCP 工具。功能均使用原生 API 或本合集可审查的业务代码；无需打开对应面板。先 `mc_inspect`，再按本表选择动作和真实 ID。

| 原入口/用途 | action | 输入与范围 |
|---|---|---|
| 高级钻孔 AD012 | `drilling.stages` | 已有刀具、参考工序、TPlane 局部点、每阶段用途/循环/深度/排序/切削值；中心钻、钻孔、沉孔、倒角。 |
| 攻丝 AD013 | `drilling.tap` | 可串联中心钻和预钻；公制右旋、明确节距及真实机床/后处理目标。 |
| 实体边界面板 | `geometry.convex_boundary` | 单个平面凸多面体、直边、世界 XY 构图面、一个闭环、已有可见结果层。凹形/孔/多区域投影使用 `porsche.project_boundary`。 |
| 串链拾取面板 | `selection.chains` | 明确线/弧/NURBS 图素 ID、预期链数、是否要求闭合、替换/追加选择。临时独立副本上原生串链，应用仅选择原图素。 |
| 几何边倒角面板 | `geometry.chamfer_edges` | 实体 ID、实时边标签、等距距离；输出独立实体副本，保留原件，不自动扩展相切边。 |
| 中键确认设置 | `interface.middle_confirm` | 本插件观察器开关及 100–600ms 时长；不触发确认点击，回滚恢复原配置文件及运行状态。 |
| 工艺助手共同参数 | `operation.parameters` | 支持的未锁定 2D 轮廓/挖槽/面铣工序，进给/转速/壁余量/底余量至少一项。RPM 修改拒绝 CSS 工序。 |
| 工序三面 | `operation.planes` | 将上述工序 WCS/CPlane/TPlane 统一为已有 ViewID；坐标数据不会随之自动重新解释。 |
| 小蜜蜂工序复制 | `operation.copy` | 轮廓/钻孔工序、当前机床内目标刀路群组；副本 Posting=false、Dirty=true。 |
| 批量群组 | `groups.create` | 当前活动父群组、名称前缀、起始序号和数量；回滚拒绝新增子组、已有工序或名称/父级变化。 |
| 群组改名 | `groups.rename` | 明确 group_id→名称；支持交换名称，拒绝冲突；原名被别人占用时拒绝回滚。 |
| 矩形毛坯 | `stock.rectangle` | machine_group_id、正尺寸、原点、锚点枚举、已有平面；完整旧毛坯设置可恢复。 |
| 坐标/视图设置 | `view.planes` | 四个已有 ViewID 及三项跟随选项；不改变小蜜蜂持久通知注册。 |
| 材料估算 | `materials.estimate` | 显式密度、每公斤价格、来源、币种、尺寸、单位、总余量及数量；只计算及写 JSON，不维护材料库。 |
| 工序库导出 | `operations.export` | 工序 ID、include_geometry；生成 `.mcam-operations`，原生回读数量，保存 SHA256。 |
| 工序参数库导入 | `operations.import` | 现有文件绝对路径、SHA256、库内 ID、当前活动刀路群组；`include_geometry` 必须为 false。 |

## 查询和执行

所有变更沿用 `mc_prepare_change → mc_apply_plan → 核对结果 → 按需 mc_rollback_plan`。参数完整且用户已授权自动执行时不重复询问。群组创建要求 parent_id 等于 mc_inspect 的活动群组，接口不提供任意移动插入箭头的动作；原生创建可能把活动位置切到新组，应用后用 mc_inspect 读取当前组。官方 MakeGroupCurrent 在本构建的子组路径设置默认工序组，不能用来声称已移动活动位置。

计划只属于当前宿主会话；不要跨重启复用。工序参数回滚恢复参数，不恢复旧刀路计算状态。

`mc_entity_information(expected_document, entity_ids)` 返回真实图素类型及可用边标签、相邻持久面 ID。边倒角仅接受唯一匹配的明确边；查询后发生库导出/导入或几何编辑须重新查询。标签是临时句柄，不能当作持久 ID。

`mc_operation_library(expected_document, path)` 只读现有原生工序库，返回 SHA256、库内 ID、名称、组及刀具摘要。它不导入工序。不要拿当前文档工序 ID 代替库内 ID。

例如共同参数修改，未修改字段也明确写 null：

```json
{"action":"operation.parameters","expected_document":"E:/Tests/part.mcam","operation_ids":[17],"parameters":{"feed":123,"spindle":1234,"wall":0.1,"floor":null}}
```

这是接口示例，不是切削推荐。生产值来自用户工艺。

## 钻孔与攻丝坐标合同

`parameters.sets` 中每组提供 `reference_id`、`local_points`、`top` 和 `stages`。参考工序确定完整平面原点和轴；局部点到世界点包含平移。`Depth/Clearance/Retract/FeedPlane` 均沿该工序平面解释。输入不接受隐式选择点或鼠标拾点。

阶段字段使用业务合同原名：`Name/Purpose/Cycle/Sorting/Tool/Cutting/Depth/Clearance/Retract/FeedPlane/Peck1/Peck2/PeckClearance/ChipBreak/Dwell/ThreadPitch/TapTarget`。精确枚举与必填字段以 `mc_prepare_change` schema 为准。

刀具通过数据库 Slot 绑定，并核对刀径、类型、H/D。`NativeFeedModeReviewed` 必须为 true，表示传入的是确认过的原始进给值，服务不会自动做每转/每分换算。攻丝还要求 `mc_inspect.workflow_context.tap_target` 中的当前机床与后处理身份、显式节距及 `ExplicitFeedReviewed=true`。本接口不宣称机床 G84 后处理已验收。

Apply 创建工序并逐字段回读，不自动重算或后处理。回读包括实际点数、局部/世界坐标、循环、刀具及各阶段参数。创建成功与可加工刀路、碰撞仿真是不同结果。

## 工序库边界与恢复

导出/参数导入可能使原生内核重新分配临时面标签。检查按持久面 ID、面类型、法向、颜色、边数量、图素属性/时间戳及工序/刀具/群组进行；临时标签差异完整写入比较报告。仅无量纲视图矩阵的 XYZ 分量允许 1e-12 绝对浮点误差，其余数据不以通用容差放宽。

**带几何导入尚不可用。** API29 测试曾在带几何 ImportOperation 后的图素读取中发生原生访问异常，公开 schema 和宿主入口都拒绝 `include_geometry=true`。参数库导入后应明确关联几何，再独立检查/重算；不能把“导入成功”当作刀路可加工。不要改用通用脚本工具绕过此限制。

报告/材料估算/工序导出回滚保留产物文件。库导入回滚只清理该计划记录的新工序、图素、刀具与平面；检测到后续改动则拒绝删除。回滚拒绝后计划进入终止的 RollbackFailed 状态，不可直接重试；先检查实际对象和日志，必要时显式恢复自有对象。超时先查 `mc_request_status`，不可重发。宿主崩溃后保存原始请求和系统日志，核对新会话与源文件，再恢复工作；不要伪造成功回执。

## 仍需界面或专门实现的范围

八个旧面板仍作为可选入口保留。上述直接接口覆盖明确列出的工作流，未把所有菜单都改为无界面：任意面删除/复杂补面、完整分模、原版 X+ 的所有高级路径、机床/后处理配置编辑、材料库维护与跨文件批量实体测量、生产后处理/仿真仍按各自合同操作。已有 `porsche.heal_holes` 处理完整孔副本，不等同任意面删除。保存/另存可按已授权任务使用现有 Mastercam MCP 的明确工具，不需要伪装成面板接口。

CIMCO 的安装、配置和功能保持原状；不新增其自动调用接口。
