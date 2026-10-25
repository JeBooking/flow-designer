# Diagnostic workflow user guide

[简体中文](USER-GUIDE.zh-CN.md) · [Project README](../README.md)

For engineers integrating an existing Python project with diagnostic workflows. Flowable schedules real execution and a separately started Python worker calls business functions. You can also export an offline Python scaffold to implement independently.

## 1. Choose an execution mode

| Entry                       | Purpose                                                          | Executes business Python?                                           |
| --------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------- |
| Python Projects             | Register projects, discover interfaces, debug one call           | Yes, when you invoke a function                                     |
| Enable structure simulation | Observe BPMN token animation                                     | No; does not validate Python, data or business decisions            |
| Flowable Execution          | Deploy and run actual workflows, inspect results and human waits | The worker calls bound interfaces                                   |
| Export Python skeleton      | Generate an offline project for engineers to complete            | Acquisition/decision/action placeholders default to manual fallback |

The scaffold does not automatically execute external-module bindings saved in the diagram. Flowable workers execute those bindings. Registering a project does not start a worker.
Structural simulation follows BPMN animation rules; it does not validate diagnostic Yes/No results or serial success/pause scheduling.

## 2. Start and register an existing project

Run in separate terminals at the repository root:

```powershell
python backend/server.py
pnpm dev
```

Open the URL printed by Vite. `/api` forwards to `127.0.0.1:8765`. Alternatively, run `pnpm build-only` and open `http://127.0.0.1:8765/vue-bpmn-designer/` through the backend.

Open **Python Projects** in the toolbar:

1. **Project directory**: the existing root, e.g. `D:/equipment/diagnostics`. Absolute paths or paths relative to this repository are accepted; no copying is necessary.
2. **Entry module**: an importable name such as `machine.api`, not `machine/api.py`.
3. **Python interpreter**: an existing environment such as `D:/equipment/diagnostics/.venv/Scripts/python.exe`. Empty uses the backend interpreter. Dependencies must already be installed there.
4. Optionally enter a display name and register the project.

Discovery shows functions, signatures and documentation. With `__all__`, exported functions including re-exports are listed; otherwise only public functions defined by the entry module appear:

```python
# machine/__init__.py; machine.api could also be registered as the entry
from .sampling import inspect_voltage
from .actions import reset_device

__all__ = ['inspect_voltage', 'reset_device']
```

Discovery/debug calls add the project's `src/`, root and parent to the import path and use its root as the working directory. Each call uses a separate subprocess; do not depend on objects retained by earlier calls. Refresh interfaces after code changes. Removing registration leaves source files intact. Registrations persist in `backend/.local/projects.json`.

Debug a function without side effects first: select it, enter a JSON array of positional arguments and a JSON object of keyword arguments, then inspect the result/error. This invokes one function, not the workflow. JSON results pass through; other objects are represented as `repr`, not transferable original objects. The default timeout is 120 seconds; change it with `python backend/server.py --timeout 600`.

## 3. Draw a small workflow and describe the work

Start with **Start → Investigation → Conclusion → Remediation → Problem Solved**, then add a No branch or Escalation. The parallel investigation/dependency example illustrates grouping. Loading examples replaces the canvas; export anything to retain first. Older examples may need migration to current rules.

Select nodes and fill in the name and details. An empty name generates a summary from content and node size; manually entered names remain. Investigations also require data to inspect, acquisition method, assessment method and a reference file. Conclusions require content, investigation actions require action instructions. Investigations decide; actions execute; conclusions record text; Problem Solved/Escalation express outcomes.
The **Node type** field under General is read-only and identifies the node even when its name is empty.

Classify investigation outlets as Yes/No, or name the flows `yes/no/是/否`, consistent with the assessment. Either group may have multiple outlets or be absent; an unmatched result records a failed idea. Investigations cannot connect directly to remediation; insert a conclusion. Investigation actions lead back to investigations. Validation reports illegal connections and missing content; drafts may still be saved.

Choose parallel or serial in process properties. Parallel starts matching ideas concurrently; failure ends only that idea. Serial tries flows by ascending `diagnosisOrder` (definition order breaks ties), continues after failure and pauses after success when work remains, offering continue/finish. Merges continue on each arrival without automatically waiting for other ideas. Loops need a reachable terminal outlet.

Reference files may be images, PDFs, text, audio, video or other types, up to 50 MiB each. Flowable compile/start requests have a 70 MiB total limit including Base64 and JSON overhead, so keep combined attachments within that request limit. Browser support determines previews. Other types can be opened through the Windows local service in a compatible installed application; support for a MIME type does not install a viewer. Names and content are saved with the workflow. Generic project exports put resources in `assets/` and retain relative paths in the main JSON.
Without a default association, the system application chooser opens. Scripts and shortcuts always ask for a viewing application. Local applications open a temporary copy; edits do not automatically update the project. Select the modified file again to save it.

## 4. Bind interfaces and match variables automatically

Select **Execution and human decisions** on an investigation or **Interface binding** on an action. Choose the module and function; registered interfaces show signatures. Importable names can also be entered manually. Leave Job topic empty to use the node ID; topics must be unique within the workflow.

