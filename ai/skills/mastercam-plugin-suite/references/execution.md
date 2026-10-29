# 调用合同

`mastercam-plugins` 是插件层 MCP，复用已配置的 `mastercam` MCP 进入宿主主线程。它不分发 Mastercam SDK、不更改宿主启动项，也不绕过原有客户端审批设置。

## 工具与实际效果

| 工具 | 效果 |
|---|---|
| mc_catalog / mc_capability | 离线知识检索，可在 Mastercam 未启动时使用。 |
| mc_inspect | 读文档、单位、工序、刀具、前 250 个几何记录及选择。 |
| mc_operation_information | 范围/时间/装刀轴向下界；查询后恢复工序选择。dirty 或无效刀路不能当成有效时间。 |
| mc_prepare_change | 类型化预检，返回原值/目标值或几何分析。MP 会导出独立 STL、JSON/CSV 分析文件；恢复源选择，不创建结果图素。 |
| mc_apply_plan | 创建或修改计划中的数据库对象；严验参数，返回原生批次回读。无自动保存/后处理。 |
| mc_regenerate_hsm_plan | 只计算该 HSM 批次的新工序，记录原始 bool 与 fresh 状态。 |
| mc_rollback_plan | 本会话精确恢复；有后续编辑、文件变化等冲突会拒绝。 |
| mc_plan_status / mc_request_status | 前者查询宿主内计划，后者读磁盘请求结果，后者超时后仍可用。 |
| mc_discard_plan | 丢弃未执行计划，不修改数据库，不删除分析文件。 |

六种写入动作：`operation.depth`、`operation.finish`、`operation.chamfer`、`hsm.pocket`、`mp.sections`、`mp.draft`。参数 schema 是 MCP `mc_prepare_change` 的输入定义，使用 action 区分。精光/倒角当前只绑定已有刀具；底层插件虽然支持建刀，此适配器不因此暗含建刀行为。

计划保存文档、文件戳、几何/工序/刀具/选择/坐标上下文指纹。预览 15 分钟有效；Apply 前重新建立 native 包装对象并比对预览。不要在预览后切换文档、改选择、改刀具或编辑参数。若已变化就丢弃旧计划，再预览。

## Failure handling

- 先读 `ok`，再读 `data.status` 与 `data.result`；工具运输层成功不代表业务成功。
- `unknown_or_running`：保留 `request_id`，查询 `mc_request_status`；不换编号重跑。未决请求会阻止后续 native 调用。
- `not_found`：核对原请求编号、配置和工作区。查无记录不证明未执行，不能新建编号盲重试。
- `not_submitted`：本地准备在发送前失败，收据已终结且未进入宿主。修复本地错误后可使用新编号；旧编号只返回原失败收据。
- `Invalidated`：重新建立的预览变化或失败，旧计划不能再次执行；必须重新预览。
- 原生异常：查看错误与计划状态/原生审计。插件自动恢复失败会明确报告；不要概括为“已回滚”。
- 进程退出：磁盘结果仍可读，内存计划消失。不能用旧 plan ID 在新进程继续执行或回滚。
- 已保存文件变化：当前适配器拒绝旧计划。不要改收据、哈希或时间戳使检查通过。
- 恢复未知请求前须确认宿主当前状态。配置工作区中的 `active.json` 是未决请求标记，不能在宿主仍执行时删除。只有人工确认宿主已退出、保存现场且旧请求不再运行，才可将该标记移到证据备份目录；旧请求记录仍保留为未知，不重放。

所有调用在一个配置工作区内串行化；不要同时通过旧 bridge 或界面修改同一工程。文件日志保存在配置 workspace 的 `plugin-ai/<request_id>/`。

`mc_inspect` 当前只列前 250 个几何对象，不列可见层和关联深度字段。不要据此猜测遗漏的 ID 或层；层可见性及禁止解除关联由 prepare 的原生预检再次检查。只有分析意图时，MP 流程停在 prepare 并返回报告，不调用 apply；分析仍会写独立报告文件。
