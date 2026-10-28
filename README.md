# Mastercam 2027 插件工具箱

面向 **Windows x64 · Mastercam 2027 / API29** 的安装合集。将 24 个重建模块整理为一个发布包，提供中文功能目录、一键安装、文件校验、升级备份和卸载恢复。

**[下载最新版安装包](https://github.com/xiepm/mastercam_plugin/releases/latest)** · [全部插件目录](docs/PLUGINS.md) · [安装说明](docs/INSTALL.md) · [兼容性与已知范围](docs/COMPATIBILITY.md)

## 下载与安装

1. 在 Releases 下载 **`Mastercam2027-PluginSuite-2027.10.28.1.zip`**，完整解压到一个文件夹。
2. 确认 Mastercam 2027 已启动过一次，然后正常关闭 Mastercam。
3. 双击 **`Install.cmd`**。自动查找安装目录；若未找到，输入包含 `Mastercam.exe` 的目录。按 Windows 提示允许写入安装目录。
4. 重启 Mastercam，查看 **小蜜蜂、工艺助手、X+ 工具、MP 设计工具** 页签。

**保时捷／V++ 的入口位于「工艺助手 → 保时捷 / V++」**，包含实体自动轮廓、自动删孔补面、复杂孔自动工序。

安装器使用 Windows 自带 PowerShell 5.1，也支持 PowerShell 7。无需另外安装开发工具、REA 或 IPC 服务。插件运行需要 Mastercam 2027 的 API29 与 .NET 10 Windows Desktop 运行环境。

## 包含哪些工具

| 分类 | 主要功能 |
|---|---|
| 保时捷／V++ | 实体投影轮廓；粗轮廓、精光、倒角三工序；副本删孔补面；复杂孔识别后按阶段建工序 |
| 小蜜蜂 | 刀路参数、刀具、图形、共同参数、复制粘贴、群组与 NC 名称、导入导出、模板入口 |
| 工序与钻孔 | 粗转精、倒角、深度、替换串连、工序信息、装刀长度下界、分阶段钻孔与明确规格攻牙 |
| X+ 工具 | 串连、分度平面、SVG 导入、草绘刀路、刀柄截面、程序单、电极几何报表、STL 导出、白底截图 |
| MP 设计工具 | 曲面法向、按曲面类型选择、按解析面半径选实体、三维直边提取与 XY 投影 |
| 辅助 | 几何与坐标、夹具、矩形毛坯、三面检查、正交视图、中键确认 |

详见 [24 个模块及其功能范围](docs/PLUGINS.md)。这些重建工具有明确的支持范围，不代表同名厂商产品的全部功能。

## 原版插件与模板

CIMCO、HSM、原版 X+、Moldplus/Design Tools 以及旧模板均列入 [外部组件目录](docs/EXTERNAL.md)。本包不携带厂商安装包、许可证文件或 Mastercam SDK DLL，也不修改已有 CIMCO。原版 X+ 的菜单仅在检测到完整的 15 个原版 FT 入口时显示。

本仓库分发的重建模块没有新增激活、试用或用途限制界面；Mastercam 与外部组件按各自产品要求安装。

## 校验、升级与卸载

- **校验**：双击 `Verify.cmd`，检查下载文件和已安装文件的 SHA-256。
- **升级**：退出 Mastercam，解压新发布包，再运行 `Install.cmd`。最初的原文件备份会保留。
- **卸载**：退出 Mastercam，运行 `Uninstall.cmd`。仅恢复本套件接管的文件和启动项；其他配置、用户数据和 CIMCO 保留。
- **备份位置**：`<Mastercam安装目录>\chooks\.MC2027PluginSuite\`。卸载完成前不要删除。

安装文件被人工修改或启动项被其他安装器改变时，安装器会停止并报告冲突，避免覆盖这些修改。详细命令和恢复方式见 [安装说明](docs/INSTALL.md)。

## 验证与兼容性

保时捷业务 DLL 沿用已完成 **91 项宿主检查和 10 项离线投影检查** 的产物；OperationTools 等生产 DLL 保持已有验收版本。发布版额外调整了菜单显示条件与独立启动入口，安装器在隔离目录测试，不等于在另一台电脑完成全套宿主验收。

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