Text-only conclusions need no binding. Problem Solved and Escalation do not bind functions. Actions support no arguments and `None` returns. Put decisions in investigations and return `True`/`False`, `yes`/`no`, or `{"next":"yes", ...}` / `{"next":"no", ...}`. A compatible outgoing flow ID selects its entire Yes/No group, not only that flow. Arbitrary numbers or strings are not interpreted by truthiness.

The worker matches signature parameters in this order: legacy explicit mappings when present, same-name workflow variables, a unique same-name field in upstream results, then defaults. No-argument functions run directly; positional-only parameters and `async def` are supported. Missing or ambiguous values report the parameter name rather than guessing.

For `inspect_voltage(device_id, threshold=24)`, initial variables `{"device_id":"M01"}` supply the device and preserve the default threshold. A return value `{"next":"yes","voltage":22.6}` is saved as a **workflow variable named after the node ID**. A downstream `voltage` parameter finds the unique field automatically. Two results containing `voltage` are ambiguous: engineers should use clear business names or an entry wrapper. A parameter named after a node ID receives its full result; top-level variables take precedence over result fields.

If the existing function returns only raw data, an engineer can add a thin entry wrapper that reuses acquisition and adapts it to the Yes/No protocol (assuming numeric readings here):

```python
from machine.sampling import read_voltage

def inspect_voltage(device_id, threshold=24):
    voltage = read_voltage(device_id)
    return {'next': 'yes' if voltage < threshold else 'no', 'voltage': voltage}
```

Save it as `workflow_api.py` at the project root, register module `workflow_api`, and bind `inspect_voltage` on the investigation. Adapt parsing/assessment to the actual return type; keep the original project in place.

No code or parameter expressions are needed in the panel. Selecting a different interface clears old mappings. Existing mappings still support `$NodeID.field`, `$variable`, `$` (all variables), and `$$` (escaped dollar sign). Workflow function results must be JSON serializable.

**Registration and worker interpreters are separate settings.** Registration configures discovery/debugging only. Real execution needs a worker started with an interpreter containing both business dependencies and the official client, with `--project` pointing to the business project.

## 5. Deploy and execute for real

Prepare Java 21, Maven 3.9 and a Python environment for the official client:

```powershell
# Inside flowable-runtime
mvn package
java -jar target/diagnostic-flowable-1.0.0.jar

# At repository root; an existing business environment may be used instead
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
```

If Maven dependencies are unavailable but an executable jar already exists, `scripts/rebuild-flowable-local.py` can reuse its dependencies to rebuild Java classes and resources offline; see `--help`. Standard builds/releases still use `mvn package`.

Keep the backend and frontend from section 2 running. Java defaults to `http://127.0.0.1:8080`, with demo credentials `diagnostic / local-demo`. The proxy and worker share `FLOWABLE_URL`, `FLOWABLE_USER`, and `FLOWABLE_PASSWORD`. Configure appropriate credentials and access control for deployments.

1. Open **Flowable Execution**, export the execution package and extract it. `source.bpmn` is the editable snapshot, `workflow.bpmn20.xml` the engine definition, and `bindings.json` the interface bindings. Do not edit the engine definition as your source diagram.
2. Start the worker using the environment with the business dependencies:

   ```powershell
   D:/equipment/diagnostics/.venv/Scripts/python.exe backend/flowable_worker.py D:/exports/bindings.json --project D:/equipment/diagnostics
   ```

   Install the official client in that environment too. Repeated `--project` options add each root and `src/`. The worker does not read the registered interpreter or provide discovery/debugging's per-call subprocess isolation. Avoid conflicting module names and relative file paths that assume the debug working directory.

3. Enter an initial variable JSON object, e.g. `{"device_id":"M01"}`, and deploy/start from the drawer.
4. Refresh execution results to inspect visited nodes, results, failures, human waits and execution details. Results containing a `chartSvg` string can display that SVG; arbitrary local file paths do not automatically become charts.
5. Re-export and start matching workers after changes to bindings, connections, groups or ordering. Existing instances still need their old workers. Restart workers after business code changes too. Workers with different business configurations must not subscribe to the same topics.

Without a running worker, automatic tasks wait; Python is not launched automatically. Interface exceptions are task failures; inspect worker logs and execution details. Retries may repeat calls, so equipment actions need suitable idempotency.

Flowable compilation currently supports one top-level process, one plain start and the project's diagnostic nodes. Subprocesses, complex events and ordinary parallel gateways are rejected, as are condition expressions/default flows: use investigation Yes/No results. The offline scaffold's broader scope does not imply Flowable deployability.

## 6. Human decisions, component fallback and rechecks

An investigation with **Human decision / confirmation** enabled can wait directly without Python. If bound, the interface runs first, then waits for review. This switch appears only on investigations. Offline action completion confirmation is a separate mechanism.

Existing business decisions can request human fallback through the supplied component, without enabling the switch:

```python
from diagnostic_components import decision

@decision(instructions='Compare the curve with the rated voltage')
def inspect_voltage(device_id, threshold=24):
    raise NotImplementedError('Engineer must implement acquisition and assessment')
```

