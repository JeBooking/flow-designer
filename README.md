<div align="center">
    <h1>vue-bpmn-designer</h1>
    <p>BPMN process designer (Flowable edition)</p>
    <p>
      <strong>English</strong> | <a href="./README.zh-CN.md">简体中文</a>
    </p>
</div>

---

## Online Preview

- Preview URL: https://tsai996.github.io/vue-bpmn-designer/

Modern BPMN designer built with **Vue 3** + **Vite 6** + **TypeScript**.
This project deeply integrates `bpmn-js` and provides Flowable-focused customization for diagram modeling, property editing, and BPMN lint validation out of the box.

## ✨ Features

- **⚡️ Modern Stack**: Vue 3 (Composition API), Vite 6, TypeScript
- **🎨 UI System**: Based on Element Plus and SCSS
- **⚙️ Deep Bpmn-js Integration**:
  - Built-in `bpmn-js` with Flowable syntax support
  - Real-time linting via `bpmn-js-bpmnlint`
  - Process simulation via `bpmn-js-token-simulation`
  - Extra plugins such as grid background and mini-map (`diagram-js-minimap`)
- **💻 Embedded Code Editor**: Built-in CodeMirror 6 for advanced script/config editing
- **🧩 Developer Experience**:
  - `unplugin-auto-import` + `unplugin-vue-components` for auto imports
  - ESLint + Prettier integrated

## Diagnostic nodes

The palette includes Investigation, Investigation Action, Conclusion, Remediation, Deep Diagnosis,
Jump, Problem Solved and Escalation tasks. Investigation
means “further investigation is required” and requires data to inspect, acquisition instructions,
a reference image and assessment criteria. Upload a PNG, JPEG or WebP image (up to 5 MB); the image
is embedded in BPMN XML for offline sharing. Conclusion is a text-only diagnostic judgment. It must
follow an investigation and have exactly one successor: a handling action or escalation.
Investigation Action records a machine action and may only connect from and to an Investigation.
Remediation and Jump are handling actions; they may continue to another handling action, Deep
Diagnosis, Problem Solved or Escalation. Jump may end its current diagnostic chain without reaching a final node.
Problem Solved and Escalation are final nodes with editable names and details.
Every branch in a diagnostic chain must be able to reach Problem Solved or Escalation; a branch may
instead end at Jump or an investigation with no successor (a recorded failed path). Investigation/action loops remain valid when they can still reach one of these
outcomes.

Investigation accepts a start event, another investigation or an Investigation Action as predecessor.
It may continue to another investigation, Investigation Action, conclusion, Jump or Escalation.
Direct connections to Remediation are rejected, including shortcut append menus.
Self-connections are rejected. These rules apply when drawing, reconnecting and inserting nodes;
imported invalid connections and missing fields are reported by process validation. Drafts can still
be saved with validation errors.
Use Start → Investigation → Conclusion → Remediation → Problem Solved for an initial example.

**Export diagnostic JSON** saves a standalone version 3 `workflow.json` with diagnostic content,
embedded reference images, interface bindings, dependencies, branches, and investigation mode.
It omits layout, node dimensions, user colors, and fonts. **Export complete BPMN** retains the
full editing model, including saved layout and user styles. Legacy runtime JSON files in Python
skeleton bundles remain compatible; use the dedicated JSON export to save a portable definition.

The toolbar's **Import** accepts `.bpmn`, `.xml`, and exported `workflow.json` files. JSON imports
rebuild the diagram with a new layout and retain node content, connections, Yes/No groups,
serial order, and investigation mode. Legacy custom branch names keep their connections and
require a Yes/No assignment. Upload reference images stored as paths again, and configure
interface bindings absent from the JSON. Import `source.bpmn` from the export bundle to retain
the original layout and complete model configuration.

Investigations have **Yes and No** groups, each with any number of successors. Edit a connection
label on the canvas using only `是`, `否`, `yes`, or `no` (English is case insensitive) to change
its group, or use the properties panel. Neither group is mandatory. An unmatched result ends
and records that path as failed. Connect dependent checks after their prerequisite.
Groups persist as `flowable:diagnosisBranch` on sequence flows.

Choose **Parallel** (default) or **Serial** in the process properties. Parallel mode starts all
matching sibling paths concurrently, without priority; a failed path never restarts its siblings.
Serial mode tries siblings in ascending connection order (`flowable:diagnosisOrder`, with XML
order as the fallback). A failed path advances to the next sibling; exhausting all paths without
success fails the investigation. Success pauses remaining paths and lets the user finish or
continue them. Both the Flowable runtime and exported Python runner implement these rules.
A terminal ends its own path.
Merges continue on each arrival and do not synchronize other paths, so multiple actions may
connect to Problem Solved without a gateway warning.

New nodes have blank names. Every diagnostic node has a name and detailed content; an omitted
name is derived from the opening content and fits the node's shape and current size. A manually
entered name is retained. A conclusion name also fills empty conclusion content in full.
Nodes can be resized, with automatic names recalculated on resize. Changes support undo/redo.
Investigation uses a diamond, Investigation Action an upright trapezoid, Conclusion a rectangle,
Remediation an inverted trapezoid, Jump an ellipse, Problem Solved a triangle, and Escalation a
five-point star. Deep Diagnosis keeps its existing shape.

Only investigations show human judgment settings. Action nodes retain interface binding with
automatic signature-based parameters: exact workflow variable names, then unique fields in
upstream results, then function defaults. Missing or ambiguous data produces an explicit error.
No-argument functions and actions returning `None` are supported; no JSON entry is required.
Existing explicit mappings remain readable; selecting a new interface clears stale mappings.
The **Parallel investigations and dependencies** example demonstrates this contract. Legacy examples
retain migration labels: assign Yes/No and move decisions out of action nodes before execution.

