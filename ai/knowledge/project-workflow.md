# 从三维工件到原生工程

本文件是 2026-11-01 可移植包的操作知识，不是任意 STEP 自动加工已验收的声明。

## 输入与来源

输入优先 STEP/STP 实体或已有 MCAM；三维截图不能代替精确拓扑。保留源文件摘要、单位、软件/插件版本，以及用户实际提供的工艺单。任务目录在仓库外，原件只复制。不要上传客户工件到本公开仓库。

已有制造语义通过 features.json 2.2 进入 P07。包内 CAPP 快照读取 manufacturing_context 并生成 cam_plan.json 1.1；它不运行 AAGNet。模型预测和 Agent 显式解释需要分别记录来源。原支座的 Face 组是该 STEP 的显式解释，不适用于新工件。

## 宿主、导入与保存

安装插件后运行 Install-AI.cmd，配置基础 mastercam 和 mastercam-plugins 两个 MCP、两个 Skill 及私有工作区。基础桥接调用 Mastercam 安装自带 IPCServer，不分发 SDK DLL。

要求一个 Mastercam 进程。无宿主时 mastercam_launch 可导入任务目录中的 STEP/MCAM；启动返回 ready=false，要等 mastercam_inspect 实际成功。已有工程时先保存，由 UI 打开测试副本，不能在 IPC 中串行调用 FileManager.New/Open 后假定完成。

SaveAs 后检查完整文件路径、文件大小、原生 CurrentFileName 以及工序回读。冷重开使用实际保存文件，记录新 PID、工序参数和刀路范围；旧截图不构成重开证明。

## 工序与装夹

首先 mc_inspect 获取 native operation ID、实体 ID、ViewID、刀具槽。树中的工序序号和显示刀号不是这些内部 ID。使用 mc_capability 选择当前 typed 动作；参考工序、几何、刀具和数值均来自本次任务。

准备预览后按用户已有授权 apply。Porsche 的 Regenerate 必须显式为 true；HSM 有独立重算工具。其他 apply 不代表重算、保存或后处理。保留原生 false 和 fresh Dirty；不能用旧对象缓存状态覆盖失败。

三轴两次装夹要求两个 setup 群组，各自 WCS/TPlane 和工作零点。在每次装夹局部坐标中加工方向面向刀具；翻面坐标变换、毛坯/余料传递和各装夹 NC 分开记录。把上下方向写进计划还不等于原生分组正确。

## 仿真、后处理与验收

材料仿真应绑定当前工序、刀柄/刀杆、毛坯、目标、容差和检查开关，并确认完整运动执行到末尾。Native Verify、CIMCO 刀位仿真、整机仿真、几何材料差和尺寸公差有不同边界。

P08 的 2027 Verify helper 是从既有实现导出的源码，通过本机 Framework 编译后连接原生仿真域；旧 2026 模板不能直接作为 2027 的已验收结果。包内原支座脚本仍有源文件哈希限制，不能改掉限制来“支持”新工件。

NC 应由绑定的原生后处理产生。若要工件局部 5 mm 起退刀，在实际装夹下配置并核验；它不是通用换刀位置。CIMCO 模型可在 M6 时添加 NC 字面中没有的动作，要分别检查显式指令和解释器行为。

每项结论附原生回执及依赖文件。task checkpoint 的 pass 需要文件，但这个条件本身不能证明文件内容正确。未测机床/夹具/尺寸项目仍是 pending/unknown，不把空报告自动视为通过。
