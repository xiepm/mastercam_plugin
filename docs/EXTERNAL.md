# 原版组件与模板

| 项目 | 合集中处理方式 | 范围 |
|---|---|---|
| CIMCO Verify | `Install.cmd` 自动检测；缺少时下载并调用官方签名安装器 | 固定 26.9.11.46240，选择 2027 组件；完整匹配安装跳过，较新版本不降级。仓库不转存厂商安装器或许可证。 |
| CIMCO Edit 独立编辑器 | 保留已有安装 | 与 Mastercam 内的 Verify 插件不同；不是本套件自动安装项目。 |
| HSM 加工重构 | DLL 和 FT 已直接包含在 ZIP | 高速摆线及两种螺旋挖槽流程；见 [HSM/MP 功能](HSM-MP.md)。 |
| HSM 原厂完整产品 | 不装入缺内核的升级包 | 官方 27 升级包不含完整内核；未以混搭内核或旧授权替代。 |
| X+ 原版 | 15 个 API29 入口、39 个文件已直接包含 | 原始 DLL 不修改；API28 Ribbon 不装；FlowTo5Axis DLL 缺失，因此不列为可用功能。 |
| MP 设计工具重构 | 原有模块与 MPRebuild2027 已直接包含 | 曲面/实体辅助、截面、切片和网格分析；未声称完整 Moldplus 等价。 |
| Moldplus / Design Tools 原厂产品 | 不安装 2026 旧包 | 官方 Design Tools 15.0 对应 2027，下载要求客户登录。 |
| 旧保时捷／V++ | 使用已验收的 PorscheAdvanced2027 重构模块 | 不附带旧激活器或厂商许可文件。 |
| 刀路模板 / 花生米模板 | 通过现有导入入口导入自己的模板 | 不上传开发机模板或私人零件；旧 HSM 工序不会由重构模块自动转换。 |

官方来源：[CIMCO Verify 下载](https://www.cimcoverify.com/download)、[HSM 升级包说明](https://www.mastercam.dk/hsm-performance-pack/download/hsm/)、[Moldplus 下载](https://www.moldplus.com/downloads/)。核对日期 2026-10-28。

CIMCO 安装包固定哈希及下载地址写在 `scripts/Cimco.ps1`；原版 X+ 文件来源与字节校验保存在 `validation/xplus-provenance.json`。本套件不上传开发机许可证、私人配置、SDK 或商业内核。

在 Mastercam 刀路管理器选择“导入”，或使用小蜜蜂模板入口，选择自己的 `.mcam` 或操作库。先另存项目并核对单位、机床群组、刀具与坐标，再计算刀路。
