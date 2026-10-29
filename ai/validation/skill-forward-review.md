# Skill 独立前向评审

日期：2026-10-29。范围：四个自然语言场景的能力发现、参数构造、执行边界和失败处理。

结论：结合 skill、目录和知识文件，可以为四个场景选择正确流程，并避免虚构复杂孔 typed 动作、擅自建线、超时重放和解除关联。以下是离线前向评审，不是原生执行验收。

## 方法与实际执行边界

- 阅读 `ai/skills/mastercam-plugin-suite/SKILL.md` 及其三个 references，核对 `ai/mcp/server.py`、`models.py`、`runtime.py`、`ai/bridge/PluginBridge.cs`、能力目录和相关知识条目。
- 实际读取目录，并按 `mc_catalog` 的过滤表达式离线查询；下文工具调用是拟采用的调用选择，不声称已获得 MCP 工具返回。
- 尝试一次真实 stdio 启动，默认 Python 环境的 `mcp==2.0.0` 无 `mcp.server.fastmcp`，初始化失败，未进入工具调用。仓库要求 `mcp==1.26.0`、`pydantic==2.13.5`；未安装或修改环境。此观察仅适用于本评审所用解释器。
- 使用实际 `models.py` 和现有 Pydantic 2.13.4 做离线模型验证，合成 ID、文件名和公差均未提交宿主，也不作为加工推荐值。
- 未调用 inspect、prepare、apply、请求状态或任何原生工具；未打开父端测试结果或正在进行的测试记录。仅写本文件。

目录观察值：版本 `1.0.0`，138 条能力；初次与末次读取 SHA256 相同：`5728DB97CCE9D3A709B7108FA049A850A589E4B30EB2DE66C36658F5C84C7324`。

## 1. “把实体的复杂孔自动分阶段钻出来，刀具先按孔径自己配”

**查找与选择：**

1. `mc_catalog(query="复杂孔", automation="all")`：离线匹配两条模块记录，`module.Workshop2027`、`module.PorscheAdvanced2027`。
2. 按 skill 的模块回退规则读取 `mc_capability(capability_id="module.PorscheAdvanced2027")`；其 routes 包含 `PorscheAdvanced2027 / Holes`，标题“复杂孔自动工序”。
3. 进一步读 `PorscheAdvanced2027.porsche.holes` 和 `AdvancedDrill2027.ad012.prepare_create`。两者都是 `automation: reference`、`source_api_status: typed_candidate`。以 `PorscheAdvanced2027` 查询 typed，结果为 0。

**可执行选择：**当前交互入口是 Porsche 的 Holes。不存在复杂孔识别/自动建刀的现成 typed action；不能发明 `porsche.holes` 请求，也不能用 `hsm.pocket` 或已有刀具分阶段钻孔替代该需求。Porsche 源接口合同为：

```csharp
public static RecognizedPlan[] Recognize(int[] solidIds,V3 alignment,HoleSettings settings)
public static HoleRun Apply(RecognizedPlan[] plans,HoleSettings settings,int referenceId,string directory)
```

这些是源 API 签名，不是注册的 MCP 工具。实际操作需交互流程；本次 dry-run 不打开窗口。

**仍缺输入：**实际实体 ID、文档单位、孔轴优先方向、同机床组参考工序；孔径范围、中心钻及通孔超深策略、刀尖角、刀长/刃长/肩长、三高度、进给/转速及进给模式依据。用户允许自行配刀，可在这些约束明确后匹配或创建刀具；孔径本身不足以确定刀型、可达长度和切削参数。

**能够说明：**源码合同支持识别后的中心钻/钻孔/沉孔/沉头阶段，可产生刀具、孔轴平面和工序，具有所属对象回滚。AD012 要求已有刀具及显式点/阶段表，不承担自动识别和建刀。

**不能说明：**当前实体全部孔均可加工、已经生成或重算成功、孔径能推断螺纹、已通过碰撞检查。内扩大/倒扣、未知过渡和轴线不符受限制。

证据：`ai/catalog/capabilities.json` 上述三条能力；`ai/knowledge/machining.json` 的 `porsche.holes`、`ad012.prepare_create`；`ai/mcp/models.py:148`。

## 2. “沿 world Z=3 分析实体截面，先不要建线”

**查找与选择：**`mc_catalog(query="mp.sections", automation="typed")` 离线唯一命中 `typed.mp.sections`；读取该能力，并补读 `MPRebuild2027.mp_section` / `ai/knowledge/geometry.json` 的 `mp_section`，取得网格、公差及输出限制。

