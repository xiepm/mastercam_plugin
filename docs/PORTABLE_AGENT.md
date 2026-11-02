# 把本机 Codex 的 Mastercam 工程能力迁移到另一台电脑

原生载荷基线：2027.11.01.2。2026-11-02新增的规划扩展以源码提交标识，详见[规划安装、知识库迁移与重放](PLANNING_WORKFLOW.md)；旧版本ZIP不含该扩展。目标是让新电脑获得同一套工具、操作知识和上下文恢复入口，不承诺相同的通用成功率。

## 用户指定的六项

| 编号 | 组件 | 本包内容与加载方式 |
|---|---|---|
| 2 | Prompt | ai/prompts/mastercam-engineer.md 与用户任务模板；由 mastercam-project Skill 明确读取，不修改用户全局系统提示词 |
| 4 | Skill | mastercam-project 管理工程全流程，mastercam-plugin-suite 管理参数化动作；安装到目标 Codex 的 skills |
| 5 | MCP | 自包含的基础 mastercam 桥接及现有 mastercam-plugins；安装器注册两项，不再依赖作者电脑的外部目录 |
| 6 | Tools | 安装、doctor、静态编译、CAPP 规划、P08 来源快照、真实 stdio 调用、原生创建与重开测试 |
| 8 | Knowledge | 有来源的加工工作流、装夹/起退刀/仿真问题经验及插件合同；mc_knowledge_search/read 按需读取，不要求向量数据库 |
| 13 | Context | 输入副本、要求、计划和资源摘要、逐阶段证据及下一步；mc_task_create/checkpoint/resume 跨新会话恢复 |

## 新电脑安装

1. 安装并正常启动过 Mastercam 2027，确认合法可用的软件环境；安装 Windows x64 Python 3.11 或以上。插件依赖对应 API29/.NET 10，部分功能绑定具体原生构建。
2. 下载本仓库源码 ZIP 或 clone。先关闭 Mastercam，运行 **Install.cmd** 安装匹配插件；该入口按既有安装流程处理 CIMCO Verify。CIMCO Edit 独立编辑器仍是外部组件。
3. 在同一解压目录运行 **Install-AI.cmd**。它建立.ai-venv及独立规划环境、安装锁定依赖、选择Mastercam目录、生成私有工作区、注册两个MCP并安装三个Skill。规划参考需另外配置有权限使用的知识库。缺少Python或冲突配置会明确停止，不静默覆盖已有桥接。
4. 重启 Mastercam，使安装后的启动器按当前用户启用 IPCServer。重载 Codex MCP 或打开新会话，检查工具已出现。
5. 用 doctor --native 实际调用宿主，再运行下文独立测试。安装成功或 mc_catalog 成功都不等于加工工程验收成功。

显式路径示例（按新电脑实际位置修改）：

```powershell
.\Install-AI.ps1 -MastercamRoot 'E:\CAM\Mastercam 2027' -Workspace 'E:\MastercamAgent\workspace'
.\.ai-venv\Scripts\python.exe ai\tools\doctor.py --config 'E:\MastercamAgent\workspace\plugin-ai-config.json' --native --output 'E:\MastercamAgent\workspace\doctor.json'
```

默认工作区位于当前用户 LocalAppData/MastercamAgent/workspace，默认客户端使用 CODEX_HOME 或用户 .codex。工作区必须位于仓库之外。不要把生成的 config.toml 备份、connection.json、任务、账号或客户工件上传。

原生插件由 Install.cmd 管理，AI 注册由 Install-AI 管理；安装后不移动/删除解压目录，因为 MCP 引用这里的代码和 .ai-venv。迁移目录需要核对旧注册后重新安装，不把旧绝对路径机械复制到另一台电脑。

## 给新会话的第一句话

```text
使用 $mastercam-project。
输入 E:\parts\part.step，生成独立的 Mastercam 2027 加工工程。
这是三轴加工；工艺与资源资料在 E:\parts\requirements。
需要生成刀路、保存重开并做材料去除和刀柄碰撞检查。
请按实际能力执行，保留原件，把每阶段证据与待解决项写入任务上下文。
```

新会话继续：`使用 $mastercam-project，恢复任务 part-001，先核对当前证据，再继续未完成步骤。`

