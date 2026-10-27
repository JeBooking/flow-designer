# 自动判断与人工接管示例

[English](README.md) | [中文](README.zh-CN.md)

这个独立 Python 工程演示自动分支、人工复核、判断组件兜底和预期的 Python 失败。工程没有工厂入口，
业务代码不需要第三方依赖，只使用传入的电压数据，不采集或操作设备。

## 启动并登记一次

先完成[用户指南中的平台准备](../../../docs/USER-GUIDE.zh-CN.md#2-首次准备与每次启动)，
再在仓库根目录执行 `pnpm dev`，由启动器统一管理所需服务和 worker。

打开 **Python 项目**，登记以下信息：

| 字段 | 内容 |
| --- | --- |
| 项目目录 | `backend/examples/manual_handling_project`（相对仓库根目录） |
| 入口模块 | `manual_handling` |
| 解释器 | 本机 Python 3.9+ 解释器的可执行文件路径 |
| 类或工厂 | 留空，使用模块函数 |
| 名称 | 便于识别即可，例如 `人工接管示例` |

纯人工图也需要登记这个模块，因为后续的记录动作会调用 `record_result()`。业务解释器无需安装
Flowable SDK；平台 worker 会提供 `diagnostic_components` 的导入路径，不要把它当作第三方依赖安装。

## 导入一张图并开始执行

1. 导入前先保存当前画布。
2. 在设计器主界面使用 **导入 BPMN 或 workflow.json**，选择本工程 [diagrams](diagrams/) 目录中的一个
   独立 `.bpmn` 文件。这些文件不放进执行界面的示例菜单；启动应用也不会自动用示例替换画布。
3. 选中排查节点 Check，对照下表查看 **Python 项目**、**调用接口** 和 **人工判断／确认**。
   如果导入的绑定尚未关联本机登记项，选择刚登记的工程；记录节点 Record 也应选择同一工程和
   `record_result()`。纯人工图的 Check 故意不绑定 Python。
4. 打开 **诊断执行**，点击 **开始执行**。默认电压为 `21.2` V；要演示自动走“是”，在开始新实例前，
   添加名称为 `voltage`、数值为 `24` 的额外启动输入。不添加则使用默认值，自动图走“否”。

纯人工图使用节点说明中的静态示例 `21.2` V。它的 Check 不调用 Python，启动输入 `voltage`
不会改变这段说明或其中的示例依据。

每张图都是 Start → Check；“是”经过 Conclusion → Record → Problem Solved（问题解决），
“否”到 Escalation（上升）。`record_result()` 仅作为示例记录步骤，返回 `None`，不写文件、不操作设备。

## 覆盖范围与预期结果

下表的人工开关指 Check 上的 **人工判断／确认**。

| 流程图 | Check 接口／人工开关 | 触发方式 | 预期结果 |
| --- | --- | --- | --- |
| [01-automatic.bpmn](diagrams/01-automatic.bpmn) | `automatic_decision`／关闭 | `voltage >= 22` 返回“是”，否则“否” | Check 自动分支；`21.2` 到上升，`24` 到问题解决 |
| [02-manual-only.bpmn](diagrams/02-manual-only.bpmn) | 无 Python 接口／开启 | 节点直接要求人工判断 | Check 不调用 Python，等待人工选择“是／否” |
| [03-bound-manual.bpmn](diagrams/03-bound-manual.bpmn) | `collect_evidence`／开启 | 先调用 Python 获取依据，再复核 | 显示依据，等待人工选择“是／否” |
| [04-base-fallback.bpmn](diagrams/04-base-fallback.bpmn) | `base_fallback`／关闭 | 未覆盖 `DecisionComponent.decide` | 通过组件协议转入人工判断 |
| [05-decorator-fallback.bpmn](diagrams/05-decorator-fallback.bpmn) | `decorator_fallback`／关闭 | `@decision` 包装的函数内抛出 `NotImplementedError` | 装饰器将尚未实现的判断转为人工请求 |
| [06-explicit-review.bpmn](diagrams/06-explicit-review.bpmn) | `explicit_review`／关闭 | 主动返回人工判断请求 | 不依赖节点人工开关，等待人工选择“是／否” |
| [07-ordinary-error.bpmn](diagrams/07-ordinary-error.bpmn) | `ordinary_unimplemented`／关闭 | 普通函数直接抛出 `NotImplementedError` | 预期执行失败并显示 traceback，不会转人工 |
| [08-empty-result.bpmn](diagrams/08-empty-result.bpmn) | `empty_decision`／关闭 | 函数体使用 `pass`，返回 `None` | 预期 `ValueError`：排查必须返回“是／否”；不会转人工 |

## 在浮动复核窗口中操作

每个人工待办自动从节点展开浮动窗口，曲线连接节点，各自保留输入和错误，完成后收回。
可拖动标题，或聚焦标题后用方向键移动（Shift 加大步长），支持自动排布和恢复自动定位。
收起不代表完成，点击节点的橙色待处理按钮可重开；窄屏使用待办卡片轨道。关闭抽屉后仍继续
监控当前实例，直到流程结束；结束后保留已完成节点的提示。

窗口展示完整节点说明、参考和依据。先单选“是／否”组，再勾选组内后续路径，默认全选；
路径子集需要重新编译部署的新执行。选择没有后继的组仍按原语义记录思路失败。
并行多个待办时禁用回退，因为回退会清理共享结果，请先处理其他人工任务。

点击节点的绿色完成勾，查看该节点每轮的起止时间和耗时。新执行逐次保存函数实际输入（含默认值）、
实例初始化输入（配置工厂时）、返回的依据／结果、部署时的说明和参考文件、所选分支及错误。
人工记录保存当时可用上下文、依据、参考和选择；该上下文与函数实际参数分别标记。重跑保留此前记录。
旧实例或缺失字段显示“未记录”，不会补造快照。修改画布或导入流程图后，隐藏旧实例的画布提示。
刷新页面或重建 modeler 不会恢复对该实例的监控。

Python 脚本未返回的局部中间变量无法自动获取。需要保留的采集值、参考值和判断依据，
应通过返回结构或 `HumanDecisionRequest.data` 提供；下文的 `voltage`、`threshold`、`unit` 就是这类依据。

运行图 02–06 时，查看判断依据和参考／判断方法说明。Python 提供的默认依据为
`voltage: 21.2`、`threshold: 22`、`unit: V`；纯人工图通过节点说明提供背景。
在 **下一步** 中选择“是”或“否”，再点 **确认并继续**。判断问题是“电压是否大于或等于 22 V”，
所以默认依据对应“否”；也可以人工选择另一分支来观察流程行为。

- 选“是”：经过结论和记录动作，到问题解决。
- 选“否”：到上升后还会等待一次，需要点击 **确认上升并结束**。图 01 默认自动走“否”时也会有这次等待。
- 图 07：应看到 Python 调用失败，展开错误详情中的 **原始 Python 异常堆栈**，定位故意抛出的异常。
  这不是成功的人工兜底，也不表示已经完成人工复核。
- 图 08：排查没有返回分支判断，应出现 `ValueError`；同样在错误详情中查看 traceback，不应出现人工复核。

## 能力边界

只有组件协议会把尚未实现的判断转成人工处理；普通 `pass` 或返回 `None` 不会主动请求人工复核，
图 08 专门演示这一边界。图 03 等待人工是因为开启了节点人工开关，不是因为返回依据就会自动兜底。

这些示例覆盖的是排查判断。执行界面目前没有用于手工填写采集结果、确认任意业务动作完成的统一表单，
不能把“是／否”复核当作这些能力。本说明描述预期行为，不代表已在你的机器上实机运行通过。
