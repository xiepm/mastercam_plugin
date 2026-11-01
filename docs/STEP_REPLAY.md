# STEP → 两装夹九工序 → 原生仿真 → 冷重开验收

这是既有支座工件的**来源绑定重放**。输入必须匹配 SHA-256
`68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429`。
客户 STEP 不放在公开仓库；由工件持有者私下提供给获授权的接收者。
程序拒绝不同哈希的工件，不可删除校验以“支持”新零件。

复用链路：P01 OCCT/occwl 精确解析 → 有来源的特征及制造上下文 → P07 CAPP
`cam_plan.json 1.1` → P08 原生工序模板和装夹修正 → Mastercam Verify → P01 余料比较。
特征语义由 Agent 在这个确定工件上建立，未调用 AAGNet/P09/P10/P12；没有第二套 IR 或几何解析器。

## 目标电脑准备

1. 按 [可移植安装](PORTABLE_AGENT.md) 安装 Mastercam 2027 插件、两个 MCP 和 Skill。
   使用授权可用的 Mastercam 2027 / API29，确认原生 IPC 启动及静态编译检查通过。
2. 本轮锁定的 P01 环境是 **WSL2 / Ubuntu 22.04 / Linux x86_64**。
   安装好该发行版及 micromamba；安装器不会自动改变 Windows 功能或重启电脑。
   micromamba 的官方说明：[安装文档](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)。
3. 在 WSL 中运行包内安装器（仓库路径按实际修改）：

```bash
python3 '/mnt/e/mastercam_plugin/ai/tools/install_p01.py' \
  --prefix /home/operator/.local/share/mastercam-agent/p01-occt751 \
  --micromamba /home/operator/.local/bin/micromamba
```

安装器使用 163 个精确 URL/版本/构建/哈希锁定的 conda 包和带哈希的 manifold3d wheel，
安装到新目录并检查回读。P01 为 Python 3.9.18、OCCT 7.5.1、occwl 2.0.2、manifold3d 3.5.4。
该环境仅做无界面的几何计算，不安装神经网络权重；occwl 的 notebook/viewer 可选依赖不作为本入口需求。
已有目录不会被覆盖。保留 `<prefix>/mastercam-p01-install.json`。

## 从新的独立目录执行

先保存并退出正在编辑的 Mastercam。运行器只启动和关闭自己拥有的进程；
已有宿主时停止，不会挤占当前文档。使用 ASCII、无空格的私有工作区最稳妥；源文件可以有中文路径。

```powershell
.\.ai-venv\Scripts\python.exe ai\tools\replay_stand.py build `
  --source 'E:\私有工件\stand.step' `
  --directory 'E:\MC-Validation\tasks\stand-first\replay' --task-id stand-first `
  --config 'E:\MC-Validation\plugin-ai-config.json' `
  --machine 'C:\Users\Public\Documents\Shared Mastercam 2027\CNC_Machines\MILL 3 - AXIS VMC MM.mcam-mmd' `
  --wsl-distro Ubuntu-22.04 `
  --p01-python /home/operator/.local/share/mastercam-agent/p01-occt751/bin/python
```

新目录必须位于该 MCP 配置允许的 workspace 下。不要把另一台电脑的绝对路径、
config.toml 或历史回执直接复制为本机配置/证据。

**build 返回 20 是预期的界面提交节点，不是验收通过或错误重试信号。**
Mastercam 2027 的 ViewSheets API 能回读临时名称，但本轮实测保存重开会丢失名称。
Codex 用其电脑控制工具完成以下原生界面步骤（须有已解锁的交互桌面）：

1. 核对标题为本次目录中的 `stand-3axis-2setups.mcam`；底部应只有两个装夹视图页。
2. 分别右击两个页签，选择“重命名”，输入 `装夹1_正面_G54`、`装夹2_翻面_G55`，每次按 Enter。
   即使 MCP 内存回读已显示这两个名称，也要完成原生 UI 提交。
3. 读取新界面确认两标签。不要按 Ctrl+S：STEP 导入会话可能弹出异步“另存为”窗口；
   下一步由 MCP 原生保存到已绑定的 MCAM。使用实际截图/控件定位，不复制屏幕坐标。
4. 继续验证，不重新运行 build：

```powershell
.\.ai-venv\Scripts\python.exe ai\tools\replay_stand.py verify `
  --directory 'E:\MC-Validation\tasks\stand-first\replay' `
  --config 'E:\MC-Validation\plugin-ai-config.json'
```