仅给 STEP 不一定足够确定材料、装夹、图纸公差和切削参数。已知资料直接读取；缺失且会影响结果的信息才需要补充。软件试验可以按明确授权使用虚拟资源，仍需标注来源。

## 在新电脑重放与验收

现有支座的 STEP → 两装夹九工序 → 完整 Verify → 过切/刀柄检查 → 两次冷重开，使用 [专用重放说明](STEP_REPLAY.md)。这包含额外的锁定 P01 环境、原生页签名称提交和独立验收记录。下面的 contour cycle 仍是较小的连接/持久性冒烟测试。

先关闭自己正在编辑的 Mastercam 文档并正常退出。以下 cycle 只在没有现有宿主时创建自己的测试进程，然后生成新的矩形轮廓原生工程、计算刀路、保存、正常关闭所拥有的宿主、启动新进程重开并核验。原生检查可能使会话变为“已修改”；验证后将会话另存 inspection-session.mcam，再正常退出，原验收文件 contour.mcam 的哈希不变。测试进程由独立运行器持有，失败时保留窗口，不随一次性 MCP 客户端退出而被杀死。

```powershell
.\.ai-venv\Scripts\python.exe ai\tools\native_smoke.py cycle --config 'E:\MastercamAgent\workspace\plugin-ai-config.json' --directory 'E:\MastercamAgent\workspace\acceptance\first-run'
```

输出包括 create.json、reopen.json、contour.mcam、verification.json。目录不能重复使用。这验证基础原生工程和刀路持久性，不宣称材料仿真、过切、刀柄/整机碰撞、NC 或任意 STEP 已通过。

进一步任务需要分别保留各次装夹/毛坯、刀具、完整材料仿真、碰撞开关和报告、后处理版本及 CIMCO 解释配置。用另一台物理电脑重复测试后，记录 OS、软件/API、包版本、输入摘要、每阶段结果和人工介入次数。未知结果必须保留，不能统计为通过。

## CAPP 与既有工作的复用

提供明确 features.json 与 manufacturing_context.json 时：

```powershell
.\.ai-venv\Scripts\python.exe ai\tools\capp_plan.py --features 'E:\MastercamAgent\workspace\tasks\part-001\features.json' --context 'E:\MastercamAgent\workspace\tasks\part-001\manufacturing_context.json' --output 'E:\MastercamAgent\workspace\tasks\part-001\cam_plan.json'
```

这调用原有 P07，不是重新实现的规划器。生成计划之后还要核对原生能力/绑定。P01 的可选几何路线需要匹配的 OCCT/occwl 环境；基础安装不带它。AAGNet、P09/P10/P12 权重没有参与原支座闭环，本包也不携带它们。

原支座九工序的来源绑定脚本与后续修正工具作为有界复现资料保留，客户工件与原厂后处理不公开；必须匹配原输入，不能改掉来源校验用于新工件。新工件由实际几何查询、明确工艺需求和已支持插件能力处理。

## 恢复与升级

传输路径必须是 ASCII、无空格，或者能取得这样的 Windows 短路径；环境检查会提前报告。原 CAD 可以使用中文名，进入任务目录后保存副本。API29 管道按 5 字节整块接收，本包已补齐消息尾部，避免换目录后脚本挂起；对应原生 IPC 构建也纳入校验。

- typed 请求超时查询 mc_request_status；基础脚本超时查询 mastercam_request_status。未知请求不得再次提交。私有 mastercam/active.json 会阻止新的原生写入。核对宿主和回执、正常退出宿主后，可执行 `ai/tools/recover_request.py --config <配置> --request-id <原请求ID> --reason <核对说明>`。任何 Mastercam 进程仍在运行时工具均拒绝；恢复记录仍为 unknown。
- MCP 注册冲突或 Skill 被用户改过时安装器拒绝覆盖；先检查差异。与本包无关的模型设置、MCP 和审批选项保持原样。
- 关闭 IPC 自动启动可以把本机 LocalAppData/MC2027PluginSuite/agent-enabled.json 中 enabled 设为 false；这是运行配置，不在公开包内。重启宿主后生效。
- 历史工件/仿真回执的路径和摘要不改写为新电脑证据。历史单轮廓结果见 ai/validation/portable-acceptance.json，九工序结果见 ai/validation/stand-replay-acceptance.json，跨电脑状态单独登记。
