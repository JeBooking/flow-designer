# Flowable 外部 Python 诊断

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

1. 点击“Flowable 执行”→“载入诊断示例”。会替换画布，先导出需要保留的图。
2. 点击“导出执行包”，解压，得到 `source.bpmn`、`workflow.bpmn20.xml`、`bindings.json`。
   前者用于继续编辑，后者是引擎执行定义；不使用引擎定义替换原始图。
3. 在仓库根目录运行：

   ```powershell
   backend/.local/venv/Scripts/python.exe backend/flowable_worker.py C:/path/to/bindings.json --project backend/examples/diagnostic_demo
   ```

4. 在执行抽屉中填写初始变量，例如 `{"scenario":"recover"}`，点击“部署并启动”。
5. 点击“刷新执行结果”，查看实际经过的节点、变量和 Python 生成的温度图。
   SVG 文件位于 `backend/examples/diagnostic_demo/output/`。

示例包含全部八类诊断节点：排查、排查动作、结论、处置措施、深度诊断、跳转、问题解决、上升。
它使用模拟温度数据执行真实阈值判断并生成真实 SVG；风扇自检和恢复动作明确为模拟，不控制机台。

| scenario | 路径 |
| --- | --- |
| normal | 排查正常 → 结论 → 处置确认无需复位 → 问题解决 |
| recover | 排查异常 → 结论 → 恢复措施 → 问题解决 |
| action | 排查 → 排查动作 → 再排查 → 结论 → 处置 → 问题解决 |
| escalate | 排查 → 结论 → 处置 → 深度诊断 → 上升 |
| severe | 排查 → 结论 → 处置 → 上升 |
| jump | 排查 → 结论 → 处置 → 跳转交接 |

跳转函数记录 `handoff_requested` 及目标链路；不假装已执行目标链路。
跳转任务成功后允许本实例交接结束。接入实际项目时由对应业务函数实现目标链路交接。

## 接入自己的工程

在非最终节点的“Python 外部接口”中填写模块路径、函数名、JSON 关键字参数。
启动 worker 时通过 `--project` 添加工程根路径，可以重复传入；依赖安装在该 worker 使用的 Python 环境。
函数按标准 Python `import` 调用。最终节点只表示结束，不绑定业务逻辑。

```json
{"data": "$Inspect.data", "threshold": 70}
```

以 `$` 开头的字符串从流程变量读取，支持字典路径和数组下标；`$` 单独使用时传入整个变量字典。
`$$device` 表示普通字符串 `$device`。支持普通函数与 `async def` 异步函数，其它值按原样传入。
函数结果必须可以序列化成 JSON，保存为“节点 ID”同名流程变量。
多个后继的节点必须返回 `{"next":"后继连线ID", ...}`；不合法结果使任务失败，不会并行执行所有分支。
编译器自动插入排他网关；不执行用户填写的任意 Python 或条件表达式。

工作主题默认使用节点 ID，导出时加入流程 ID 和执行定义摘要，避免不同图的同名任务混用函数。
移动节点、修改说明文字或 XML/参数 JSON 重新格式化不会改变主题。
同一张图内主题不得重复。连线、绑定或参数修改后，应重新导出并启动对应的 worker；旧实例仍需旧 worker。
原图中的条件表达式和默认分支会在导出时明确拒绝，分支统一由 Python 返回的 `next` 决定。
不要同时让配置不同的 worker 订阅同一组主题。

当前执行导出支持一个顶层流程、一个普通开始事件和这些诊断节点；子流程、并行节点、复杂事件等会明确拒绝。
所有非最终节点须绑定接口并满足内容、连接和终点规则。示例没有人工确认 UI；需要等待人操作时应后续配置用户任务。
外部任务失败、超时重领可能造成重复调用，真实机台操作函数须按业务需要保证幂等。
桌面绘图函数若要求主线程或交互桌面，应在业务入口中启动独立桌面进程；官方客户端回调运行在线程中。

## 验证

```powershell
python scripts/verify-flowable.py --unit-only
# Flowable 已启动时，使用装有官方客户端的解释器
backend/.local/venv/Scripts/python.exe scripts/verify-flowable.py
```

第二条验证真实引擎、官方客户端、六种路径、路由互斥、判断结果与生成 SVG。
