# 验证记录

本目录区分业务模块已有宿主证据与发布工具新增测试。

## 业务产物

- PorscheAdvanced2027 1.0.0：最终安装产物已通过 91 项宿主检查、10 项离线投影检查；三个 FT 入口和创建/回滚界面已实际执行，保存后重开检查已通过。摘要见 `business-acceptance.json`。
- OperationTools2027 1.0.3：范围与原点补偿、装刀下界、参数/锁定/钻孔回读、三阶段工序、独立链 A→B 及回滚有既有宿主证据。发布文件保持对应哈希。
- HSMRebuild2027 0.1.0：16 组逻辑测试、6 组原生流程及完整基线保护通过；492 项字段匹配。HighSpeed 与恒定重叠螺旋原生计算返回 true、重新读取 Dirty=false；TrueSpiral 只验创建和回读。见 `hsm-native-acceptance.json`。
- MPRebuild2027 1.0.1：安装后的宿主执行 12 组、11,301 项断言，截面、切片、斜截面、正反拔模方向、新建结果、精确回滚、故障清理及失效计划拒绝通过；源选择、时间戳、57 个原几何和 13 个原工序保持一致。见 `mp-native-acceptance.json`。
- 其他模块的验收范围并不统一：大多数有业务/界面检查；按曲面类型选择的独立界面取消未单独验收；截图模块历史测试中有删除空层失败的清理记录，未将其声明为完整测试清理通过。
- 运行过程中的原始失败、REA 结果、测试工程及本机日志保留在开发工作区，本公开包只提供不含本机路径的摘要和源证据哈希。

## 发布整合

`Workshop2027.dll` 2.8.0 增加 HSM、MP 高级功能路由和原版 X+ 入口；`MC2027SuiteStartup.dll` 使用独立启动入口，无需开发机 IPC。公开载荷共 295 个文件，本机另生成 1 个旧启动项转接 FT；已安装并重启，旧启动链和小蜜蜂/工艺助手/中键入口均返回成功。本机实测不代表另一台电脑已完成全部宿主验收。

HSM 面板/新建挖槽及工艺助手转发的五个 MP 窗口共 7 个入口已打开并取消，窗口类型/模式匹配，原工序和几何保持一致；MP 五个直接 FT 入口也通过同样验收。已确认七个插件页签显示。HSM 的 FT 补入资源声明后通过注册调用，业务 DLL 未重编译。见 `bundle-host-integration.json`。

`installer-5.json` / `installer-7.json` 各 37 项，覆盖真实发布载荷的干净安装、空启动链、中文/空格路径、UTF-8 收据、重定向配置、UTF-16 保留、升级、文件冲突、备份损坏、部分失败恢复、旧启动链、卸载和路径越界保护。测试只在隔离目录操作，不启动或修改 Mastercam。

`cimco-tests-5.json` / `cimco-tests-7.json` 各 18 项，覆盖官方安装器缓存、签名/哈希、已有安装判定、参数及失败处理。本机实际下载的 43,230,352 字节官方安装器通过哈希和 CIMCO A/S 签名检查；现有完整 26.9.11.46240 安装被正确跳过，文件未变。未在空白机器上执行 CIMCO 首次安装，见 `cimco-live-verification.json`。

原版 X+ 的 39 个文件与源包逐字节一致，15 个 FT 路由通过依赖检查；这不代表 15 个原版功能均经过本轮业务实测。见 `xplus-provenance.json`。

## 复现

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\Installer.Tests.ps1
pwsh.exe -NoProfile -File .\tests\Installer.Tests.ps1
```

测试数据位于 `%TEMP%\mc27-test-xxxxxxxx\`，不会纳入发布包。原始业务 DLL 的哈希由 `catalog/package.json` 记录；重编译整合代码后应运行 `tools/Update-Manifest.ps1` 并重新测试打包。
