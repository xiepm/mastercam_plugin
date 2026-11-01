# AI-CNC 来源快照与适用范围

本目录是原 AI-CNC P01/P07/P08 的选择性源码导出，不是新建解析器、制造 IR 或另一套执行器。source-manifest.json 对每个文件记录源内容 SHA-256、发布内容 SHA-256 和必要的路径适配。上游工作区含未提交文件，因此 upstream_base_commit 不能单独代表这里的源码。

- P01：共享 STEP/Face、几何与材料计算的依赖闭包。可选使用，需要与来源匹配的 pythonocc/occwl 环境；本包的 Windows 基础安装不自动安装 OCCT，也不声称已验证新的 Face 编号兼容性。
- P07：已有 features.json 2.2 + manufacturing_context → cam_plan.json 1.1 规划器。通过 `ai/tools/capp_plan.py` 使用；依赖已由 Install-AI 安装，不需要模型权重。
- P08：原生有界模板、2027 仿真跨域 helper、后处理修正与核验脚本。既有 stand profile 锁定原 STEP 哈希；原件未公开分发。不能删除哈希校验，把它当成任意 STEP 自动编程器。
- 原有 2026 的 single/multi 仿真执行路径仍属历史模板，未随本包自动晋级 2027。2027 支座路径的可移植适配只替换运行目录、MCP 配置和静态编译位置，不重写制造计划。

修改这些源文件时，应在所属 P01/P07/P08 上游评审，再使用 `tools/Import-AICNC.py --source <上游工作区>` 生成受控快照。原回执不能改路径后当成新电脑验收。发布适配需要重新测试，source-manifest 的 adaptations 明确列出变化。

全新的 STEP 通常从 Mastercam 原生实体检查和已支持插件动作开始，或由兼容 P01/模型路线提供明确 features；详见 mastercam-project Skill。包不含 AAGNet 权重、客户 STEP/MCAM、机床后处理正文、厂商 SDK 或许可证。

来源绑定支座的可重放入口、P01 环境安装与原生 UI 边界见 [STEP_REPLAY](../../docs/STEP_REPLAY.md)。P08 新增 stand_replay 校验与静默保存辅助，继续使用同一原生执行器和 P01/P07；模型推理没有参与该用例。
