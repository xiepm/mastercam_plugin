# 验证记录

本目录区分业务模块已有宿主证据与发布工具新增测试。

## 业务产物

- PorscheAdvanced2027 1.0.0：最终安装产物已通过 91 项宿主检查、10 项离线投影检查；三个 FT 入口和创建/回滚界面已实际执行，保存后重开检查已通过。摘要见 `business-acceptance.json`。
- OperationTools2027 1.0.3：范围与原点补偿、装刀下界、参数/锁定/钻孔回读、三阶段工序、独立链 A→B 及回滚有既有宿主证据。发布文件保持对应哈希。
- 其他模块的验收范围并不统一：大多数有业务/界面检查；按曲面类型选择的独立界面取消未单独验收；截图模块历史测试中有删除空层失败的清理记录，未将其声明为完整测试清理通过。
- 运行过程中的原始失败、REA 结果、测试工程及本机日志保留在开发工作区，本公开包只提供不含本机路径的摘要和源证据哈希。

## 发布整合

`Workshop2027.dll` 2.7.1 和 `MC2027SuiteStartup.dll` 为本次编译的整合产物。前者调整可选原版菜单显示，并将模板入口接到已有导入窗口；后者摆脱开发机 IPC 依赖。编译成功与安装器测试不等于这两个新产物在另一台电脑已完成宿主验收。

`installer-5.json` / `installer-7.json` 由 `tests/Installer.Tests.ps1` 生成，覆盖真实发布载荷的干净安装、空启动链、路径含空格、重定向配置、UTF-16 保留、升级、文件冲突、备份损坏、部分失败恢复、旧启动链、卸载和路径越界保护。测试只在隔离目录操作，不启动或修改 Mastercam。

## 复现

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\Installer.Tests.ps1
pwsh.exe -NoProfile -File .\tests\Installer.Tests.ps1
```

测试数据位于 `%TEMP%\mc27-test-xxxxxxxx\`，不会纳入发布包。原始业务 DLL 的哈希由 `catalog/package.json` 记录；重编译整合代码后应运行 `tools/Update-Manifest.ps1` 并重新测试打包。
