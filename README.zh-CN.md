<div align="center">
    <h1>vue-bpmn-designer</h1>
    <p>bpmn-js 流程设计器（Flowable 版）</p>
    <p>
      <a href="./README.md">English</a> | <strong>简体中文</strong>
    </p>
</div>

---

## 诊断节点

工具栏新增排查节点、排查动作、结论节点、处置措施、深度诊断、跳转节点、问题解决和上升。排查节点表示“需要继续排查”，必须填写查看什么数据、如何获取数据、排查参考图和如何判断问题。参考图支持 PNG、JPEG、WebP（最大 5 MB），嵌入 BPMN XML，便于内网离线共享。排查动作记录诊断过程中执行的机台动作，只能由排查节点进入并连接到排查节点。结论节点是纯文本的诊断判断，不代表最终结论；它必须由排查节点进入，并且后序必须且只能选择处理动作或上升。处置措施和跳转节点均属于处理动作；处理动作可以连接到另一个处理动作、深度诊断、问题解决或上升。跳转节点所在链路允许不连接到最终节点。问题解决和上升是内容固定的最终节点。

每条诊断链路都必须存在一条可达问题解决或上升的路径；链路也可以在跳转节点结束。排查与排查动作之间的循环允许存在，只要仍有路径能够到达上述节点。

排查节点前序仅允许开始事件、其他排查节点或排查动作，后序仅允许排查节点、排查动作、结论或处理动作；排查节点禁止自连。画线、改接及插入节点时检查连接限制；导入的非法连接和必填项缺失由流程校验报错。允许保存尚未通过校验的草稿。示例：开始 → 排查 → 结论 → 处置措施 → 问题解决。

诊断字段以 `bpmn:Task` 上的 `flowable:` 属性保存，支持撤销和重做。本次仅实现流程编写模型，尚未实现代码和诊断手册生成。

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

## 相关项目

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

分别启动 `python backend/server.py` 和 `pnpm dev`，在顶栏点击 **Python 项目**。
填写已有工程的目录及可导入的入口模块，即可查看公开函数并在 Python 中调用。
外部工程保持独立维护，可指定其已有虚拟环境中的解释器。
参见 [后端接入说明](backend/README.md)，包含 `__all__` 导出方式、可运行示例及通用调用 API。
该入口只负责工程登记、接口发现和调用，不强制业务数据格式，暂未绑定 BPMN 节点。

## 导出诊断 Python 工程

点击工具栏的 **导出 Python 骨架**，解压 ZIP 后使用 Python 3.10+ 执行
`python runner.py`。生成工程仅依赖标准库，无需 AI、工作流服务器或额外安装包，可离线运行。

工程将获取数据、解析数据、展示数据、诊断、分支决策、机台动作和流程调度拆成独立模块，
通过稳定的 BPMN 节点 ID 映射到待填写的函数。未实现自动获取时，展示流程图中的人工采集方法，
接受文本、JSON 或 `@JSON文件路径`；也可以通过 `run(supplied={节点ID: 原始数据})`
或 `--data inputs.json` 传入数据。未实现自动诊断时展示原诊断方法，并让操作者选择下一条连线。
自动诊断函数须返回当前节点的后续连线 ID；未实现的机台动作必须人工确认完成后才能继续。

ZIP 包含原始 BPMN XML、参考图、工作流 JSON、示例输入和双语使用说明。
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
# Flowable 诊断执行

诊断节点支持绑定外部 Python 模块函数。通过“Flowable 执行”选择人工判断、温度、电压、通信重试、双传感器或压力六组示例，
导出执行包、部署启动流程，并查看执行记录和 Python 实际生成的图表。
流程由 Flowable 调度，已有工程由官方 Python 客户端调用。
详见[启动与示例说明](backend/FLOWABLE.zh-CN.md)。
启用“人工判断／确认”的节点和上升复核均可保留历史并回退到此前已执行的节点。
人工模式可不绑定 Python；绑定后先运行接口再等待人工选择。新增“人工判断与回退”示例。
Python 判断组件提供基类和装饰器，业务判断未实现时自动转人工，无需开启人工模式；代码骨架导出复用同一组件。
