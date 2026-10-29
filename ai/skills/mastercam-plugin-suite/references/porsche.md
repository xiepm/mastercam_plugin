# 保时捷直接调用

这四个 action 使用现有 `mc_prepare_change`、`mc_apply_plan` 和 `mc_rollback_plan`。先读对应 `typed.<action>`，再从 `mc_inspect` 取得真实实体、参考工序和 ViewID。完整参数以工具 schema 为准，未给定的加工参数不能沿用演示值。

| 意图 | action | 关键区别 |
|---|---|---|
| 只投影实体边界 | porsche.project_boundary | 保留凹形、内孔和分离区域；prepare 只分析，apply 才建闭合折线。 |
| 自动轮廓并生成粗/精/倒角 | porsche.contour | 三道真实工序；当前机床组的未锁定 Basic 2D 平底刀轮廓作参考。 |
| 自动删孔补面 | porsche.heal_holes | 按主圆柱孔段的**半径**闭区间筛选完整孔；生成独立副本，原实体保留。 |
| 复杂孔自动建工序 | porsche.holes | 按**直径**筛选主孔，识别真实孔段、入口和孔轴，生成分阶段工序。 |

`plane_id` 是 inspect.views 的 **ViewID**，不是 ViewNumber；投影高度、最低点和边界加工深度均相对该平面的完整仿射坐标系。`height:null` 使用投影最高点。`alignment` 是世界坐标单位向量，不是平面 ID。

轮廓编排的 `allow_create_tools:true` 表示明确允许缺刀时建刀；当前原生流程没有“禁止建刀”开关，不能把 false 当作已支持。孔流程可用 `CreateMissingTools:false` 限制为已有匹配刀具；孔径并不足以确定刃长、刀尖角、进给、转速和高度。倒角刀原生 TipAngle=45 对应本机构建验证的 90°夹角刀；不能把两个角度直接混用。

`Regenerate` 必须显式指定。true 会在这两个 Porsche 工序动作的 apply 中计算刀路，失败由原生检查返回；false 创建 Dirty 工序。其他动作的 apply 仍不隐含重算。可用 `mc_operation_information` 读取有效刀路范围；最低点回读通过不是碰撞或 NC 验收。

补面 prepare 返回原实体的目标孔和源对象指纹，**尚未完成补面**；能否成功由 apply 的原生内核、实体有效性和孔消失检查决定。多实体调用中已创建的本批副本会在后续失败时清理。不要把临时面标签当成跨副本稳定 ID。

返回 `data.result.output` 中的真实 `created_operation_ids`、`created_tool_slots`、`created_plane_ids` 或 `created_geometry_ids`，以及 native_audit/readbacks。回滚只属于本计划，应用后数据库几何、工序、刀具或平面变化会使回滚在删除前拒绝；选择改变本身不算冲突。原实体、原刀具、参考工序保持原样。

组合使用时，先保留原实体 ID。孔加工使用原有孔特征；删孔补面副本上的目标孔已经消失，不能悄悄拿副本替换孔识别输入。轮廓输出为二维边界加工，不是任意实体三维清料；螺纹、倒扣、未知过渡和相交不完整孔不得推断为已支持。

自然语言例子：“按我提供的半径范围预览删孔补面，保留原件”应只 prepare 并展示副本策略；“用给定刀具参数生成三阶段并重算”可在用户既有授权范围内继续 apply，不需重复确认已授权事项。超时仍先查原 request_id。
