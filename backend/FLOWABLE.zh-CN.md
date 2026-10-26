# Flowable 外部 Python 诊断

## 当前是/否执行约定

排查支持是和否两组出口，每组可有任意条连线，也可以缺省，使用 `flowable:diagnosisBranch` 保存。
没有匹配后续节点时，在 `diagnosticFailures` 中记录该思路失败。
流程属性 `flowable:diagnosisMode` 选择 `parallel`（默认）或 `serial`。
并行模式同步触发同组思路，无优先级；失败只结束当前思路，不重新触发兄弟思路。汇合按每次到达继续，无需强制聚合网关。
串行模式使用持久化队列，按 `flowable:diagnosisOrder` 升序、未指定时按 XML 顺序依次排查。
失败后尝试下一个待执行思路，全部耗尽且未成功时 `diagnosticStatus=failed`。
成功后暂停剩余思路（`diagnosticStatus=paused`）；界面可选择结束或继续，复核接口
使用 `mode=success`，提交 `action=confirm` 和 `next=finish` 或 `continue`。
继续操作恢复保留的队列，不重放已经完成的路径。有条件的判断应放在排查节点；结论只记录文本时无需绑定 Python。
导出的离线 Python 遵循相同规则，通过 `run(..., resume=state, success_action='continue'|'finish')` 恢复暂停状态。

worker 使用 `inspect.signature` 识别参数：兼容旧映射、匹配同名流程变量、上游结果中唯一的同名字段、
再使用默认值；缺失或歧义会提示具体参数。支持位置专用参数、异步接口、无输入及无返回值动作。
排查返回 `True`/`False`、`yes`/`no` 或 `{"next":"yes"}`；旧连线 ID 选择该线所属的整个分组。
节点面板无需填写参数语言。

请使用新增“并行排查与依赖”示例。旧示例及下文旧引擎场景脚本须迁移拓扑，原互斥约定不再适用。
没有分组的排查连线会被拒绝，不根据排列顺序猜测。
当前离线检查：`python scripts/verify-diagnosis-design.py`、`python scripts/verify-python-bindings.py`、
`pnpm exec node scripts/verify-code-export.mjs`。

浏览器编辑自定义诊断节点，导出器将它们转换成标准服务任务、排他网关和结束事件。
Flowable 7.1.0 负责调度；官方 `flowable.external-worker-client==1.0.2` 负责领取任务和提交结果。
`flowable_worker.py` 只负责调用绑定的 Python 函数，不实现自己的流程引擎。

## 启动环境

需要 Java 21、Maven 3.9、Python 3.9+ 和项目原有的 pnpm 环境。
Java 和 Python 依赖可以预先准备后在内网安装。普通工程师通过浏览器操作。

```powershell
# 在 flowable-runtime 中运行，数据库保存在当前目录 data/ 下
mvn package
java -jar target/diagnostic-flowable-1.0.0.jar
```

默认服务仅监听 `127.0.0.1:8080`，认证为 `diagnostic / local-demo`，用于本机示例。
实际使用时通过环境变量 `FLOWABLE_USER`、`FLOWABLE_PASSWORD` 配置账号密码。
Python 客户端和代理服务使用相同环境变量及 `FLOWABLE_URL`（默认 `http://127.0.0.1:8080`）。
不要在本机示例之外直接暴露默认配置；需要内网部署时配置地址、访问控制与数据库。

在仓库根目录另开终端：

```powershell
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
python backend/server.py
```

再运行 `pnpm dev`，打开编辑器。正式构建也可由 Python 服务提供 `dist/`。

## 运行完整示例

1. 点击“Flowable 执行”，选择诊断示例，再点击“载入诊断示例”。会替换画布，先导出需要保留的图。
2. 点击“导出执行包”，解压，得到 `source.bpmn`、`workflow.bpmn20.xml`、`bindings.json`。
   前者用于继续编辑，后者是引擎执行定义；不使用引擎定义替换原始图。
3. 在仓库根目录运行：

   ```powershell
   backend/.local/venv/Scripts/python.exe backend/flowable_worker.py C:/path/to/bindings.json --project backend/examples/diagnostic_demo
   ```

4. 在执行抽屉的下拉框选择示例场景，如 `recover`。启动表单自动显示登记会话类/工厂的初始化参数，留空使用默认值；其他启动数据可添加名称/值行。点击“部署并启动”。高级初始变量 JSON 默认折叠，开启后可替代表单，例如 `{"scenario":"recover"}`。
5. 点击“刷新执行结果”，查看实际经过的节点、变量和 Python 生成的温度图。
   SVG 文件位于 `backend/examples/diagnostic_demo/output/`。

