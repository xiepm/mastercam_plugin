# 示例请求

以下仅示范字段含义。路径、ID、数值必须取自当前文档和用户工艺要求，不得照抄到实际零件。

深度预览：

```json
{"request":{"action":"operation.depth","expected_document":"<mc_inspect 返回的已保存文件>","operation_ids":[123],"parameters":{"Depth":-8,"Incremental":false,"DetachAssociativeDepth":false}}}
```

这个例子把指定工序的刀具平面绝对深度改为 -8 个文档单位，不表示 world Z=-8，也不允许默默解除关联深度。

实体截面：

```json
{"request":{"action":"mp.sections","expected_document":"<已保存文件>","solid_ids":[456],"output_level":1,"parameters":{"origin":{"x":0,"y":0,"z":3},"normal":{"x":0,"y":0,"z":1},"count":1,"spacing":0,"mesh_tolerance":0.01,"weld_tolerance":0.0001}}}
```

平面是 world Z=3；此公差只是示例。结果层须已存在且可见。先查看闭环/开放路径/告警，再决定是否生成线。`count>1` 时 spacing 必须大于 weld_tolerance。

执行已授权的预览：

```json
{"plan_id":"<返回的 plan_id>","preview_sha256":"<返回的 preview_sha256>","expected_document":"<同一文件>","request_id":"apply-<新的随机编号>"}
```

MCP 超时后用相同 request_id 查询 `mc_request_status`；不能先换编号重试。参数回读成功后如需刀路计算或仿真，要另走对应流程。

自然语言使用示例：

- “解释保时捷自动轮廓与 HSM 挖槽的区别，并列出输入要求。”只检索目录，无需启动宿主。
- “先预览把选定的两道轮廓改到刀具平面绝对深度 -12，保留关联深度。”先读取选择和 ID；若存在关联深度则报出冲突，不能擅自设 DetachAssociativeDepth=true。
- “按给定平面分析这个实体，先不要建线。”只运行 MP prepare，返回报告；不要调用 apply。
- “运行 CIMCO 看是否撞刀。”当前目录只有交互路线；进入实际 UI 获取仿真证据，不能用 HSM Regenerate=true 回答无碰撞。
