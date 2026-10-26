# 原生 Python 设备会话

[English](README.md)

登记目录 `backend/examples/session_project`、入口模块 `device_session`、工厂 `Device`。
使用现有 Python 3.9+ 环境，无需额外依赖。也可将 `create_session` 登记为工厂，返回同一类实例。

在“Python 项目”的同一调试会话依次调用 `collect`、`restore`、`verify`。
初次采集为 22.6 V，恢复后的复核返回 `True`。重置会话后再次采集回到初始值。
这些设备动作均为模拟。

画图时遵循已有节点连接规则：

1. 开始 → 绑定 `ready` 的入口排查，其“是”分组进入采集。
2. 节点 ID 为 **`reading`**、绑定 `collect` 的排查动作 → 绑定 `is_low` 的排查。
   `reading` 参数会取得采集节点保存的原始 `Reading` 实例。
3. `is_low` 的“是”分组 → 结论 → 绑定 `restore_and_verify` 的处置措施 → 问题解决。

`restore_and_verify` 在同一实例完成恢复与异步复核；复核失败会抛出任务错误，不会误报问题解决。
本例只演示恢复思路，可不连接 `is_low` 的“否”分组，正常读数会记录该思路失败。
若需要正常检查完成路径，应另行设计符合规则的结论/结果链。照常填写节点必填说明及参考文件。
排查不能直接连接问题解决，处置措施不能回连排查。

在执行启动表单填写 `device_id` 为 `M01`、`threshold` 为 `24`，或留空采用构造默认值。
高级 JSON 替代方式为 `{"device_id":"M01","threshold":24}`，或 `{}` 使用默认值。
`ready` 返回 `True`；`restore` 无参数且返回 `None`；`verify` 是异步方法，
`restore_and_verify` 是返回 `None` 的异步动作。`latest`、`attempts`、`recovered`
保存在实例内部，无需在表单重复填写。`Reading` 保留为 Python 对象，界面和 Flowable
仅保存展示投影。回退重查在当前实例上重新运行方法，不回滚其内部状态。重启 worker 会丢失会话。