示例包含全部八类诊断节点：排查、排查动作、结论、处置措施、深度诊断、跳转、问题解决、上升。
它使用模拟温度数据执行真实阈值判断并生成真实 SVG；风扇自检和恢复动作明确为模拟，不控制机台。

界面提供六张可独立执行的示例图；载入后可用“示例场景”下拉框填写相应的初始变量。
各图共享 `diagnostic_demo` 工程，执行时仍需使用该图导出的 `bindings.json`。

| 示例图         | 场景                                                 | 验证重点                                     |
| -------------- | ---------------------------------------------------- | -------------------------------------------- |
| 温度综合诊断   | recover / normal / action / escalate / severe / jump | 八类节点及所有结果分支                       |
| 电源电压诊断   | recover / normal / severe                            | 下限判断、恢复成功与失败                     |
| 通信重试诊断   | recover / normal / offline                           | 异步接口、排查→动作→排查的循环；最多三次     |
| 双传感器对比   | sensor-a / sensor-b / normal / severe                | 多个排查支路互斥执行，汇合后不读取未执行支路 |
| 压力处置与交接 | stable / leak / unknown                              | 连续处置的顺序、深度分析及跳转交接           |

这些图的采样数据与机台动作均为模拟；绘图、数值计算和流程执行为真实运行。
回访同一节点时，结果变量更新为最新值；执行记录保留每次经过节点的信息。
纯诊断图的分支为排他路由，因此合流不要求等待其它支路；普通 BPMN 并行流程仍保持原有汇合校验。

| scenario | 路径                                              |
| -------- | ------------------------------------------------- |
| normal   | 排查正常 → 结论 → 处置确认无需复位 → 问题解决     |
| recover  | 排查异常 → 结论 → 恢复措施 → 问题解决             |
| action   | 排查 → 排查动作 → 再排查 → 结论 → 处置 → 问题解决 |
| escalate | 排查 → 结论 → 处置 → 深度诊断 → 上升              |
| severe   | 排查 → 结论 → 处置 → 上升                         |
| jump     | 排查 → 结论 → 处置 → 跳转交接                     |

跳转函数记录 `handoff_requested` 及目标链路；不假装已执行目标链路。
跳转任务成功后允许本实例交接结束。接入实际项目时由对应业务函数实现目标链路交接。

## 上升复核与回退重查

新导出的执行流程到达“上升”时不会立即结束，而是进入 Flowable 人工复核任务。
画布中的“上升”仍然是最终节点；编译器在引擎定义里插入等待复核步骤。
只有点击“确认上升并结束”才到达真正的结束事件。“问题解决”仍然直接结束。
更新后需重新构建并启动 Java 服务，重新导出执行包并启动对应的 worker；已有旧版本实例不改变行为。

1. 在执行抽屉点击“刷新执行结果”，出现“已到达上升，等待人工复核”。
2. 选择此前实际执行过的节点，填写回退原因。
3. 可选填写复查输入变量，例如传感器示例从 `{"scenario":"severe"}` 改为 `{"scenario":"sensor-b"}`。
   这表示更换模拟采样条件；真实工程通常在重新调用采集接口时获得新数据。
4. 点击“回退重查”。Flowable 在同一实例中返回所选节点，Python 重新执行该节点及后续路径。
5. 如果重查后仍上升，可以继续复核；如果确认无法恢复，点击“确认上升并结束”。

回退不是撤销：不会恢复机台状态，也不会删除原诊断路径。后续机台动作可能再次执行。
输入相同、代码相同的确定性算法可能给出相同判断；回退本身不会自动纠正算法。

回退会清理目标及需要重算的下游结果和路由变量，并保留有效的上游结果。
旧结果、输入修改前后的值、回退原因和时间保存为 `diagnosticReviews` 流程变量，
可在“执行详情”中查看；Flowable 活动历史保留每次经过节点和复核的记录。
清理、记录与状态变更在同一事务内执行，避免 worker 读取半更新状态。
不能通过输入变量覆盖节点结果、路由变量或复核记录，也不能使用过期的复核页面提交操作。

复核接口 `/diagnosis-api/instances/{id}/review` 由同一 Java 服务提供，并使用相同认证。
`GET` 返回待复核状态和可回退节点；`POST` 的 `action` 为 `recheck` 或 `confirm`，
必须携带当前 `taskId`。回退还需要 `targetNodeId`、`reason`，可选 `variables`。
已经确认结束的实例不再允许回退。

## 任意人工判断节点的回退

