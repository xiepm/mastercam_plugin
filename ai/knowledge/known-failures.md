# 已验证问题与处理条件

这些记录提炼自本机原生试验，保留适用边界；不能视为所有零件的默认参数。

## 换目录后 IPC 连接成功但脚本一直不返回

本次定位的 API29 IPC 接收器每次 ReadExactlyAsync 读取 5 字节，然后对整条命令 Trim。旧路径恰好构成整块，其他长度会等待最后几个字节。可移植客户端把单条 ASCII 管道消息用空格补齐至 5 字节倍数，不修改厂商 DLL。传输脚本路径含中文或空格时先尝试 Windows 短路径；不可用则要求选择 ASCII、无空格工作区。任务导入的原 CAD 文件仍可使用中文名。

| 症状 | 证据与原因 | 处理与核验 |
|---|---|---|
| 目录工具可用，执行提示缺 upstream | 旧包依赖本机外部 mastercam MCP | 运行 Install-AI，doctor 核对两个 MCP；目录可用不算连接成功 |
| IPC 管道未就绪 | Mastercam.exe 已启动，IPCServer 尚未创建 MastercamPipe<PID> | 等就绪并只读 inspect；确认启用 IPC 启动标记。不要重复提交写操作 |
| Invocation 异常 | .NET 外层异常不能说明内部原因 | 保存完整 InnerException 和原生回执；检查 API29、DLL 哈希/MVID、实际对象，禁止把外层消息当成功 |
| 2027 脚本不能加载 System.Web.Extensions | NET-Script 进入 .NET 10，而 Verify 留在 Framework 域 | 使用实际验证的 2027 模板/跨域 helper，静态编译后再执行；不复制厂商 SDK |
| SaveAs 后重开缺文件或脏工序 | 原生路径/工具 FileName/缓存状态有区别 | 用完整路径；工具名称不要写入几何 FileName；保存后读 fresh operation/data |
| 重开检查完成但退出又询问保存 | 读取或加载插件后，当前会话可能标记已修改 | 将检查会话另存新副本后正常退出；验收工程仍保持原哈希，不强制杀掉宿主 |
| 翻面仍显示同一个俯视图 | 计划方向不等于独立 native WCS/群组 | 每次装夹设独立群组和 ViewID，Commit/Retrieve 检查矩阵、原点、刀轴和深度 |
| 孔圆链位置偏移 | 底面圆弧中心使用视图局部坐标，直线端点使用世界坐标 | 明确 API 坐标合同；创建前清理旧选择，创建后回读原生链 |
| 刀柄或刀具停在工件几百毫米外 | 原位点、机床换刀、长度补偿和工件零点可能共同作用 | 读回实际 return point；分别检查 NC 首定位、H/G43 与 CIMCO 机床模型，不仅搜索 Z 最大值 |
| NC 无 Z236，CIMCO 仍走长行程 | 原试验默认 Haas 模型会在 M6 隐式定位 | 用户要求相对刀路时采用对应解释模式；这不等于实机换刀已校验，保留 M6/H 等语义 |
| 重开余料轻微变化 | 仿真精度自适应、换刀覆盖容差或材料状态继承不同 | 绑定分辨率和检查设置，从同一毛坯完整计算后再比较；不能修改网格来消差 |
| IPC/API 返回但没有 NC | 后处理调用未完成或者选择树状态不同 | 检查原生导出文件、实际工序覆盖和输出选项；未生成文件不能报成功 |
| 超时后再执行生成重复工序 | 原生请求可能仍在运行 | 先查询 mc_request_status 或 mastercam_request_status，保留 unknown；核对宿主和回执后恢复 |

来源：包内 ai/aicnc/source-manifest.json 对应的 P08 源码与脱敏的 reproduction-notes.md；插件动作更细条件见各 mc_capability。原支座经过人工纠正和多轮开发，不计作首次全自动成功。
