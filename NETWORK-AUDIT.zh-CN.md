# 网络通信与数据去向检查

检查日期：2026-10-24。对象：当前工作区源码、配置、脚本、已有 dist，以及与联网入口直接相关的已安装依赖。

## 结论

没有发现项目自有业务代码把流程、参考图片或脚本内容暗中上传到作者网站、统计平台或云存储的路径。但不能认定项目“完全离线、零公网请求”，也不能称为只有前端：

1. Iconify 默认会从公网加载图标。
2. 导入的流程可以通过 connectorIcon 引用外部图片。
3. Python 项目与 Flowable 执行功能使用 HTTP；默认本机，Flowable 地址可由环境变量改成远程。
4. 接入的 Python 业务模块会实际执行，没有网络隔离，其行为取决于所接入的工程。
5. GitHub Actions 有发布 dist 到 gh-pages 分支的配置。

这里的“未发现”是静态检查结论，不是完整供应链审计或运行时抓包证明。

## 已确认的通信入口

### 1. 公网图标加载：默认页面就可能触发

- `src/main.ts:8-14` 注册 `@iconify/vue`。
- `src/views/ProcessDesigner/index.vue:327,334,357,362,382,387` 使用字符串图标名，如 `ri:github-fill`、`ic:baseline-undo`。
- 已安装依赖 `node_modules/@iconify/vue/dist/iconify.mjs:606-624` 配置默认地址及备用地址：`https://api.iconify.design`、`https://api.simplesvg.com`、`https://api.unisvg.com`。
- 同文件约 740 行开始把图标集合和名称拼成 `/{prefix}.json?icons=...`，通过 fetch 获取。

图标未在缓存中时可能发起请求。这条调用发送图标名称，未见读取并附带 BPMN、参考图片、脚本或 Python 参数。请求成功送达时，外部服务能看到通常的网络连接信息；Referer 是否发送及其内容由浏览器策略决定。离线缓存命中不能证明没有此联网路径。

### 2. 模型中的外部图片地址：有条件触发

`src/views/ProcessDesigner/Renderer/RewriteRenderer/ConnectorIconRenderer.ts:40,87-110` 从业务对象读取 `flowable:connectorIcon`。以 `#icon-` 开头的值引用本地 SVG，其余值直接写入 SVG image 的 href，没有地址白名单。

因此，导入含有外部 URL 的相应任务或事件时，浏览器可能请求该图片，具体受渲染分支与浏览器策略影响。这不是自动上传整张流程，但 URL 查询参数可以包含流程文件作者预先写入的信息，也可以用作访问追踪。内置 ConnectorOptions 使用的都是 `#icon-*`，本身不需要访问外部图片。Connector 模板选择模块当前没有在 BpmnModeler 中启用，但上述 Renderer 已注册，不能因为模板选择关闭就忽略此路径。

`FlowableExecution.vue:329-333` 还会直接显示服务端返回的 referenceImage。正常的本地编译器会验证其为 PNG/JPEG/WebP 的 data URL；如果更换服务端或返回内容，这一显示处自身没有再限制来源。

### 3. 浏览器到 Python 服务：同源 HTTP

- `src/services/pythonProjects.ts:8`：`/api/projects`，用于登记工程、刷新/删除登记和调用函数。发送工程名、本地路径、模块名、Python 解释器信息，以及调用函数的 args/kwargs；不是把整个 Python 工程打包上传。
- `src/services/flowable.ts:2`：`/api/flowable/*`，用于编译、启动、历史记录及人工复核。
- `FlowableExecution.vue:117-135`：编译包导出和启动都会先把当前完整 XML 发到 API。XML 中可能包含参考图片的 base64、脚本和其他模型属性；启动还发送初始变量。
- 人工复核还发送动作、原因、变量、目标节点/分支等数据。
- `vite.config.ts:18`：开发时 `/api` 代理到 `http://127.0.0.1:8765`。
- `backend/server.py:203-208`：服务绑定 `127.0.0.1`，默认 8765，校验本机 Host 与允许的 Origin。

