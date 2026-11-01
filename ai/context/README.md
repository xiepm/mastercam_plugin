# 新会话恢复合同

任务输入和事件按 task.schema.json 保存在私有 workspace/tasks/<task_id>/，不随 Git 发布。

mc_task_create 固定输入副本和要求；mc_task_checkpoint 追加不可覆盖事件；mc_task_resume 重新计算输入、计划和证据摘要，发生变化则将对应结论降为 unknown。事件的 bindings 必须包含该检查实际依赖的计划/刀具/装夹/后处理/仿真配置，遗漏依赖无法自动检测，Skill 因而要求逐项绑定。

这个账本引用既有制造合同，不是第三种 IR。状态由执行者在读取真实回执后填写；有文件不等于文件证明通过。production_release 不接受 pass。

示例：先创建 task_id=part-001；把 native-readback.json、cam_plan.json、tool-config.json 保存在该任务目录；checkpoint 的 stage=toolpath、state=pass、artifacts 包含原生回执，bindings 指向计划与刀具配置。下次说“恢复 part-001”即可重新检查这些证据。