verify 使用 prepared/request 中保存的源环境和宿主 PID，通过原生 API 保存名称，
并检查界面提交前后制造参数未改变。
这一步只允许提交视图名称，不能顺便更改刀具、工序、坐标或毛坯。
实际的名称持久性仍由后续冷重开检查决定。没有电脑控制能力的客户端须由操作者完成上述两次命名，不能宣称纯命令行全自动。
指定 task-id 时，程序复用现有 Context 记账；新会话通过 `mc_task_resume` 恢复任务。

运行器依次完成：

1. 复制 STEP，验证来源哈希；P01 解析 1 个实体、37 个面，保留毫米单位、面命名空间、精确体积和目标网格。
2. 生成特征/制造上下文并调用 P07，保留两装夹九道工序的原计划及来源绑定。
3. 通过真实 MCP 在 Mastercam 导入 STEP、保存 source.mcam，再创建轮廓、钻孔、沉孔和倒角工序。
4. 使用原有 P08 修正为独立群组、G54/G55 和对齐的 WCS/TPlane/CPlane：正面 3 道，翻面 6 道。
   两个装夹局部顶面均为 Z0，刀轴为局部 +Z，起退刀高度 5 mm，进给平面 2 mm。
   原 P07 计划保留；坐标/高度映射由 setup-apply 和 clearance-apply 回执明确记录。
5. 保存 `stand-3axis-2setups.mcam`，回读实际参数，完整执行 9 道工序/233 个运动段的原生 Verify。
   固定约 0.005 mm 分辨率；启用刀柄、刀杆、刀肩对毛坯检查以及运动段之间检查；
   目标偏差阈值 ±0.02 mm，刀柄碰撞容差 0.02 mm。
6. 正常关闭所拥有的 Mastercam，启动新进程重开同一个 MCAM，再从初始毛坯完整重算。
   连续进行两次冷重开；每次重新应用有哈希绑定的目标及仿真配置。
7. 比较工序、刀具组件、装夹、视图和原位点；三个不同 PID 的最终 IPW 必须字节一致。
   使用共享 P01 再作封闭网格体积差比较；通过后才写 `acceptance.json`。

Verify 可能修改当前会话的显示平面。清理时另存 `*-inspection-session.mcam` 再退出，
不覆盖已核验的交付 MCAM。不要把 inspection-session 当成交付文件。

## 验收证据与失败处理

| 文件 | 说明 |
|---|---|
| cad-summary / features / manufacturing_context / cam_plan / trial-binding | STEP、拓扑、工艺、资源与来源 |
| generated-native / setup-apply / clearance-apply | 原生生成与显式装夹、高度修正 |
| initial / cold1 / cold2 的 readback.json | 不同进程读取同一交付工程的参数 |
| 同前缀 export.json / ipw.stl / material.json | 已完成的原生检查、余料及独立几何比较 |
| cold1 / cold2-equivalence.json | 重开前后余料体积差 |
| acceptance.json | 输入、源码、MCAM、IPW 哈希与证据清单 |
| failure.json | 失败阶段、异常及“禁止自动重试”状态 |

超时不等于失败或成功。先看原生 request/dispatch/receipt 和当前宿主；不要重新提交未知写操作。
既有目录不允许从头重跑。修复问题后用新的目录重放，保留失败记录。
仿真耗时会变化；等当前请求的结果，不并行操纵活动文档。

这里验证的是**软件材料去除与刀具组件对毛坯检查**，不等于 T7/新代实机运动学、
实际夹具碰撞、图纸尺寸或生产 NC 放行。平面网格体积差也不替代精确 STEP 尺寸验收。
设置/目标通过旁文件重放，不能声称它们全部嵌入 MCAM。
另一台物理电脑需自行生成新报告；本机新环境通过不等于异机已经通过。

## 给另一台电脑的 Codex

```text
使用 $mastercam-project，按 docs/STEP_REPLAY.md 重放给定私有 STEP。
先检查当前软件、MCP 和 P01 环境，不重装已经合格的环境。
使用新的私有工作目录，完成两装夹九工序、完整材料仿真、过切和刀柄检查、两次冷重开。
读取 acceptance.json 及原生证据后交付 MCAM；失败保留回执并查原因，不删除来源校验或改写旧回执。
```