相对地址意味着请求发往“当前页面的同源服务器”。默认本地部署时不出本机；若把页面和 API 代理部署到远程服务器，数据就会发送到该服务器，前端没有把目的地硬性限制为 localhost。

### 4. Python 到 Flowable：确实存在流程部署上传

- `backend/flowable_bridge.py:261-283`：读取 `FLOWABLE_URL`，默认 `http://127.0.0.1:8080`；通过 urllib 的 urlopen 发请求。
- `deploy()` 以 multipart/form-data 上传 `workflow.bpmn20.xml` 到 `/process-api/repository/deployments`。
- `backend/server.py` 启动流程时发送流程变量，查询历史和提交复核时也调用引擎接口。
- `backend/flowable_worker.py:82` 使用相同的地址配置，订阅外部任务，接收变量并提交业务结果和路由/人工判断信息。

编译后的引擎 XML 仍可能包含业务说明、参考图等诊断执行元数据。将 FLOWABLE_URL 配为外部服务器会使这些数据离开本机。代理环境及服务重定向也可能影响 urllib 的实际请求路径，因此仅看到默认 localhost 不能证明任意部署的实际网络状态。

### 5. Python 扩展执行边界

`backend/worker.py:26` 在登记/刷新接口时就导入用户选择的模块；调用时执行公开函数。`backend/flowable_worker.py:32` 同样导入绑定模块并执行函数。

导入会运行模块顶层代码，不必等到点击函数调用。子进程继承环境，不是网络沙箱，也没有禁止请求外部服务器。仓库内置示例主要做数据模拟、生成本地 SVG 和返回结果，未发现第三方上传代码；无法据此保证任意接入工程或其依赖不联网。

### 6. 发布与开发阶段

`.github/workflows/gh-pages.yml` 在 main 分支 push 时安装依赖、构建，并将 dist 发布到 gh-pages 分支。它发布构建产物，包括被打包的静态示例，不是读取用户浏览器里尚未导出的流程并上传。推送仓库本身与网页运行时的数据发送是两种行为。

pnpm、Maven、Python 依赖安装及 Docker 拉取基础镜像需要访问相应软件仓库；这不能等同于业务内容上传。本次没有执行安装、发布或现有集成验证脚本。

## 各模块核对结果

下表涵盖 src、backend、scripts、flowable-runtime/src 中 214 个源码/声明/模型/配置文件的静态特征扫描；对通信、文件和动态执行入口继续阅读实现并追踪调用。并非对所有第三方源码逐行审计。

