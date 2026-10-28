# 安装与恢复

## 常规安装

下载 Releases 中的 `Mastercam2027-PluginSuite-2027.10.28.2.zip` 后完整解压。先正常启动一次 Mastercam 2027，让它生成当前用户的配置，再关闭软件，双击 `Install.cmd`。

`Install.cmd` 默认同时处理 CIMCO Verify：完整的 26.9.11.46240 或更新安装通过签名检查后跳过；缺失时从官方服务器下载约 43 MB，并核对固定 SHA-256 和 CIMCO A/S 签名。安装只选择通用资源和 Mastercam 2027 组件，禁止安装器强行关闭程序或自动重启。下载失败不会开始写入插件文件，修复网络后可重试。

这是**联网一键安装**。其余载荷直接包含在 ZIP 内。只安装 ZIP 内插件、不处理 CIMCO 时，执行 `Manage.ps1 -Action Install`；需要 CIMCO 时加 `-WithCimco`。CIMCO 目标由其官方注册表决定，必须与所选 Mastercam 目录一致。

安装器通过 Windows 安装记录和默认位置寻找 Mastercam。自定义目录可以手动输入，例如 `E:\CAM\Mastercam 2027`，输入的目录中必须有 `Mastercam.exe` 和 API29 的 `NETHook3_0.dll`。请勿输入 `chooks` 子目录。

首次运行可先双击 `Verify.cmd`；未安装时，包校验可以通过，随后显示没有安装记录是正常情况。单独校验下载包：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Manage.ps1 -Action CheckPackage
```

安装仅对当前 Windows 用户设置自动启动。管理员提升前会保留当前用户的配置目录；在其他 Windows 账户下需要为该账户单独配置入口。本版不支持一个安装收据同时管理多账户配置，请使用手动加载方式。

## 手动指定目录

在解压目录打开 PowerShell：

```powershell
# 只预览，不写文件
.\Manage.ps1 -Action Preview -MastercamRoot 'E:\CAM\Mastercam 2027'

# 安装全部，包括按需下载 CIMCO；Program Files 可能需要管理员权限
.\Manage.ps1 -Action Install -WithCimco -MastercamRoot 'E:\CAM\Mastercam 2027'

# 指定重定向或自定义的用户配置目录
.\Manage.ps1 -Action Install -MastercamRoot 'E:\CAM\Mastercam 2027' -ConfigDirectory 'E:\Documents\My Mastercam 2027\Mastercam\CONFIG'

# 校验已安装文件和启动配置
.\Manage.ps1 -Action Verify -MastercamRoot 'E:\CAM\Mastercam 2027'

# 卸载并恢复安装前文件
.\Manage.ps1 -Action Uninstall -MastercamRoot 'E:\CAM\Mastercam 2027'
```

Windows 的脚本执行策略可能阻止直接运行 `.ps1`。双击提供的 `.cmd`，或使用上面的 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...` 方式。该参数仅用于当前进程，不修改系统执行策略。

## 自动启动与旧插件共存

安装器只更新配置中的 **16010 启动项**，保留原文件编码、换行和其他设置。原启动 DLL 存在时，生成 `MC2027SuitePrevious.ft` 将其接入；干净安装无需旧启动 DLL。新启动器独立加载小蜜蜂、工艺助手和中键确认，不附带开发机 IPC 服务。

如果公制和英制配置指向两个不同的旧插件，自动安装会停止。可以保留原配置并只安装文件：

```powershell
.\Manage.ps1 -Action Install -MastercamRoot 'E:\CAM\Mastercam 2027' -SkipStartup
```

然后在 Mastercam 的“运行用户应用程序 / Run User Application”中加载 `chooks\MC2027SuiteStartup\MC2027SuiteStartup.dll`。此方式需每次启动后加载，或由使用者自己的启动管理器调用。不要把缺少收据的文件覆盖当作一次正常升级。

## 出错、升级与卸载

安装前检查全包 SHA-256；安装中逐文件保存快照；完成后回读哈希。普通异常会恢复本次写入前的文件和配置。升级保留最初的原文件，卸载只删除本包新建且仍与安装哈希一致的文件，或恢复原文件。

CIMCO 使用独立的官方安装器，其结果保存在 `chooks\.MC2027PluginSuite\vendor\`。CIMCO 安装失败时，核心插件会保留已安装状态并明确报错，不宣称两套安装器有统一事务回退。返回 3010 时，按提示手动重启 Windows，再运行安装器完成核验。卸载本合集不会卸载共享的 CIMCO；需要时使用 Windows 中 CIMCO 自己的卸载程序。

强制结束安装器、断电等可能留下未完成事务。先关闭 Mastercam，再运行：

```powershell
.\Manage.ps1 -Action Recover -MastercamRoot 'E:\CAM\Mastercam 2027'
```

恢复完成后重新校验或安装。备份及日志保留在 `chooks\.MC2027PluginSuite\history\`，不要从别的电脑复制安装收据。若安装文件后来被手工替换，先保存该修改，再决定是否恢复到该版本的发布文件；本版不会强行覆盖。

插件功能区可能被 Mastercam 工作区记住。卸载后若仍有失效页签，可在 Mastercam 自定义功能区中移除这些插件页签；安装器不重置整个工作区。各模块在 `%LOCALAPPDATA%` 下的个人设置、库与输出也会保留。
