# Mastercam 2027 插件工具箱

面向 **Windows x64 · Mastercam 2027 / API29** 的联网一键安装合集。一个 ZIP 包含 27 组插件/资源，包括重建工具与 15 个原版 X+ 入口；缺少 CIMCO Verify 时自动从官方服务器下载并安装，已有匹配安装则跳过。

**[下载最新版安装包](https://github.com/xiepm/mastercam_plugin/releases/latest)** · [全部插件目录](docs/PLUGINS.md) · [安装说明](docs/INSTALL.md) · [兼容性与已知范围](docs/COMPATIBILITY.md)

**AI 使用与调用**：[Skill + MCP 接入说明](ai/README.md)。功能目录覆盖 27 组模块及 CIMCO，包含 170 个实际 FT 入口；11 个 MCP 工具提供检索、检查、6 类参数化变更、回读、回滚与超时状态查询。需要现有可工作的 Mastercam MCP bridge；交互功能与未封装 API 会明确标记。

## 下载与安装

1. 在 Releases 下载 **`Mastercam2027-PluginSuite-AI-2027.10.29.1.zip`**，完整解压到一个文件夹。该包包含原有插件载荷与新增 AI 接入文件。
2. 确认 Mastercam 2027 已启动过一次，然后正常关闭 Mastercam。
3. 双击 **`Install.cmd`**。自动查找安装目录；若未找到，输入包含 `Mastercam.exe` 的目录。按 Windows 提示允许写入安装目录。
4. 重启 Mastercam，查看 **小蜜蜂、工艺助手、X+ 工具、X+ 原版、HSM 加工、MP 设计工具** 页签。CIMCO 首次安装需要联网下载约 43 MB；已有完整匹配安装时无需下载或重装。

**保时捷／V++ 的入口位于「工艺助手 → 保时捷 / V++」**，包含实体自动轮廓、自动删孔补面、复杂孔自动工序。

安装器使用 Windows 自带 PowerShell 5.1，也支持 PowerShell 7。无需另外安装开发工具、REA 或 IPC 服务。插件运行需要 Mastercam 2027 的 API29 与 .NET 10 Windows Desktop 运行环境。

## 包含哪些工具

| 分类 | 主要功能 |
|---|---|
| 保时捷／V++ | 实体投影轮廓；粗轮廓、精光、倒角三工序；副本删孔补面；复杂孔识别后按阶段建工序 |
| 小蜜蜂 | 刀路参数、刀具、图形、共同参数、复制粘贴、群组与 NC 名称、导入导出、模板入口 |
| 工序与钻孔 | 粗转精、倒角、深度、替换串连、工序信息、装刀长度下界、分阶段钻孔与明确规格攻牙 |
| X+ 工具 | 串连、分度平面、SVG 导入、草绘刀路、刀柄截面、程序单、电极几何报表、STL 导出、白底截图 |
| X+ 原版 | 15 个 API29 原版入口及其资源，文件保持原样；旧 API28 Ribbon 不装入 |
| HSM 加工 | 新建原生 HighSpeed 摆线挖槽、恒定重叠螺旋、TrueSpiral；参数回读、计算、回滚 |
| MP 设计工具 | 原有曲面/实体辅助；新增任意平面截面、平行切片、网格拔模角分析、分区交界边及法线箭头 |
| CIMCO Verify | 自动检测、官方安装器下载、SHA-256/签名校验、2027 组件安装 |
| 辅助 | 几何与坐标、夹具、矩形毛坯、三面检查、正交视图、中键确认 |

详见 [全部模块及其功能范围](docs/PLUGINS.md) 和 [HSM / MP 新增功能](docs/HSM-MP.md)。HSM 与 MP 为独立重构的功能子集，尚不包含原版全部高级功能。

## 原版插件与模板

CIMCO 的官方安装器由 `Install.cmd` 按需下载，仓库不携带该安装器、许可证或 Mastercam SDK DLL。HSM/MP 重构 DLL 与原版 X+ 已直接包含在 ZIP 内。原厂完整 HSM / Moldplus、CIMCO Edit 独立编辑器和旧刀路模板的处理见 [外部组件目录](docs/EXTERNAL.md)。

本仓库分发的重建模块没有新增激活、试用或用途限制界面；Mastercam 与外部组件按各自产品要求安装。

## 校验、升级与卸载

- **校验**：双击 `Verify.cmd`，检查下载文件和已安装文件的 SHA-256。
- **升级**：退出 Mastercam，解压新发布包，再运行 `Install.cmd`。最初的原文件备份会保留。
- **卸载**：退出 Mastercam，运行 `Uninstall.cmd`。仅恢复本套件接管的文件和启动项；其他配置、用户数据和 CIMCO 保留。
- **备份位置**：`<Mastercam安装目录>\chooks\.MC2027PluginSuite\`。卸载完成前不要删除。

安装文件被人工修改或启动项被其他安装器改变时，安装器会停止并报告冲突，避免覆盖这些修改。详细命令和恢复方式见 [安装说明](docs/INSTALL.md)。

## 验证与兼容性

保时捷业务 DLL 沿用已完成 **91 项宿主检查和 10 项离线投影检查** 的产物；OperationTools 等生产 DLL 保持已有验收版本。新增 HSM 已验证真实挖槽创建、参数回读、计算和回滚；MP 1.0.1 已在安装后的 Mastercam 中通过 **12 组、11,301 项断言**。安装器在 PowerShell 5.1 和 7 中各通过 **37 项检查**。这些结果来自本机与隔离安装目录，尚未在另一台电脑完成全套宿主验收。

保时捷的部分原生接口绑定特定 Mastercam 构建；其他补丁版本可能被接口检查拒绝。请先查看 [兼容性](docs/COMPATIBILITY.md) 和 [验证记录](validation/README.md)。刀路参数仍需根据实际零件、刀具和机床检查，当前包不包含机床专用后处理。

## 仓库结构

```text
Install.cmd / Uninstall.cmd / Verify.cmd   双击入口
Manage.ps1 / scripts/                      安装、校验与恢复逻辑
payload/chooks/                           发布用 DLL、FT、资源
catalog/                                  模块目录、逐文件版本与 SHA-256
docs/                                     安装、功能、兼容性、外部组件
src/                                      发布启动器与菜单整合源码
tools/                                    构建与打包工具
tests/ / validation/                      安装器测试与验证摘要
```

仓库包含发布载荷；普通用户无需编译。业务模块目前按已验收二进制分发，`src/` 仅包含本次发布整合代码。反馈问题请在 [Issues](https://github.com/xiepm/mastercam_plugin/issues) 附上模块名称、Mastercam 版本、操作步骤及错误文字，不要上传许可证或私人零件文件。