| 模块 | 数据处理与检查结果 |
| --- | --- |
| main、App | Vue 初始化；Iconify 公网图标入口；生产模式反调试组件 |
| ProcessDesigner 主界面 | FileReader 本地读取 XML；Blob 下载 XML/SVG/Python ZIP；外部 GitHub/Gitee 链接需点击；图标加载见上文 |
| BpmnModeler、BpmnPanel | 本地创建模型、注册模块、选择属性面板，没有额外 API 上传入口 |
| Panel 全部 60 个文件 | 模型字段编辑为主；HttpTask、EmailTask、ShellTask、ScriptTask、ExternalTask 等配置执行语义，编辑时不直接执行 HTTP/邮件/脚本；Investigation 图片为本地 data URL；PythonBinding 记录执行绑定 |
| PythonProjects | 显式登记/调用操作使用 projects API；打开面板会获取工程列表 |
| FlowableExecution | 编译包、启动、历史、人工复核通过 API；与纯浏览器代码导出不同 |
| Modeling、Replace、Parse | 本地业务对象创建、替换、解析与命令栈操作，未发现独立网络发送入口 |
| Renderer | 本地 SVG 渲染；connectorIcon 外部图片例外见上文 |
| Palette、ContextPad、PopupMenu | 本地工具栏、节点创建和菜单；未发现上传入口 |
| Connector | 静态模板及属性写入；内置图标为本地 SVG；模板菜单当前未启用 |
| Properties、utils、hooks | 获取 bpmn-js 服务、读写业务对象和扩展元素；没有 API 发送逻辑 |
| Diagnosis | 诊断类型、连接规则、渲染与图片 data URL 校验；没有云端诊断调用 |
| Lint | 静态 resolver 和本地校验；bpmn.io URL 为帮助元数据，不代表把模型提交给 bpmn.io |
| Translate、languages | 本地字典与翻译；未使用在线翻译服务 |
| CodeGeneration | 浏览器生成文件和 ZIP；模板中的 acquisition.fetch 是普通 Python 函数名，不是 HTTP fetch；默认展示打开本地图片 URI |
| examples | 编译时导入本地 BPMN 示例，不是远程下载模型 |
| components/CodeMirror | 本地编辑、语法支持、补全和静态 HTML 帮助；未发现执行用户脚本或在线编译请求 |
| components/SvgIcon、assets、styles、public | 本地 SVG、字体依赖与图片；未发现自有 CSS 引入远程字体/CDN 的入口 |
| stores | Pinia 持久化语言选择；没有发现自动保存/同步流程到云端的 store |
| types、typings、flowable.json | 类型声明和模型描述；XML namespace URL 是标识符，不会因声明本身触发请求 |
| backend/server、worker | 本机 HTTP、工程登记 JSON、子进程导入/调用；边界见上文 |
| backend/flowable_bridge、flowable_worker | 可配置目标的引擎通信和流程上传；边界见上文 |
| backend/diagnostic_components、内置示例 | 人工判断约定、示例计算、写本地图表；未发现第三方上传 |
| Java Application、ReviewController | 本地引擎与历史/复核操作；未发现自定义第三方 HTTP 客户端发送逻辑 |
| application.properties | 引擎绑定 127.0.0.1:8080；H2 使用本地 data/diagnosis；保留完整历史，因此本地数据库会保存执行信息 |
| scripts | 示例生成、代码导出检查、本机 API/引擎验证；部分脚本会部署流程并运行 worker，其引擎目标同样受 FLOWABLE_URL 影响 |
| Vite、package、env、Docker、CI | 默认本地代理；四个 .env 文件均为空；没有项目级 install/postinstall 上传脚本；Docker 引用的 conf/nginx.conf 在当前工作区缺失，无法审计该配置 |

## 容易误判的内容

- Investigation 的“上传参考图”使用 FileReader.readAsDataURL，保存到模型，不是发往图床。但后续执行编译/启动发送完整 XML 时，图片也可能随 XML 传给后端/引擎。
- disable-devtool 依赖里存在默认外部错误页地址，但本项目显式配置 timeOutUrl 为 about:blank，并提供 rewriteHTML，未发现当前配置走该默认外部地址的依据。
- bpmn-js 署名、仓库链接、lint 文档、XML 命名空间和依赖许可证中的 URL，不应直接归类为模型上传。
- 已有 dist 中也发现 Iconify 的三个公网域名；压缩包中出现域名只能证明字符串存在，不能单独证明每个地址都被请求。

## 如要求严格本机、零公网访问

建议将 Iconify 图标改为本地资源；限制 connectorIcon 及服务端返回图片只能使用批准的本地片段/data URL；在服务配置层限制引擎地址和代理；审查所接入 Python 工程；以 CSP 与进程出站网络规则约束资源和请求，并在浏览器与后端进程两侧抓包验证。

本次仅检查并新增本报告，没有修改业务代码，没有运行构建、类型检查或会启动/部署流程的验证脚本。检查使用 git status、rg 文件清单/特征检索、PowerShell Get-Content/Get-ChildItem 和正则扫描。未进行全交互抓包、全量 node_modules/venv/Maven 二进制审计、数据库内容审计，也未核实机器当前运行进程的 FLOWABLE_URL、代理或远程部署配置。