Alternatively extend `DecisionComponent` and implement `decide`. An unimplemented component or explicit `NotImplementedError` inside the component produces a `HumanDecisionRequest`; a plain undecorated function raising it does not automatically fall back. `pass`/`None` does not mean unimplemented; other exceptions remain failures. Return the request object directly, without manually JSON-encoding it. Sync/async are supported. The worker supplies the component's import path; independent execution must add this repository's `backend` directory.

Refresh the drawer to view evidence, assessment instructions and choices; confirm Yes/No to continue. Escalation waits for review before ending. Serial success with remaining work offers continue/finish.

While waiting for an investigation decision or escalation review, select an earlier executed node, supply a reason and optional revised input variables, then recheck. This preserves history, old values and reasons, clears results that need recomputing, and executes again. It does not undo equipment actions; actions may run again. The current node, unexecuted nodes and completed instances cannot be arbitrary recheck targets. Running automatic nodes do not offer pause/intervention.

## 7. Save, move and import projects

- **Export diagnostic project**: one version 4 `workflow.json` plus separate resources. Keeps content, bindings, dependencies, groups, order and mode; omits layout, size, colors and fonts.
- **Import project directory**: choose the extracted directory to load JSON and relative resources together. If importing JSON alone reports missing resources, import the directory instead. Layout is regenerated; existing attachments need no upload.
- **Export full BPMN**: complete editing snapshot, retaining layout.
- **Export Python skeleton**: the same JSON and `assets/`, plus modules, sample input, instructions and implementation map; no additional `source.bpmn`.
- **Flowable execution export**: a separate engine package containing the three files in section 5.

Move generic projects as a whole directory; do not replace resource paths with absolute paths. Older JSON is importable; unclassified legacy branches need explicit Yes/No groups. BPMN extensions use the `flowable:` prefix. Editor changes support undo/redo.

## 8. Complete the offline Python implementation

Extract into a new directory and use Python 3.10+ with only the standard library:

```powershell
python runner.py
python runner.py --data inputs.json --no-images
```

Read `IMPLEMENTATION.md` to locate functions by node ID. Each function's comments identify its node ID/type/name/full content, inputs, outputs, outlets and file call relationships. `node_N` depends on export order: migrate implementations by IDs in `HANDLERS`.

| File                   | Business implementation and default behavior                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| acquisition.py         | Acquire raw data; otherwise show acquisition instructions and accept text/JSON or `@JSON-file-path`                        |
| parsing.py             | Parse, validate and convert units; passes input through by default                                                         |
| display.py             | Business charts; defaults to showing data/reference paths and trying the browser; `--no-images` disables automatic opening |
| diagnosis.py           | Automatic decisions; otherwise show instructions and ask Yes/No                                                            |
| actions.py             | Real actions; otherwise require manual completion and explicit `yes`                                                       |
| routing.py / runner.py | Groups, dependencies, scheduling, history, failure and resume; normally unchanged                                          |

The call chain is `runner → acquisition → parsing → display → diagnosis → routing → successor`; actions use `runner → actions`. Explicitly import existing business packages inside the relevant handlers and make them importable in this Python environment. Only deliberate unimplemented placeholders request manual fallback; other exceptions stop execution. Parsing/display errors do not become manual success.

Copy `inputs.example.json` to `inputs.json`, replace values and keep only known nodes. `--data` or `run(supplied={NodeID: raw_data})` bypasses acquisition for those nodes while retaining parsing/decisions. Replace `Context.ask/show` to integrate another UI. `context.data[NodeID]` stores `raw/parsed/result`. Serial pauses return `state`; resume with `run(..., resume=state, success_action='continue'|'finish')`. The default limit is 1000 steps (`--max-steps`); implement function-level timeouts yourself.

Offline execution supports plain nested subprocesses and exclusive choices. Condition text is displayed, never executed as code. Outcomes include Problem Solved, Escalation, Jump, failure or a serial pause. Jump is a handoff, not execution of another workflow; implement that integration explicitly. Regenerate into a new directory and migrate by ID to preserve business code.

## 9. Troubleshooting

| Symptom                               | Check                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| Python Projects cannot connect        | Backend is running, port and proxy match                                                   |
| Interface not found                   | Root, entry module, `__all__`, interpreter and dependencies; refresh after changes         |
| Simulation moves but execution stalls | Simulation only animates tokens; check Java, backend, matching bindings/worker/topics      |
| Missing/ambiguous parameter           | Signature, initial variables and executed upstream results; remove conflicting field names |
| Export rejected                       | Reported node ID, required content, groups, terminal outlet and supported constructs       |
| Result cannot route                   | Return explicit Yes/No, not `None` or ordinary data                                        |
| Reference cannot open                 | Import the entire directory, check files and installed applications                        |
| Action repeats after recheck          | Recheck reruns rather than undoing; implement idempotency                                  |

See [Python integration details](../backend/README.md) and [Flowable technical notes](../backend/FLOWABLE.zh-CN.md). Current grouping/automatic matching rules here supersede exclusive-routing/manual-mapping instructions in older example sections.