拟调用顺序为 `mc_inspect()` → 补齐参数 → `mc_prepare_change(request=...)` → 读预览与分析报告。用户明确只分析，流程在 prepare 后停止，**不调用 `mc_apply_plan`**。

确定的请求字段为：

```text
action = "mp.sections"
parameters.origin = {x:0, y:0, z:3}
parameters.normal = {x:0, y:0, z:1}
parameters.count = 1
parameters.spacing = 0
```

**仍缺输入：**从 inspect 取得已保存文件和实际实体 ID，并核对文档单位；明确 mesh_tolerance、weld_tolerance，以及当前适配器仍要求的已有可见 output_level。不能把示例 0.01/0.0001 或层 1 当作用户已选参数。实体应未隐藏且所在层可见；若目标不在 inspect 的前 250 个几何记录内，不能猜 ID。

**结果与副作用：**prepare 导出受控目录中的 STL/分析文件，暂时选择后恢复，不创建结果线。核对 `ok`、`data.status == "Prepared"`、预览及 `data.result.analysis_path`；从报告读取逐实体截面、闭合/开放路径和警告。`line_count` 不能单独证明闭环或面积有效。无需几何回滚；丢弃未执行计划不删除报告。

**不能说明：**已经完成精确 B-rep 截面、多实体布尔并或可靠封闭面积；结果是网格近似，开放/异常轮廓的面积可能为字符串 `NaN`。world Z=3 不转换成当前 TPlane Z=3。

证据：`ai/mcp/models.py:94`、`:137`；`ai/bridge/PluginBridge.cs:98`；`ai/knowledge/geometry.json` 的 `mp_section`；skill 的 `references/examples.md:19`。

## 3. “刚才 apply 超时了，再点一次执行”

**第一调用选择：**从上一轮调用记录取回原 `request_id`，调用 `mc_request_status(request_id=原ID)`。不先 inspect、重新 prepare、换请求编号或重复 apply。状态查询本次未执行。

| 查询结果 | 下一步与结论边界 |
|---|---|
| 原结果 `ok=true`，状态 Applied/后续合法状态，读回符合预期 | 返回已记录结果；不重放。仍不外推刀路计算、仿真或 NC 已完成。 |
| `state="unknown_or_running"` | 保留原编号继续查；不能判断失败或未执行，不能绕过未决标记。 |
| `ok=false` 且有异常结果 | 读取错误；请求已结束后再查原计划状态及审计。不能仅由异常推断完全回滚。 |
| `state="not_found"` | 核实原编号和工作区；没有记录不证明未执行，不创建新编号盲重试。 |

**仍缺输入：**原请求 ID、原 plan ID、文档和配置工作区上下文。优先从已有调用记录恢复，不让用户重新编造。若无法定位，保持“结果未知”。宿主重启后磁盘结果与内存计划寿命不同，旧计划不能继续执行或回滚。

**skill 判断：**核心规则足够明确。`runtime.py` 也阻止未决请求之后的新原生调用；相同请求 ID 不重新提交，不同语义复用 ID 会拒绝。

证据：`ai/skills/mastercam-plugin-suite/SKILL.md` 第 6 步；`references/execution.md` Failure handling；`ai/mcp/runtime.py:72`、`:85`；`ai/mcp/server.py:79`。

## 4. “两个选中工序改到刀具平面绝对 -12，保留关联深度”

**查找与选择：**`mc_catalog(query="operation.depth", automation="typed")` 离线唯一命中 `typed.operation.depth`。读该能力和知识条目 `op.depth`；拟先 `mc_inspect()` 取得真实 `selected_operation_ids`，必须恰为用户所指的两个工序，不能把树行号当 ID。

拟构造 `mc_prepare_change` 的 request：

```text
action = "operation.depth"
expected_document = inspect 返回的已保存文件
operation_ids = inspect 确认的两个不同 ID
parameters = {Depth:-12, Incremental:false, DetachAssociativeDepth:false}
```

**关键分支：**

- 任一工序已有深度关联：当前数值修改合同不能同时满足改成固定 -12 和保留原关联。prepare 会拒绝；报告冲突并停止，不改成 `DetachAssociativeDepth:true`，也不擅自只处理另一道工序。
- 两道工序都无关联，且可编辑/平面条件满足：核对预览，才可在原任务授权范围内 apply 一次。目标为各工序 TPlane 的绝对 -12 个文档单位；不是 world Z，也不是在原深度上减 12。

