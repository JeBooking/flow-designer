<div align="center">
    <h1>vue-bpmn-designer</h1>
    <p>bpmn-js 流程设计器（Flowable 版）</p>
    <p>
      <a href="./README.md">English</a> | <strong>简体中文</strong>
    </p>
</div>

---

## 使用手册

从接入已有工程开始，请阅读 [中文用户手册](docs/USER-GUIDE.zh-CN.md) / [English guide](docs/USER-GUIDE.md)。

在“Python 项目”登记自己的业务工程，在当前画布绑定接口后点击“诊断执行 → 开始执行”。后端自动管理对应 worker，无需导出执行包或单独启动 worker。
覆盖解释器、模块登记、接口发现、变量匹配、人工兜底与回退、导出和排错。

“开启结构模拟”仅展示令牌，不调用 Python。“导出 Python 骨架”供独立开发，未实现业务转人工，不自动调用已保存的外部绑定。
参考文件支持图片、PDF、文本、音视频等，最大 50 MiB；浏览器预览或通过本机服务打开，取决于浏览器及本机软件。

## 在线预览

- 预览地址：https://tsai996.github.io/vue-bpmn-designer/

基于 **Vue 3** + **Vite 6** + **TypeScript** 构建的现代化流程设计器组件。本项目深度集成了 `bpmn-js`，并针对 Flowable 规范进行了深度定制，提供了开箱即用的流程绘制、属性编辑和 BPMN lint 校验等能力。

## ✨ 特性

- **⚡️ 最新技术栈**：Vue 3（组合式 API）、Vite 6、TypeScript
- **🎨 全新 UI 体系**：基于 Element Plus 和 SCSS
- **⚙️ 深度集成 Bpmn-js**：
  - 内置 `bpmn-js`（支持 Flowable 语法）
  - 使用 `bpmn-js-bpmnlint` 实时校验语法
  - 使用 `bpmn-js-token-simulation` 模拟执行
  - 内置网格背景、迷你地图（`diagram-js-minimap`）等增强插件
- **💻 强大的代码编辑器**：内置 CodeMirror 6，用于高级脚本或配置编辑
- **🧩 极致的开发体验**：
  - 配置 `unplugin-auto-import` 和 `unplugin-vue-components` 实现组件和 API 自动引入
  - 集成 ESLint、Prettier 进行代码规范检查

## 诊断节点与依赖关系

排查有“是”和“否”两种分支，每种分支可连接任意多个节点，无需同时具备两种分支。
在画布上修改连线名称即可改变分支，仅接受“是”“否”“yes”“no”，英文大小写不敏感；也可在属性面板选择。
没有匹配后续分支时记录该思路失败。有依赖的排查连接在其前置节点之后。
分支保存为 `flowable:diagnosisBranch`。

流程属性可选择并行排查（默认）或串行排查。并行模式同步启动同组思路，无优先级，
某条思路失败仅结束自身，不会重新触发其他并列思路。串行模式按连线顺序
（`flowable:diagnosisOrder` 升序，未填写时按 XML 顺序）依次排查；失败后尝试下一条，
全部思路耗尽且未成功则整个排查失败。成功后默认暂停剩余思路，用户可选择结束或继续排查。
Flowable 引擎和导出的离线 Python 均遵循这些规则，并保留失败记录。
终止节点仅结束当前路径；汇合按每次到达继续，不等待其他路径，多个处置连接问题解决不需要聚合网关。
排查不能直接连接处置措施，快捷追加与手动画线均受限制。

新建节点名称留空。所有诊断节点都包含名称和详细内容；未主动填写名称时，从内容开头
按节点形状和当前尺寸自适应截取，手动名称保留。结论只填名称时完整补全空白内容。
节点可拖动边角调整大小，自动名称随尺寸重新截取，操作支持撤销、重做。
排查为菱形，排查动作为正梯形，结论为矩形，处置措施为倒梯形，跳转为椭圆形，
问题解决为三角形，上升为五角星，深度诊断保持原样。

仅排查显示人工判断设置。动作保留接口绑定，按函数签名自动匹配参数：同名流程变量、
上游结果中唯一的同名字段、函数默认值；缺失或来源不唯一时提示具体参数名。
支持无参数接口及返回 `None` 的动作，无需填写 JSON。旧参数映射继续兼容，选择新接口时清理旧映射。
“并行排查与依赖”示例展示新规则；旧示例保留并标注迁移要求，运行前须设置是/否，并将动作上的判断移入排查。