在非最终诊断节点的“执行与人工判断”中启用“人工判断／确认”。
不配置 Python 接口时直接等待人工；配置接口时先执行采集、绘图或动作，再等待人工选择。
多后继节点按出线名称列出选项，必须明确选择；单后继节点提供“确认并继续”。
所有这些等待入口以及上升复核均提供回退，可选择此前实际执行过的排查、结论或动作节点。
当前节点和未执行节点不能作为回退目标；首个节点会提示暂无可回退节点。
回退到人工节点时会再次等待；若该节点绑定 Python，则先重新运行 Python。
本次不包含运行中自动节点的暂停介入；“问题解决”仍立即结束。

示例列表新增“人工判断与回退”：电压绘图后确认 → 纯人工结论确认 → 模拟处置后人工选择解决或上升。
无需到达上升即可从结论或处置节点回退。示例中的机台动作仍为模拟动作。
每次回退均保留历史、清理待重算结果；动作可能重复执行，不会撤销之前已发生的机台动作。

执行接口保持 `/review`，GET 的 `mode` 区分 `decision` 与 `escalation`，
人工节点返回说明、参考图与 `options`（出线 ID 和名称）。POST `action: confirm` 时，多出线必须传 `next`。
Python 的 `next` 在人工模式中只是建议，可以省略；实际路由由人工选择决定。
确认后节点结果中的 `next` 更新为实际选择并带有 `humanConfirmed: true`，原始结果保存在复核记录。
对象结果的其他字段保持不变；非对象结果包装在 `data` 中，纯人工节点生成确认结果。
新增配置保存为 `flowable:humanDecision`，支持撤销、重做和 XML 导入导出。
升级后重建并重启 Java/Python 服务，重新导出执行包并启动对应 worker；已部署实例保持原行为。
编译后的配置存储在 `flowable:diagnosticExecution` 扩展元素，避免流程说明 2000 字符限制。

## 接入自己的工程

先在“Python 项目”登记已有目录、可导入模块、解释器及可选工厂。状态型工程最直接的入口是
`Device` 等现有类：公开绑定方法成为接口，`self` 不作为用户输入。登记类只检查签名，不创建实例；
实际会话创建时按同名启动变量或默认值传入构造参数。工厂函数有返回类注解时同样免调用发现；
无注解工厂会用默认值临时创建对象，有必填参数须补返回类注解。工厂留空兼容模块函数和 `__all__`。

在非最终节点选择模块、工厂及方法/函数即可。签名自动匹配启动变量、按节点 ID 保存的完整原始结果、
唯一的字典同名字段，并保留默认值、位置专用参数和 `async def`；无需填写参数表达式。
旧映射仍兼容 `$Inspect.data`、`$`（全部变量）、字典/数组路径及 `$$device`（普通字符串 `$device`）。
动作允许返回 `None`，排查应返回明确是/否：`True`/`False`、`yes`/`no` 或含 `next` 的字典。
旧出口连线 ID 选择其所属整个分组；不以任意对象的真假性推测分支。最终节点不绑定业务逻辑。

用装有官方客户端的环境启动 worker。默认读取 `backend/.local/projects.json`，按模块/工厂选登记，
业务子进程使用登记解释器及工程工作目录。`--registry PATH` 可指定其他登记文件。
旧的未登记模块仍可用可重复的 `--project PATH` 提供备用根目录，此时使用 worker 自身解释器。
业务依赖安装在实际执行该工程的解释器环境。

同一流程访问同一工程时共享一个常驻隔离 Python 子进程，工厂实例只创建一次，普通函数也保留模块
全局状态；不同流程完全隔离。原始结果在 Python 内按节点 ID 保存，可为任意 Python 对象。
Flowable 仅保存可 JSON 化的展示投影，需要时带 `native`、`pythonType`、`representation` 信息；
`repr` 展示不会当成原对象传给后续方法。原生引用不能跨工程子进程共享。同一实例上的并行方法须由
业务工程管理线程安全。分支调度、人工等待及历史仍由 Flowable 负责，没有新增另一套流程引擎。

可按[设备会话示例](examples/session_project/README.zh-CN.md) 完成采集、判断、恢复和异步复核，
直接保留原生采集对象。调试连续调用共享会话，“重置会话”重新开始；真实流程的回退则在当前实例上
重跑方法，不回滚内部状态。worker 观察到流程结束后释放会话，失败会话保留供检查。
没有自动检查点：worker/子进程重启会丢失会话，旧流程继续时明确报会话丢失，不会静默重建实例。
历史及展示投影不能还原原始对象。离线骨架仍按原来的补业务/人工兜底规则运行，不自动执行图上 binding。

