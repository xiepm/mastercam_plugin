# STEP与二维图纸 → 历史经验检索 → 规划审查

本次新增可安装、可迁移、可重放的规划前置流程。Skill指导Codex读取输入，原P07代码负责自动检索及来源/覆盖审查。它不新建CAM执行器，不把规划审查当作刀路、仿真或生产通过；生成Mastercam工程仍继续既有P07/P08流程。

## 新电脑安装

需要Python 3.11+。下载包含本文件的源码版本，固定解压位置。旧`v2027.11.01.2`发布ZIP不含本次功能；PR合入前使用`codex/planning-reference-workflow`分支。首次依赖安装需要联网。

```powershell
git clone --branch codex/planning-reference-workflow https://github.com/xiepm/mastercam_plugin.git
cd mastercam_plugin
.\Install-Planning.ps1 -Workspace 'E:\Private\MastercamAgent'
```

安装器创建`.planning-venv`，将`aicnc-plan-new-part`安装到当前Codex Home；可用`-CodexHome`指定其他配置或隔离验收。不要求Mastercam启动，不修改其他MCP注册。未提供知识库时配置为null，真实规划明确报未配置，不用演示库顶替。

要生成MC工程，另按[完整安装说明](PORTABLE_AGENT.md)安装插件，然后运行`Install-AI.ps1`。它现在也调用规划安装器，支持`-KnowledgeRoot`、`-P01Python`与`-P01Distro`。已知未修改的旧Skill先备份后迁移；自定义Skill保留。备份在workspace。旧native配置若指向不同安装位置，仍按原安装器提示迁移。

## 私有知识库配置与迁移

公开仓库只有代码、Schema和合成验收件，**不含工厂真实STEP、MCAM、图纸及案例证据**。同一历史经验库需要单独传送有权限使用的私有包；只复制模板JSON而遗漏冻结证据不能通过校验。

源电脑导出（替换为实际路径）：

```powershell
.\.planning-venv\Scripts\python.exe ai/tools/knowledge_bundle.py export `
  --knowledge-root 'E:\Private\ProcessReferences' `
  --output 'E:\Transfer\private-reference.zip'
```

先校验catalog、合并决策、library与证据，再生成ZIP、逐文件摘要清单及`.zip.sha256`。只有本地操作，没有上传。通过双方获准的私有渠道传送，不能放进公开GitHub。

新电脑导入到不存在的新目录，再配置：

```powershell
$digest=(Get-Content -LiteralPath 'E:\Transfer\private-reference.zip.sha256' -Raw).Trim()
.\.planning-venv\Scripts\python.exe ai/tools/knowledge_bundle.py import `
  --archive 'E:\Transfer\private-reference.zip' `
  --destination 'E:\Private\ProcessReferences' --sha256 $digest
.\Install-Planning.ps1 -Workspace 'E:\Private\MastercamAgent' `
  -KnowledgeRoot 'E:\Private\ProcessReferences'
.\.planning-venv\Scripts\python.exe ai/tools/planning.py doctor `
  --config 'E:\Private\MastercamAgent\planning-config.json'
```

导入拒绝摘要不符、路径越界、重复文件和已有目标。配置遵守[Schema](../ai/schemas/planning-config.schema.json)，[示例](../ai/planning-config.example.json)只说明结构。移动仓库、更换Python或知识库后重跑安装器，它更新本机connection并备份旧规划配置。

## STEP几何读取

此安装器不携带OCCT、AAGNet权重或CAD商业授权。STEP必须通过真实几何后端解释：使用已验证的Mastercam原生几何工具，或安装[已有P01环境](STEP_REPLAY.md)。P01安装器为`ai/tools/install_p01.py`，在WSL/Linux执行，先查看其`--help`和环境前提。

P01安装示例（WSL）：`python3 ai/tools/install_p01.py --prefix "$HOME/.local/share/mastercam-agent/p01-occt751"`。然后Windows规划安装器指定`-P01Distro 'Ubuntu-22.04' -P01Python '/home/你的用户/.local/share/mastercam-agent/p01-occt751/bin/python'`。P01输出cad_core、Face边界与版本来源；它不等于运行了AAGNet或确认全部制造语义。没有可用几何后端时必须报告缺口。

## 日常调用

