# Local Python integration / 本地 Python 工程接入

Read the [English user guide](../docs/USER-GUIDE.md) / [中文用户手册](../docs/USER-GUIDE.zh-CN.md)
for drawing, binding, execution, human review and offline exports.

## 启动与登记 / Start and register

先按[首次准备](FLOWABLE.zh-CN.md#首次准备) / [prepare once](FLOWABLE.md#prepare-once)
安装 pnpm 依赖、准备 Python 3.9+ 虚拟环境和官方客户端，并用 Java 21、Maven 构建引擎 jar。
启动器不会自动安装依赖。准备好后在仓库根目录运行 / Once prepared, run from the repository root:

```powershell
pnpm dev
```

统一启动前端、Python 后端和 Java 引擎；打开打印的地址，在顶栏选择 **Python 项目**。
`/api` 转发至 `127.0.0.1:8765`。生产环境先构建 `dist/`，再运行 `pnpm start`；
`pnpm dev:frontend` 仅启动前端。显式设置 `FLOWABLE_URL` 只连接指定外部引擎；复用后端时须匹配同一引擎 URL。

The launcher starts the frontend, Python backend and Java engine. Open the printed address
and choose **Python projects**. `pnpm start` serves an existing `dist/` build;
`pnpm dev:frontend` starts only the frontend. An explicit `FLOWABLE_URL` connects to that
external engine only. A reused backend must report the same engine URL.

登记已有工程目录、可导入模块、可选解释器和工厂；工程保留原目录，依赖须已安装。

Register a local directory, importable module (for example `machine.api`, not a
filename), optional interpreter and optional factory. Relative paths resolve from
the repository root. Registration does not copy files or install dependencies.
The interpreter uses the project's root as its working directory, with `src/`, root
and parent on its import path.

工厂填 `Device` 等类名或 `create_session` 等函数名，公开绑定方法成为接口，`self` 不需输入。
类登记只检查签名，不实例化；会话创建时用同名启动变量或默认值传入构造参数。
工厂有返回类注解时同样免调用发现；无注解工厂会用默认值临时创建对象，若有必填参数，须补充
返回类注解。留空工厂时兼容原模块函数：有 `__all__` 按其导出（含重导出），否则发现入口模块
自身定义的公开函数。

Set factory to a class or factory function to expose its object's public bound
methods. Class discovery does not construct the class; required constructor inputs
are matched from startup variables at runtime, with defaults preserved. A factory
with a return-class annotation also supports discovery without invocation. An
unannotated factory is temporarily called using defaults; add a return-class
annotation if it requires arguments. An empty factory preserves ordinary module
function exports, including `__all__`.

## 连续调试与原生对象 / Debug native objects

按已登记接口的签名填写输入，同一调试会话中的连续调用共享实例和结果。
“重置会话”丢弃原实例与结果。界面只显示对象投影，含 `native`、`pythonType`、
`representation` 等信息，`repr` 不代替原始对象；内部属性及原始结果留在 Python 会话中。

Input fields follow the selected signature. Consecutive calls share a debug session;
**Reset session** discards its instance and results. Native objects stay in Python;
the HTTP response is a display projection, never a transferable replacement object.
Calls execute real business code. The default timeout is 120 seconds, configurable
with `python backend/server.py --timeout 600`; stopping a call cannot undo external actions.

## Flowable 执行 / Workflow execution

打开“诊断执行”，填写启动输入后点击“开始执行”。后端自动编译当前图、准备或复用 worker，
再部署并启动实例，无需手工导出绑定或启动 worker。详见[执行说明](FLOWABLE.zh-CN.md) / [execution guide](FLOWABLE.md)。

Open **Diagnostic execution**, fill startup inputs and click **Start execution**. The backend
compiles the current diagram, prepares or reuses its worker, then deploys and starts it.
No manual binding export or worker launch is required.

默认从 `backend/.local/projects.json` 按模块/工厂选择工程，业务子进程使用登记解释器及工作目录。
启动表单按登记类/工厂初始化签名生成，可选项留空保留默认值；额外启动数据可添加名称/值行。
普通方法参数从上游自动匹配。高级初始变量 JSON 默认折叠，开启后替代表单，默认 `{}`。

The worker reads `backend/.local/projects.json` and matches module/factory registrations;
business subprocesses use the registered interpreter and working directory. Startup fields
follow initialization signatures and preserve defaults for blank optional values. Add name/value
rows for extra data, or enable the collapsed advanced JSON option (default `{}`) to replace
the form. Ordinary method arguments match upstream results automatically.

结果自动轮询，真实画布节点高亮。结果卡片、数组表格展示返回值，返回 `chartSvg` 时显示图表；
原始详情默认折叠，失败时可展开查看 Python traceback。关闭抽屉后继续监控当前实例并更新画布提示，
直到流程结束，结束后保留已完成节点的提示；改图或导入图会隐藏旧实例的画布提示。
浏览器刷新或 Modeler 重建不会恢复监控。死信失败可确认重新执行，但旧实例不取消，动作可能重复。

Results update automatically with actual canvas-node highlights, result cards and array tables.
A returned `chartSvg` displays a chart; raw details stay collapsed and can expose a Python traceback.
Closing the drawer keeps monitoring the current instance and updating its canvas prompts until the
process ends; completed-node prompts remain available afterward. Editing or importing a diagram hides
canvas prompts for the previous instance. Refreshing the browser or recreating the Modeler does not
restore monitoring. Confirmed reruns after dead-letter failure create a new instance without
canceling the old one and may repeat actions.

人工待办自动从节点展开浮动窗口，曲线连接节点，完成后收回；各任务独立保留输入和错误。
可拖动标题或用方向键移动（Shift 加大步长），支持自动排布与恢复自动定位。收起不代表完成，
点击节点待处理按钮可重开；窄屏使用待办卡片轨道。窗口保留完整说明、参考与依据。
“是／否”组单选，组内路径默认全选，也可勾选子集；此执行语义需要新编译部署。
并行多待办时禁用回退，避免清理共享结果影响其他任务；请先处理其余人工任务。

Pending human tasks automatically expand into floating windows connected to nodes by curves and retract
on completion. Each task retains its own inputs and errors. Drag the title or use arrow keys (Shift for
larger steps); automatic layout and restored automatic positioning are available. Collapsing does not
complete a task: reopen it from its node's pending button. Narrow screens use a pending-card rail.
Windows show full instructions, references and evidence. Choose one Yes/No group; its paths default to
all selected and allow a subset in newly compiled deployments. Rechecking is disabled with multiple
parallel pending reviews because it clears shared results; handle the other human tasks first.

新执行的节点历史逐次保存函数实际输入（含默认值）、实例初始化输入（配置工厂时）、返回的依据／结果、
部署时的说明和参考文件、分支及错误。人工记录保存当时可用上下文、依据、参考和选择；该上下文与函数
实际参数分别标记。重跑保留此前记录。旧实例或缺失字段显示“未记录”，不会补造快照。Python 脚本未返回
的局部中间变量无法自动获取；需通过返回结构或 `HumanDecisionRequest.data` 提供采集值、参考值和判断依据，
例如人工处理示例中的 `voltage`、`threshold`、`unit`。

Node history for new executions saves each call's actual inputs (including defaults), factory
initialization inputs when applicable, returned evidence/results, deployed instructions and reference
files, branch and errors. Human records save the context available at the time, evidence, references
and choice; context is distinguished from actual function arguments. Reruns preserve earlier records.
Old instances or missing fields show **Not recorded**; missing snapshots are not reconstructed.
Python local intermediate variables that are not returned cannot be captured automatically. Provide
collected values, reference values and assessment evidence in the result structure or
`HumanDecisionRequest.data`, such as the manual-handling example's `voltage`, `threshold` and `unit`.

服务日志位于 `backend/.local/logs/`，worker 日志位于 `backend/.local/executions/<hash>/<uuid>.log`。
退出启动器只停止自有服务及其 worker，不停止复用/外部服务，不会撤销设备动作。

Service logs are under `backend/.local/logs/`; managed worker logs are under
`backend/.local/executions/<hash>/<uuid>.log`. Exiting the launcher stops only owned services
and their workers; reused/external services remain running. Equipment actions are not undone.

同一流程的同一工程常驻一个隔离子进程，创建一次工厂实例；普通函数也保留模块全局状态。
不同流程完全隔离，不同工程间不能直接传递原生对象引用。原始节点结果留在会话，按签名从
启动变量及唯一同名结果自动匹配；节点 ID 同名参数可取得完整原对象。支持默认值、位置专用
参数、异步和返回 `None` 的动作。排查返回明确是/否，不能将任意对象真假性用作路由。

Flowable owns scheduling, branch selection, human waits and history. Python owns
native objects and raw results; Flowable stores display projections. A project uses
one persistent isolated subprocess per workflow. Ordinary functions keep module globals.
Native references cannot cross project subprocesses. Parallel methods sharing an
instance require business code to manage thread safety. Finished workflow sessions
are released after the worker observes completion; failed sessions remain for inspection.

没有自动检查点。worker 或子进程重启后，旧流程继续时明确报告会话丢失，不会静默创建新实例。
人工回退在当前实例上重跑，不回滚内部状态或设备动作；历史显示不能恢复原始对象。
离线骨架仍需工程师补业务，不会自动调用流程图上的 binding。

There is no automatic checkpoint/recovery. Restarted workers report a lost session
for affected workflows rather than silently rebuilding objects. Rechecks rerun methods
on current state, without undoing equipment operations. Exported offline scaffolds
still require business implementation and do not automatically execute saved bindings.

同一 Flowable 服务的相同执行包/主题只启动一个 worker 协调器；它能同时处理多次排查，
内部按流程隔离工程子进程。同机重复启动会明确报错，本机单例锁不能跨机器，跨机器也须保持
单协调器。兼容无状态函数不代表竞争 worker 能共享对象或安全水平扩容。

Run one worker coordinator for the same execution package/topics on the same Flowable
service. It supports concurrent workflow runs with isolated subprocesses. A local lease
rejects duplicate workers on one machine; it cannot coordinate different machines, so
retain one coordinator across hosts too. Stateless-function compatibility does not
provide shared objects or safe horizontal scaling through competing workers.

## Platform API

- `GET /api/health`: backend identity and configured `flowableUrl` for launcher reuse validation.
- `POST /api/flowable/start`: `{ "xml": "...", "variables": {} }`; compiles the current diagram, prepares its worker, deploys and starts it.
- `GET /api/projects`: registrations and discovered interfaces.
- `POST /api/projects`: `{ "path": "...", "module": "...", "python": "optional", "factory": "optional", "name": "optional" }`.
- `POST /api/projects/{id}/refresh`: refresh discovery after code changes.
- `POST /api/projects/{id}/call`: `{ "function": "collect", "args": [], "kwargs": {}, "sessionId": "optional", "inputs": {} }`; returns `sessionId`. `inputs` initializes the first call's factory. Reuse `sessionId` to retain state.
- `POST /api/projects/{id}/sessions/close`: `{ "sessionId": "..." }`; discard that debug session.
- `POST /api/projects/{id}/remove`: remove registration without deleting source files.

登记持久保存在 `backend/.local/projects.json`。后端默认绑定本机回环地址，用于本地工具；
额外本机前端来源可用 `--origin URL` 添加。刷新/重新登记后需重置旧调试会话才能加载新代码。