同一 Flowable 服务的相同执行包/主题只启动一个 worker 协调器，其内部通过隔离子进程同时处理
多次排查。本机单例租约会明确拒绝重复订阅；该锁不能跨机器，因此不同机器间也须保持单协调器。
兼容普通无状态函数不代表多个竞争 worker 可以共享原生对象或安全水平扩容。

Python 任务失败后，在 Flowable 执行中刷新结果并展开失败详情，可查看原始 Python traceback；
worker 日志可补充上下文。

工作主题默认使用节点 ID，导出时加入流程 ID 和执行定义摘要，避免不同图的同名任务混用函数。
移动节点、修改说明文字或 XML/参数 JSON 重新格式化不会改变主题。
同一张图内主题不得重复。连线、绑定或参数修改后，应重新导出并启动对应的 worker；旧实例仍需旧 worker。
原图中的条件表达式和默认分支会在导出时明确拒绝；自动模式使用 Python 的 `next`，人工模式使用人工选择。
不要同时让配置不同的 worker 订阅同一组主题。

当前执行导出支持一个顶层流程、一个普通开始事件和这些诊断节点；子流程、并行节点、复杂事件等会明确拒绝。
非最终节点须绑定接口或启用人工判断，并满足内容、连接和终点规则。
外部任务失败、超时重领可能造成重复调用，真实机台操作函数须按业务需要保证幂等。
桌面绘图函数若要求主线程或交互桌面，应在业务入口中启动独立桌面进程；官方客户端回调运行在线程中。

## 验证

### 判断组件自动转人工

`backend/diagnostic_components.py` 提供可复用的 Python 判断组件。Flowable 只接收等待请求、保存状态和继续执行，不判断业务逻辑是否实现。所有绑定 Python 的非最终节点都支持此协议，无需开启“人工判断／确认”；该开关用于额外要求人工复核自动结果。

```python
from diagnostic_components import DecisionComponent, decision

judge = DecisionComponent()

def diagnose(reading):
    return judge.run(reading, instructions='查看曲线，选择符合现场情况的后继')

@decision(instructions='查看曲线，选择符合现场情况的后继')
def diagnose_with_decorator(data):
    raise NotImplementedError('待实现业务判断')
```

基类未覆盖 `decide(self, data)`，或被装饰函数明确抛出 `NotImplementedError`，都会返回 `HumanDecisionRequest`。补齐实现后正常返回 JSON，多分支包含 `{"next": "连线ID", ...}`，即自动继续。`pass` / 返回 `None` 不表示未实现；其他异常仍是任务失败。同步、异步函数均支持。装饰器用于普通函数，其第一个参数或 `data` 关键字参数作为判断依据；类方法建议使用基类。

接口应直接返回请求对象，不要自行转成 JSON。请求携带数据与可选说明，不阻塞 worker 等待人工输入。说明留空时沿用流程图中的诊断方法；参考图和后继选项仍来自流程图。可选 `options` 必须与全部后继连线 ID 一致。界面展示依据数据和图表，允许选择分支或回退；回退同时清理失效的请求。

worker 已提供该模块的导入路径，业务工程正常导入即可；独立运行业务工程时应将 `backend` 加入 Python 导入路径。导出的代码骨架包含同一模块，由命令行界面收集人工选择。示例接口见 `backend/examples/diagnostic_demo/diagnostic_demo/decisions.py`。

升级后需重新导出、部署执行包并启动对应 worker；已有实例继续使用原版本 worker。组件独立验证与真实引擎验证（关闭人工开关，验证结论/处置节点的等待、图表依据、分支和回退）：

```powershell
backend/.local/venv/Scripts/python.exe scripts/verify-decision-components.py
backend/.local/venv/Scripts/python.exe scripts/verify-component-decisions.py
```

```powershell
python scripts/verify-flowable.py --unit-only
# Flowable 已启动时，使用装有官方客户端的解释器
backend/.local/venv/Scripts/python.exe scripts/verify-flowable.py
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-examples.py
node scripts/verify-diagnostic-lint.mjs
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-review.py
backend/.local/venv/Scripts/python.exe scripts/verify-human-decisions.py
```

第二条验证真实引擎、官方客户端、六种路径、路由互斥、判断结果与生成 SVG。
第三条运行四张自动图的十三种场景；第四条验证六图的全部规则、XML 往返和普通 BPMN 汇合规则。
复核脚本验证等待、连续回退、局部重查、A/B 分支旧结果隔离、非法/过期请求及最终确认。
原示例验证脚本会显式确认上升后检查结束状态。
人工判断脚本验证首次等待、纯人工节点、分支选择、回退至结论及动作、旧结果清理和审计。