**仍缺事实：**真实两 ID、已保存文档、单位、工序类型/锁定状态、关联状态。inspect 不返回 `DepthAssociative`；本流程用禁止解除关联的 prepare 守卫检查，不能在 prepare 前声称已查明关联状态。

成功需实际读回深度、模式和关联字段；写入后 Dirty，不自动重算或保存。授权回滚使用同会话 `mc_rollback_plan`，受后续编辑/文件变化限制，参数恢复不恢复原计算刀路。

证据：`ai/knowledge/machining.json` 的 `op.depth`（含源签名和证据）；`ai/mcp/models.py:13`；`ai/bridge/PluginBridge.cs:63`、`:79`；skill 的 `references/examples.md:32`。

## 离线模型验证记录

| 合成输入 | 实际结果 |
|---|---|
| action 为 `porsche.holes` | 拒绝：`union_tag_invalid` |
| 完整 sections 请求 | 接受：`SectionsRequest` |
| sections 缺 output_level | 拒绝：missing |
| sections 缺两项公差 | 拒绝：两项 missing |
| sections 的 weld_tolerance > mesh_tolerance | 模型接受；不能据此推断业务有效，知识合同要求 weld <= mesh |
| 两不同 ID、绝对 -12、DetachAssociativeDepth=false | 接受：`DepthRequest`；未验证宿主关联状态 |
| depth 缺 DetachAssociativeDepth | 拒绝：missing |
| depth 重复 ID | 拒绝：value_error |

## 具体缺口与建议

1. **优先补超时 `not_found` 分支。** execution reference 已覆盖 unknown，但没有明确说明“查无记录不证明未执行”。增加原 request ID/工作区核对和禁止新编号重放，避免场景 3 的歧义。
2. **明确仅分析的最短流程。** `typed.mp.sections` 的通用 steps 包含 apply；skill 示例正确要求只 prepare。建议 typed 条目显式分为“分析后返回”和“另获建线意图后 apply”，并注明 prepare 也写报告文件。
3. **完善只读前置信息。** inspect 没有可见层列表、深度关联字段，且只列前 250 个几何对象。场景 2 无法仅靠现有 inspect 确认 output_level 合法；场景 4 依赖 prepare 错误发现关联。建议后续提供这些只读信息；当前先文档化限制，不猜值。
4. **将 typed 条目链接到详细业务合同。** typed 条目本身多为通用步骤和 schema 指针；网格近似、weld<=mesh、关联限制在另一知识条目。增加明确的对应 workflow ID，可减少漏读。中文“复杂孔”只命中模块，skill 的 module/routes 回退有效，可再为工作流增加同义词。
5. **说明模型接受与业务通过的区别。** 两项公差关系未在 Pydantic 层校验。说明或补前端交叉约束，能更早反馈；当前不得将 schema 接受称为 prepare/native PASS。
6. **标明 stdio 回退应使用已安装依赖的解释器。** `ai/README.md` 已给独立环境安装步骤；skill 回退指引可直接强调使用该环境，避免默认 Python 的不兼容 MCP 版本。本评审未修复环境，也不推断其他环境失败。

这些建议未写回 skill、代码、目录或配置。本报告没有新增原生验收结论。

## 被评审快照

以下均为仓库相对路径；SHA256 对应本次读取版本。

| 路径 | SHA256 |
|---|---|
| `ai/skills/mastercam-plugin-suite/SKILL.md` | `90C4664A565E251C5761BF7D2DF0EED51AA1C29D6AFCCB5D01B97F20DCFA6139` |
| `ai/mcp/server.py` | `7CE4DD0C2310E64B57EA2DEAA0CEE277CC61DCE567263685E2779FDD3ABD2602` |
| `ai/mcp/models.py` | `FB7679A6F52A3958A068596D808B39ED1F0CB6CA57147CB476140CB1C570576C` |
| `ai/mcp/runtime.py` | `695E721D07A3C77C7FA8BE818ECEA690557DE5230C5EB0DC5CEA57152CB01253` |
| `ai/bridge/PluginBridge.cs` | `4BD1A55D97AA06384EEB99EDC5553FE4C5E481EA3E07343782319CD66E013172` |
| `ai/knowledge/machining.json` | `A954929F49817F5C68646D40A0DF69E60429205DC80DEC166AFAE16F5EF823D4` |
| `ai/knowledge/geometry.json` | `4250649A693E59E7E318389B6EA2CC04A6914550F8F01F78903CE717688578ED` |
