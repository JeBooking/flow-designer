<div align="center">
    <h1>vue-bpmn-designer</h1>
    <p>BPMN process designer (Flowable edition)</p>
    <p>
      <strong>English</strong> | <a href="./README.zh-CN.md">简体中文</a>
    </p>
</div>

---

## User guide

Read the [English user guide](docs/USER-GUIDE.md) / [中文用户手册](docs/USER-GUIDE.zh-CN.md) for existing-project registration, interpreters, discovery, node binding, automatic variable matching, Flowable/workers, human fallback, rechecks, export and troubleshooting.

Register your own business project through **Python projects**, bind its interfaces on the current diagram, then choose **Diagnostic execution → Start execution**. The backend manages the matching worker automatically; no execution bundle or separate worker command is needed.

**Enable structure simulation** only animates tokens and does not call Python. Offline skeletons are a separate development option: unimplemented logic uses human fallback and saved external bindings are not executed automatically.

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
a reference file and assessment criteria. Upload images, PDFs, text, audio, video or other files (up to 50 MiB); the file
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

**Export diagnostic project** downloads a ZIP containing the primary `workflow.json` definition
and actual files under `assets/`. JSON contains relative resource paths, not Base64. Its generic
resource manifest can also carry documents, data, and other file types. The project omits layout,
node dimensions, user colors, and fonts. Extract it and use **Import project directory** to load
the definition and resources together. Python skeletons use the same version 4 definition and
resource paths; neither export duplicates the workflow in a `source.bpmn` file.
**Export complete BPMN** remains an optional editor snapshot with saved layout and user styles.

The toolbar's **Import** accepts `.bpmn`, `.xml`, and exported `workflow.json` files. JSON imports
rebuild the diagram with a new layout and retain node content, connections, Yes/No groups,
serial order, and investigation mode. Legacy custom branch names keep their connections and
require a Yes/No assignment. Import a project directory to resolve local resource paths; importing
only JSON restores the diagram and reports unloaded resources. Legacy JSON files remain readable.

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
# start frontend, local backend and local Flowable
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

First prepare Java 21, Maven 3.9, Python 3.9+, frontend dependencies and the official Python client, and build the Flowable JAR; see [environment preparation](backend/FLOWABLE.md). Install business dependencies in their business interpreter beforehand. These preparation steps do not need repeating each run.

Then use only `pnpm dev` at the repository root to start the frontend, local backend and local Flowable. Open `http://127.0.0.1:5173/vue-bpmn-designer/`, then register your directory, importable module, interpreter and optional class/factory under **Python projects**. Registration neither copies sources nor installs dependencies. Select the project and interface on each node; parameters match signatures automatically.

Choose **Diagnostic execution → Start execution** on your current diagram; the backend prepares the worker. Flowable owns scheduling, human waits and history. The canvas and result cards automatically reflect real node states; raw variables and records live in collapsed details. Charts appear only when business code returns `chartSvg`; the platform does not generate business charts.

Each workflow has a persistent isolated Python process per project, retaining objects, instance state and module globals; Flowable stores display projections. Worker or business process restarts lose sessions, with no automatic checkpoint. Closing the execution drawer pauses polling while the backend workflow continues; reopening it resumes monitoring in the same panel. Refreshing the page or recreating the modeler does not restore monitoring of the previous instance. Exiting the launcher stops its own services and cannot undo equipment actions; reused services remain running.

After a task reaches dead letter, **Run the current diagram again** asks for confirmation before creating a new instance. It does not cancel the old instance or undo completed actions, and actions may run again. Previous instance IDs remain available in the current panel; record them before refreshing or recreating the modeler. Service logs live in `backend/.local/logs/`; worker logs use `backend/.local/executions/<content-hash>/<launch-uuid>.log`.

With an existing production build, use `pnpm start` and visit `http://127.0.0.1:8765/vue-bpmn-designer/`. Use `pnpm dev:frontend` for frontend-only development. See [backend integration](backend/README.md).

## Export a diagnostic Python project

Click **Export Python skeleton** in the modeling toolbar, extract the ZIP, and run
`python runner.py` with Python 3.10+. The generated project uses only the standard
library and works offline without AI, a workflow server, or additional packages.

The project separates acquisition, parsing, display, diagnosis, routing, machine
actions and orchestration into Python modules. Each module maps stable node
IDs to editable functions. `IMPLEMENTATION.md` maps nodes to files/functions; each handler comment identifies the node, full business content, input/output contract, outlets and call relationships. Unimplemented acquisition displays the manual data
collection instructions and accepts text, JSON or `@path/to/data.json`. You can
also pass `{node_id: raw_data}` via `run(supplied=...)` or `--data inputs.json`.
Unimplemented diagnosis displays the diagram's assessment instructions and asks
the operator to choose Yes or No. Automatic diagnosis returns `True`/`False`, `yes`/`no`,
or a dictionary with `next`. A legacy outgoing flow ID selects its whole group.
Machine actions require explicit completion confirmation when unimplemented in the offline skeleton.

The Python ZIP includes the shared workflow JSON, resource files, code skeleton,
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

# Diagnostic execution

Bind your own Python interfaces on the current diagram, then choose **Diagnostic execution → Start execution**. The backend manages workers; the canvas and results reflect real Flowable execution. Human decisions, escalation review and rechecks preserve history; rechecks can repeat equipment actions. Decision components can explicitly request human fallback. See [current workflow execution](backend/FLOWABLE.md).
