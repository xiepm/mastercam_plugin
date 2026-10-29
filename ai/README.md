# Mastercam 插件 AI 接入

这部分把插件的功能含义、输入要求、使用步骤与已验证接口整理成 AI 可检索、可执行的能力。

阅读功能用法可从 [加工与工序](knowledge/machining.md)、[几何与设计工具](knowledge/geometry.md) 开始；AI 查询使用 [结构化功能目录](catalog/capabilities.json)。

- **功能目录**：`catalog/capabilities.json`，覆盖发布包的 27 组模块及 CIMCO；含真实 FT 入口索引、前置条件、参数含义、副作用、回滚与验收边界。
- **Skill**：`skills/mastercam-plugin-suite`，指导 AI 选择功能、核对坐标/刀具/单位、读取预览及处理失败。
- **MCP**：`mcp/server.py`，11 个工具，6 类结构化写入动作；复用已经工作的 Mastercam MCP 进入宿主主线程。
- **原生适配层**：`bridge/bin`，仅引用安装的 API29 和已发布业务 DLL，不分发 Mastercam SDK，不修改现有业务 DLL。

目录中 `typed` 表示已有参数化 MCP，`interactive` 表示需通过界面完成，`reference` 表示功能知识/源 API 合同。`typed_candidate` 仅表示底层有可封装的接口。不要把这几种状态混为一谈。

## 当前可直接执行

| action | 功能 | 输入重点 |
|---|---|---|
| operation.depth | 工序深度修改 | 实际工序 ID、TPlane 深度、绝对/增量、是否允许解除关联 |
| operation.finish | 2D 粗转精 | 已有平底刀槽、刀径、补偿、进给模式与切削参数 |
| operation.chamfer | 2D 倒角 | 已有倒角刀槽、刀尖角、宽度、偏移和切削参数 |
| hsm.pocket | 三种原生挖槽策略 | 参考工序完整单闭合链、已有刀具、入刀/步距/高度/进给 |
| mp.sections | 截面与平行切片 | 实体 ID、世界坐标平面、公差、层数间距、已有输出层 |
| mp.draft | 网格拔模/分区边/法线 | 实体 ID、脱模向量、阈值、公差、输出项和层 |

保时捷复杂孔与副本补面、其他库/报表/原版 X+ 等功能有使用合同和入口索引，当前不因为存在 DLL 就宣称已有通用无界面自动调用。后续新增结构化动作应复用同一预览、回读和请求状态合同。

## 本机 Codex

前提：插件合集已安装，已有 `mastercam` MCP 能在 Mastercam 2027 中执行 `mastercam_run_script`。Mastercam 本体、Python、已有 bridge 不由这里重新安装。

使用 Python 3.11+ 独立环境：

```powershell
python -m venv .ai-venv
.\.ai-venv\Scripts\python.exe -m pip install -r ai\mcp\requirements.txt
.\.ai-venv\Scripts\python.exe ai\tools\local_setup.py --mastercam-root 'E:\CAM\Mastercam 2027' --workspace 'E:\MCPWorkspace' --register
.\.ai-venv\Scripts\python.exe ai\tools\install_skill.py --config 'E:\MCPWorkspace\plugin-ai-config.json'
```

`workspace` 必须在现有 Mastercam MCP 允许执行脚本的范围内，并放在本合集目录之外；其中的运行配置和 Codex 备份属于本机私有文件。相对路径会先转为绝对路径。`local_setup.py` 从当前 Codex 配置读取名为 `mastercam` 的 stdio 服务；其他名称使用 `--upstream-name`。它只添加 `mastercam-plugins`，不修改其他服务器、审批偏好、Mastercam 启动配置或旧插件。发现不一致的既有配置会停止。

重新加载 MCP 或重新打开 Codex 会话后，使用 `$mastercam-plugin-suite`。也可以在客户端刷新之前执行真实 stdio 测试：

```powershell
.\.ai-venv\Scripts\python.exe ai\tools\call.py list
.\.ai-venv\Scripts\python.exe ai\tools\call.py mc_catalog
.\.ai-venv\Scripts\python.exe ai\tools\call.py mc_inspect --config 'E:\MCPWorkspace\plugin-ai-config.json'
```

仅查询功能目录不需要 Mastercam、上游 bridge 或 runtime 配置。执行工具会校验安装 DLL 的固定哈希以及宿主已经加载的 MVID；不匹配时按提示安装匹配版本或正常重启。

## 其他 MCP 客户端

配置结构如下，具体字段外层按该客户端要求填写：

```json
{"mcpServers":{"mastercam-plugins":{"command":"E:/AI/.venv/Scripts/python.exe","args":["E:/mastercam_plugin/ai/mcp/server.py"],"env":{"PYTHONUTF8":"1","MC_PLUGIN_AI_CONFIG":"E:/MCPWorkspace/plugin-ai-config.json"}}}}
```

运行配置示例见 `config.example.json`，其中 upstream 是已工作的 Mastercam MCP stdio 启动命令。Skill 可复制到支持 `SKILL.md` 的客户端技能目录；其他客户端可把 Skill 和相关参考文件作为其项目说明。不要把本机绝对路径直接复制给其他电脑，也不要公开带凭据的本地运行配置。

## 执行与恢复

默认先预览具体变更，再按用户授权执行；如果用户已授权参数齐全时自动执行，Skill 不重复询问。MCP 的预览哈希只证明调用指向同一个计划，不代替人的授权。

预览不写入工序或结果几何，MP 会产生独立分析文件并临时选择实体后恢复。Apply 不自动保存、重算或后处理。HSM 重算另有专用工具。输出回读通过不等于碰撞检查或生产 NC 验收。

所有 native 请求按 workspace 串行，调用前不得另开并行宿主修改。请求日志在 `workspace/plugin-ai/<request_id>/`。超时意味着结果未知，先用 `mc_request_status` 查询，不重发。详细恢复条件见 Skill 的 `references/execution.md`。

## 验证与开发

```powershell
python -m unittest discover -s ai\tests -v
python ai\tools\generate_catalog.py
pwsh -NoProfile -File ai\tests\PreviewGuard.Tests.ps1
```

`ai/validation` 记录适配层测试；业务 DLL 既有验证位于仓库根目录 `validation`。两者分别记录。业务源码并未因此全部开源；本次新增的 MCP、适配层和 Skill 源码在 `ai/`。

本次适配层通过 22 项 Python 检查、5 项生产预览守卫回归检查、35 次原生调用及 6 次发现/计划生命周期调用；测试后原有对象与选择已核对恢复。独立评审的发现和处理见 [评审闭环](validation/review-resolution.md)。

需要重编译适配层时，使用带 Roslyn 的 PowerShell 7.6/.NET 10 运行 `ai/bridge/Build.ps1 -MastercamRoot <目录>`，然后重新生成 identity/catalog。不要替换正在宿主中加载的 DLL；正常退出宿主后再更新。新增动作必须补实际原生回读与清理证据，不能仅凭 JSON schema 声称已支持。
