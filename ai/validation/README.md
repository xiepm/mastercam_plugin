# AI 接口验收范围

当前发布适配层为 `identity.json` 中的 1.1.0.0。新 Porsche 接口证据见 [porsche-native-acceptance.json](porsche-native-acceptance.json)：真实 stdio MCP 到 API29 宿主，30 个调用（含 5 次同编号缓存回执）、54 项结果断言；四种 action 及 Regenerate=false 分支通过。投影和补面测试使用三个自产实体，覆盖阶梯孔、锥形沉头、平底盲孔；轮廓加工验证一个外轮廓。非零世界位置/孔轴原点、真实刀路最低点和完整清理已验证。本轮未重测倾斜孔轴、多岛轮廓或全部失败注入。

`native-acceptance.json`、`offline-acceptance.json` 和两个独立 review 是上版 1.0.2 的原始记录，保留其哈希和范围；不将其写成 1.1.0 的全部功能复验。本轮离线结果见 `porsche-native-acceptance.json` 的 offline 字段，包含 26 项 Python 测试和 5 项生产 PreviewGuard 检查。

原始宿主请求、响应、失败尝试和夹具清理收据保存在验证电脑的私有工作区；公开摘要绑定它们的 SHA256，不分发用户零件、机器配置或日志绝对路径。业务插件的历史验收另见仓库根目录 `validation`。

没有在此宣称无碰撞、机床仿真、后处理或生产 NC 放行。原版 X+ 与 CIMCO 仍按目录使用交互路线。