## 相关项目链接

- 如果对仿钉钉流程设计器感兴趣，可查看：[lowflow-design](https://gitee.com/cai_xiao_feng/lowflow-design)

## 仓库地址

- Gitee：https://gitee.com/cai_xiao_feng/vue-bpmn-designer
- GitHub：https://github.com/tsai996/vue-bpmn-designer

## 🖼️ 示例图

<p>
  <img alt="示例图 1" src="public/sl1.png" width="480" style="display:inline-block" />
  <img alt="示例图 2" src="public/sl2.png" width="480" style="display:inline-block" />
</p>

## 📦 安装

本项目推荐使用 `pnpm` 进行依赖管理。

```bash
# 克隆项目
git clone https://github.com/tsai996/vue-bpmn-designer.git

# 进入项目目录
cd vue-bpmn-designer

# 安装依赖
pnpm install
```

## 🚀 运行与构建

```bash
# 启动本地开发服务器（默认端口等配置在 vite.config.ts）
pnpm dev

# 开发环境构建
pnpm build:dev

# 测试环境构建
pnpm build:test

# 生产环境构建（包含类型检查）
pnpm build:prod
# 或者
pnpm build

# 预览构建后的本地产物
pnpm preview

# 代码类型检查
pnpm type-check

# 运行 ESLint 修复和 Prettier 格式化
pnpm lint
pnpm format
```

## 🛠️ 核心目录结构

```text
├── public/                 # 静态资源
├── src/                    # 源码核心目录
│   ├── assets/             # 静态资源（图标、样式）
│   ├── components/         # 基础及公共业务组件
│   ├── typings/            # TS 类型定义及自动生成声明文件
│   ├── App.vue             # 根组件
│   └── main.ts             # 挂载入口
├── .env.*                  # 多环境变量配置文件
├── AGENTS.md               # AI 开发规则与约束
├── eslint.config.ts        # ESLint 9 配置
├── vite.config.ts          # Vite 配置
└── package.json            # 依赖管理和脚本定义
```

## ⚠️ 开发前必读

1. **自动引入**：项目大量使用基于 `unplugin` 的自动导入插件。开发时**切勿**手动导入 Vue 核心 API（如 `ref`、`computed`）以及 Element Plus 组件。
2. **Bpmn-js 引擎**：操作底层 BPMN 模型数据时，**必须**通过 `modeling.updateProperties` 等内部命令 API 修改，**严禁**直接修改 DOM 或业务对象，否则会破坏撤销重做功能。
3. **AI 规则约束**：请查阅根目录的 `AGENTS.md`，了解本项目为 AI / Copilot 定义的特殊规则。

## 接入已有 Python 工程

首次准备 Java 21、Maven 3.9、Python 3.9+、前端依赖、官方 Python 客户端，并构建 Flowable JAR，见[环境准备](backend/FLOWABLE.zh-CN.md)。业务依赖须预先装在业务解释器中，首次准备无需每次重复。

以后只需在仓库根目录运行 `pnpm dev`，统一启动前端、本机后端与本地 Flowable。打开 `http://127.0.0.1:5173/vue-bpmn-designer/`，在 **Python 项目** 登记自己的工程目录、可导入模块、解释器及可选类或工厂。登记不复制源码或安装依赖。节点选择工程和接口，参数按签名自动匹配。

在当前画布点击 **诊断执行 → 开始执行**；后端自动准备 worker。Flowable 负责调度、人工等待和历史，画布与结果卡片自动反映真实节点状态，原始变量和记录位于默认折叠的详情中。只有业务返回 `chartSvg` 时才显示图表，平台不会替业务生成图表。

每个流程的同一工程使用独立常驻 Python 子进程，保留对象、实例状态与模块全局变量；Flowable 保存展示投影。worker 或业务进程重启会丢失会话，没有自动检查点。关闭执行抽屉仅暂停轮询，后台流程继续；在同一面板重新打开会恢复监控。刷新页面或重建 modeler 不会恢复对旧实例的监控。退出启动器停止自己启动的服务，不能撤销设备动作，复用服务不会被终止。

任务进入死信后，可点击 **重新执行当前流程**，确认后新建实例。这不会取消旧实例，也不会撤销已完成的动作，同一动作可能再次执行。旧实例 ID 保留在当前面板中，刷新页面或重建 modeler 前应自行记录。服务日志位于 `backend/.local/logs/`，worker 日志路径为 `backend/.local/executions/<内容哈希>/<启动UUID>.log`。

已有生产构建时运行 `pnpm start`，访问 `http://127.0.0.1:8765/vue-bpmn-designer/`。仅前端开发可用 `pnpm dev:frontend`。详见[后端接入说明](backend/README.md)。

## 导出诊断 Python 工程

工具栏“导入”同时支持 `.bpmn`、`.xml` 和导出的 `workflow.json`。
工具栏“导出诊断项目”下载 ZIP，解压后包含唯一的主定义 `workflow.json` 和 `assets/` 中的实际资源文件。
JSON 仅记录相对路径，不内嵌 Base64；通用资源清单可承载文档、数据等其他文件类型。
定义保留诊断内容、接口绑定、依赖连线、分支与排查模式，不保存布局、节点尺寸、用户颜色或字体。
使用“导入项目目录”同时载入定义与资源。Python 骨架使用同一版本 4 定义与资源路径，
两类导出都不再额外放入重复的 `source.bpmn`。“导出完整 BPMN”仅用于可选的完整编辑快照。
导入 JSON 会根据节点与连接信息重建流程图并自动排版，保留节点内容、是／否分支、串行顺序和排查模式。
旧版自定义分支名称保留原连接，并提示补充是／否类别。单独导入 JSON 时会提示未加载的资源，
无需重新上传图片，改用“导入项目目录”即可按相对路径解析；旧版 JSON 继续兼容。

点击工具栏的 **导出 Python 骨架**，解压 ZIP 后使用 Python 3.10+ 执行
`python runner.py`。生成工程仅依赖标准库，无需 AI、工作流服务器或额外安装包，可离线运行。

工程将获取数据、解析数据、展示数据、诊断、分支决策、机台动作和流程调度拆成独立模块，
通过稳定的节点 ID 映射到待填写的函数。`IMPLEMENTATION.md` 提供节点到文件/函数的索引，
每个函数上方说明对应节点的 ID、类型、名称、内容、输入输出、后继出口及调用关系。未实现自动获取时，展示流程图中的人工采集方法，
接受文本、JSON 或 `@JSON文件路径`；也可以通过 `run(supplied={节点ID: 原始数据})`
或 `--data inputs.json` 传入数据。未实现自动诊断时展示原诊断方法，并让操作者选择是或否分组。
自动诊断函数返回 `True`/`False`、`yes`/`no` 或带 `next` 的字典；兼容的连线 ID 会选择其整个分组。
离线骨架中未实现的机台动作仍须确认完成后继续，这属于动作完成确认，不是分支判断。

Python ZIP 包含同一份工作流 JSON、资源文件、代码骨架、示例输入和双语使用说明。
支持普通嵌套子流程与互斥分支，条件表达式仅展示，不作为代码执行。
不支持的 BPMN 结构、必填字段缺失、不可达节点、无出口链路会阻止导出并报告原因。
跳转节点返回转交状态，不表示诊断成功；跨链路执行需要另行实现目标链路对接。
重新生成时请解压到新目录，避免覆盖已填写的业务逻辑。

可运行 `pnpm exec node scripts/verify-code-export.mjs`，验证真实 Moddle 模型、ZIP 完整性和
生成的 Python 工程行为。该检查需要 Python，可用 `PYTHON` 环境变量指定解释器。

## 社群交流

> 添加微信好友后（备注：bpmn）可邀请入群。

<p>
  <img alt="微信" src="public/wx.jpg" width="240" height="400" style="display:inline-block" />
  <img alt="QQ 群" src="public/qq_qun.jpg" width="240" height="400" style="display:inline-block" />
</p>

## 赞助支持

如果项目对你有帮助，欢迎赞助支持持续维护。

<p>
  <img alt="微信支付" src="public/wxpay.png" width="240" height="240" style="display:inline-block" />
  <img alt="支付宝" src="public/alipay.png" width="240" height="240" style="display:inline-block" />
</p>

## 📄 协议

[Apache-2.0 License](./LICENSE)

# 诊断执行

当前画布绑定自己的 Python 接口后，点击“诊断执行 → 开始执行”。后端自动管理 worker，画布与结果展示来自真实 Flowable 执行。人工判断、上升复核和回退保留历史；回退可能重复设备动作。业务判断组件可明确请求人工兜底。详见[当前流程执行](backend/FLOWABLE.zh-CN.md)。