## Related Project

- If you are interested in a DingTalk-style flow designer: [lowflow-design](https://gitee.com/cai_xiao_feng/lowflow-design)

## Repository Mirrors

- Gitee: https://gitee.com/cai_xiao_feng/vue-bpmn-designer
- GitHub: https://github.com/tsai996/vue-bpmn-designer

## 🖼️ Screenshots

<p>
  <img alt="Screenshot 1" src="public/sl1.png" width="480" style="display:inline-block" />
  <img alt="Screenshot 2" src="public/sl2.png" width="480" style="display:inline-block" />
</p>

## 📦 Installation

Use `pnpm` as package manager.

```bash
# clone repository
git clone https://github.com/tsai996/vue-bpmn-designer.git

# enter project
cd vue-bpmn-designer

# install dependencies
pnpm install
```

## 🚀 Scripts

```bash
# run dev server (port/options are in vite.config.ts)
pnpm dev

# build for development
pnpm build:dev

# build for testing
pnpm build:test

# build for production (with type checking)
pnpm build:prod
# or
pnpm build

# preview local build
pnpm preview

# type check
pnpm type-check

# lint and format
pnpm lint
pnpm format
```

## 🛠️ Project Structure

```text
├── public/                 # static assets
├── src/                    # source root
│   ├── assets/             # static resources (icons, styles)
│   ├── components/         # base and business components
│   ├── typings/            # TS type declarations and generated d.ts files
│   ├── App.vue             # root component
│   └── main.ts             # app entry
├── .env.*                  # multi-environment configs
├── AGENTS.md               # AI collaboration constraints
├── eslint.config.ts        # ESLint 9 config
├── vite.config.ts          # Vite config
└── package.json            # scripts and dependencies
```

## ⚠️ Important Notes

1. **Auto Imports**: This project uses `unplugin`-based auto import heavily. Do **not** manually import Vue core APIs (`ref`, `computed`, etc.) or Element Plus components.
2. **Bpmn-js Engine**: For BPMN model updates, always use command APIs such as `modeling.updateProperties`. Do **not** mutate DOM or business objects directly, otherwise Undo/Redo may break.
3. **AI Rules**: Check `AGENTS.md` for project-specific AI development constraints.

## Connect existing Python projects

Start `python backend/server.py` and `pnpm dev` in separate terminals. The
**Python projects** toolbar entry registers a local project directory and its
importable entry module, lists public functions and calls them in Python.
Existing projects remain independently maintained; optional interpreter paths
support their existing virtual environments. See [backend integration guide](backend/README.md)
for `__all__` exports, the included example and the generic invocation API.
No BPMN node binding or business input/output schema is imposed by this entry point.

## Export a diagnostic Python project

Click **Export Python skeleton** in the modeling toolbar, extract the ZIP, and run
`python runner.py` with Python 3.10+. The generated project uses only the standard
library and works offline without AI, a workflow server, or additional packages.

The project separates acquisition, parsing, display, diagnosis, routing, machine
actions and orchestration into Python modules. Each module maps stable BPMN node
IDs to editable functions. Unimplemented acquisition displays the manual data
collection instructions and accepts text, JSON or `@path/to/data.json`. You can
also pass `{node_id: raw_data}` via `run(supplied=...)` or `--data inputs.json`.
Unimplemented diagnosis displays the diagram's assessment instructions and asks
the operator to choose Yes or No. Automatic diagnosis returns `True`/`False`, `yes`/`no`,
or a dictionary with `next`. A legacy outgoing flow ID selects its whole group.
Machine actions require explicit completion confirmation when unimplemented in the offline skeleton.

The ZIP includes the original BPMN XML, extracted reference images, workflow JSON,
sample inputs and a bilingual README. Nested plain subprocesses and exclusive
branches are supported; conditions are displayed, never evaluated as code.
Unsupported BPMN constructs, incomplete required fields, unreachable nodes and
paths without an exit block export. Jump returns a handoff status rather than a
successful diagnosis; connecting an external workflow remains an integration task.
Regenerate into a new directory to preserve your handwritten implementations.

Run `pnpm exec node scripts/verify-code-export.mjs` for an end-to-end verification
of real Moddle models, ZIP integrity and the generated Python runtime. Python is
required for this check (`PYTHON` can override its executable).

## Community

> Add WeChat (note: bpmn) and request a group invitation.

<p>
  <img alt="WeChat" src="public/wx.jpg" width="240" height="400" style="display:inline-block" />
  <img alt="QQ Group" src="public/qq_qun.jpg" width="240" height="400" style="display:inline-block" />
</p>

## Sponsorship

If this project helps you, sponsorship is welcome.

<p>
  <img alt="WeChat Pay" src="public/wxpay.png" width="240" height="240" style="display:inline-block" />
  <img alt="Alipay" src="public/alipay.png" width="240" height="240" style="display:inline-block" />
</p>

## 📄 License

[Apache-2.0 License](./LICENSE)

# Flowable diagnostic execution

Diagnostic nodes can bind external Python module functions. Open **Flowable execution** to
choose from five examples (temperature, voltage, communication retries, sensor comparison and pressure), export an execution bundle, deploy/start and inspect
execution results with real Python-generated charts. Flowable schedules the process and the
official Python client runs the existing projects. See [setup and example](backend/FLOWABLE.md).
Human decision/confirmation nodes and escalation offer a return to earlier executed nodes
with preserved history. Python bindings are optional in human mode; bound nodes run Python
before waiting. Try the **Human decisions and rechecks** example.
Python decision base classes and decorators automatically request human judgment when business logic is unimplemented, without enabling human mode. Exported skeletons reuse the same component.