安装后让Codex重新发现Skill，必要时新开会话。通常直接说：

> STEP在`E:\Parts\part.step`，二维图纸在`E:\Parts\drawing.pdf`。请规划加工，参考历史模板并记录采用理由，不需要仿真。

也可要求“生成Mastercam工程”，规划后继续既有执行流程。可选显式提示`$aicnc-plan-new-part`。普通语言触发由Codex的Skill选择负责，并非后台自动钩子；如果未触发就显式调用。不能保证模型在所有会话中都自动选对Skill。

Skill读取本机connection，使用其中的Python运行仓库`ai/tools/planning.py`：

```text
planning.py start --config <配置> --task-id <唯一ID> --step <STEP> --drawing <二维图>
planning.py geometry --config <配置> --task <任务>   # 配置P01时
planning.py prepare --config <配置> --intake <任务>/intake.json --run-dir <任务>/reference_run
planning.py audit --config <配置> --run-dir <任务>/reference_run --review <任务>/review.json --output <任务>/audit.json
```

所有任务输出在私有workspace。start复制输入、记录哈希；PDF提取文字及最多16页预览，余下页数明确标记。Codex仍需实际读图、解释几何；DWG/DXF需要可读工具。intake由Codex从这些证据形成，文件路径本身不等于工艺需求。

## 合同与审查含义

沿用原P07 [Schema](../ai/aicnc/schemas/planning_reference_workflow.schema.json)及[示例](../ai/aicnc/schemas/examples/planning_reference_intake.example.json)。

| 文件 | 内容 |
|---|---|
| intake.json | 输入来源、材料、逐条需求ID/描述/标签/来源定位、未知项 |
| reference_run/packet.json | 自动用需求标签检索，排除同STEP自身案例，最多6个经验族及全部命中冲突/缺项，冻结证据摘要 |
| review.json | 每条需求和检索项的决定、理由、模板ID、本件证据及规划段落 |
| audit.json | 来源完整性、检索重放、引用和声明覆盖、未决项；不提供CAM/生产通过 |

`reference_context.md`是按需给模型读取的上下文。因此经验会进入本次推理，不塞进永久系统Prompt、不修改权重。Skill提供流程，JSON保存知识/决策，Markdown便于人审。检索目前是可复核的标签/文本匹配，不使用向量库。

规划使用`## P01 标题`等稳定段落，正文列需求ID及采用的`family:<ID>`。review中：需求状态addressed/deferred/not_applicable；经验族adopt/adapt/reject/defer；冲突和缺项resolved/not_applicable/unresolved。采用经验要提供实际selected_source_ids，不可照搬历史数值。resolved仅指本件规划中处理了提醒，不代表历史冲突消失或加工验证通过。新发现与原始未知项继续保留。

审查失败退出码2，记录完整退出码0；complete_with_open_items也退出0，调用方必须读status及open_items。审查不能证明工艺语义正确，也不能识别尚未录入intake的全部漏项，更不替代材料去除、过切、刀柄碰撞或保存重开实测。

## 重放验收

不需要Mastercam或真实工厂资料，使用公开合成板件（30×20×5、两个直径4通孔）：

```powershell
.\.planning-venv\Scripts\python.exe ai/tools/accept_planning.py `
  --output 'E:\Private\Acceptance\planning-001'
```

每次用新目录。脚本安装到隔离Codex Home，不覆盖日常配置，输出acceptance.json。正例必须引用模板；三个反例必须拒绝：漏审冲突、规划未声明需求、冻结证据被修改。正例保留完整，反例单独记录。

此脚本重放预写的合成规划，不会启动另一个模型，因此不证明新电脑Codex自主选Skill/规划质量。真正跨电脑验收还需以普通提示词跑未见新件，记录模型、Skill触发、几何来源、输入/知识库摘要、引用及未决项。已有真实件可以复制授权任务资料，重新prepare、更新review.packet_sha256、再audit；这属于规划重放，不是独立重新推理。

GitHub Actions在Windows/Ubuntu运行规划测试与合成重放。本机记录见[PLANNING_ACCEPTANCE.md](PLANNING_ACCEPTANCE.md)。原有工程/仿真验收仍见[STEP_REPLAY.md](STEP_REPLAY.md)。
