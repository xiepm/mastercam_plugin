# 兼容性

- Windows x64；Mastercam 2027 / API29；.NET 10 Core 与 Windows Desktop 运行时。
- 测试主程序 `Mastercam.exe` 文件版本：`29.0.0.0`。具体原生接口还核对下表的二进制哈希，不能只按“2027”判断相同构建。
- 主要宿主验收使用公制测试副本。不能据此声称所有英制、机床类型和几何组合已经通过加工验收。
- 安装器支持 Windows PowerShell 5.1 和 PowerShell 7。编译 `src/` 整合源码另需 PowerShell 7/Roslyn、本机 API29 与 .NET 10 Windows Desktop 参考运行库。

## 保时捷原生接口的已验构建

| 文件 | SHA-256 |
|---|---|
| NETHook3_0.dll | `A5F87967FB5E8CFB7EA2A66CF984C9F0E468FE67B0CB0AF5A7B334CF50D404FF` |
| MCCORE.dll | `0F9C445215D93A7A3C5C25337134BB1E2CB5884642EA0B736EC5BEBF403ED14E` |
| MCGeomSld.dll | `C73D6C39B110EC708D0989650DAFB8E1AA778D57B86ED8ED4ABADED263B85038` |
| PSKERNEL.dll | `44B9A90D60DB1ED231D171EBAD1BC68EED79B39DFB2088D8E3B341E57FD148A5` |

这些文件由 Mastercam 自身提供，不在发布包中。相关功能在构建不匹配时会拒绝使用原生桥接；请报告文件版本和哈希，不要修改检查来强行加载。其他公开 API 工具的可用性需要按实际宿主验证。

## 常见问题

**安装后没有页签**：确认启动项已配置且 Mastercam 已重新启动。查看 `%LOCALAPPDATA%\MC2027PluginSuite\startup.log`，也可通过“运行用户应用程序”加载 `chooks\MC2027SuiteStartup\MC2027SuiteStartup.dll`。手动模式不会改启动项。

**没有“X+ 原版”**：这是可选的外部原版组件。重建的 X+ 功能在“X+ 工具”页。本包没有分发那 15 个原版 DLL。

**提示目标调用异常**：记录具体功能、操作步骤和异常文字。先检查安装哈希和对应宿主版本；不要反复执行可能已经生成对象的按钮。

**旧模板提示找不到 hsm.dll**：模板中存在 HSM 插件工序，需要匹配的内核与产品许可；仅安装本工具箱不能替代 HSM 工序计算内核。

**Windows 阻止下载文件**：确认来源和校验值，查看文件属性中的来源阻止信息。包未提供代码签名；不要关闭系统安全功能或添加全局排除。
