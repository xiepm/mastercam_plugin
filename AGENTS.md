# Mastercam 可移植 Agent 包

新STEP与二维图纸先用`ai/skills/aicnc-plan-new-part/SKILL.md`，通过本机planning connection读取输入、规划前检索历史经验、规划后审查引用/冲突/缺项，见`docs/PLANNING_WORKFLOW.md`。真实知识库缺失时不能静默用公开合成库代替。私有知识包和任务回执留在仓库外。此流程是既有P07/P08的规划前置阶段，不新建IR或CAM执行器。

本仓库统一分发插件与 Agent 所需的 Prompt、Skill、MCP、Tools、Knowledge、Context。

处理加工工程请求先使用 ai/skills/mastercam-project/SKILL.md；插件动作的具体合同由 ai/skills/mastercam-plugin-suite/SKILL.md 和 mc_capability 提供。提示词见 ai/prompts/mastercam-engineer.md。运行配置与任务数据位于仓库外，由安装器生成，不能复制作者电脑的路径配置。

复用 ai/aicnc 的来源快照和现有制造合同。修改 P01/P07/P08 算法应回到上游所属项目评审，不另外编写平行解析器或执行器。源快照更新必须同步内容摘要和适配说明。

新增行为需要对应离线或真实原生验证；分别报告目录查询、连接、工序、刀路、重开、材料、碰撞与生产结论。客户工件、许可证、账号配置、运行日志和任务上下文不进入公开仓库。原版第三方载荷保持已有来源与文件摘要。
