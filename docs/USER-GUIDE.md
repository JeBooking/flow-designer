# Diagnostic workflow user guide

[English](USER-GUIDE.md) | [中文](USER-GUIDE.zh-CN.md)

Start with your own Python business project. Paths, modules, classes and methods below are placeholders: replace them with real values. The platform neither creates business implementations nor installs business dependencies.

## 1. Responsibilities

The diagram defines dependencies and diagnostic paths. Python interfaces perform acquisition, computation, equipment access and remediation. Flowable owns real scheduling, human waits and history. **Python projects** registers and debugs interfaces; **Diagnostic execution** runs the current diagram. Structural simulation only animates tokens and does not execute Python.

## 2. Prepare once, then start each run

Prepare Java 21, Maven 3.9, Python 3.9+, Node and pnpm. From the repository root:

```powershell
pnpm install
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
cd flowable-runtime
mvn package
cd ..
```

This builds `flowable-runtime/target/diagnostic-flowable-1.0.0.jar` and installs the official `flowable.external-worker-client==1.0.2`. On non-Windows systems use `backend/.local/venv/bin/python`. Reuse existing environments. Install business dependencies separately in the registered business interpreter. The launcher does not install dependencies or download Java/Python.

For each run, use:

```powershell
pnpm dev
```

Open `http://127.0.0.1:5173/vue-bpmn-designer/`. The launcher manages the frontend, local backend (8765) and local Flowable (8080). It reuses services only after identity, authentication and configuration checks. Startup failures point to `backend/.local/logs/`. `JAVA_HOME` selects Java and `PYTHON` selects the platform interpreter; otherwise the local venv is preferred before PATH.

Flowable defaults to `http://127.0.0.1:8080` with `diagnostic` / `local-demo`. Set `FLOWABLE_USER` and `FLOWABLE_PASSWORD` as needed. An explicitly set `FLOWABLE_URL` connects only to that external engine and never starts a local replacement. A reused backend must use the same engine URL.

With an existing `dist/index.html`, use `pnpm start` and open `http://127.0.0.1:8765/vue-bpmn-designer/`. Build using `pnpm build`. `pnpm dev:frontend` starts only the frontend for development.

## 3. Register your Python project

Open **Python projects** and fill in:

| Field | Placeholder | Meaning |
| --- | --- | --- |
| Project directory | `D:/your-project` | Existing business project root |
| Entry module | `your_package.api` | Importable module name, not a filename |
| Interpreter | `D:/your-project/.venv/Scripts/python.exe` | Python with business dependencies installed |
| Class or factory (optional) | `YourDevice` | Actual class/factory name; leave blank for module functions |
| Name (optional) | Your equipment diagnosis | A recognizable label |

Registration neither copies the project nor installs dependencies. Relative paths resolve from the repository root. Imports include the project's `src/`, root and parent; calls use the project root as working directory. Module functions follow `__all__`, or public functions defined in the entry module when it is absent.

Class discovery inspects signatures without creating an instance. Constructor inputs come from same-name startup variables or defaults at runtime. Factories with a return-class annotation also support discovery without invocation. Unannotated factories are temporarily invoked with defaults; add a return-class annotation when required inputs exist.

## 4. Debug interfaces and bind your diagram

Fill debug inputs from the real interface signature and call it to check the interpreter, dependencies and equipment connection. Consecutive debug calls share a session; **Reset session** discards objects and results. Debugging calls real business code, so follow equipment procedures. Debug sessions are separate from workflow sessions.

Draw your own workflow, or import your saved BPMN, `workflow.json` or project directory. Save current work before importing. Configure diagnostic content, references and Yes/No connections using section 8. On each node select its registered **Python project** and **Call interface**. Module/class entry settings come from registration and need not be repeated per node.

Investigations return explicit `True`/`False`, `yes`/`no`, or a dictionary with `next`. Conclusions may contain text only. Actions can take no inputs and return `None`. Final nodes have no business binding.

## 5. Parameters and native objects

Matching uses compatible legacy mappings, same-name startup variables, complete results stored under a node ID matching the parameter, unique same-name upstream dictionary fields, then defaults. Missing or ambiguous values identify the parameter; a signature alone cannot supply data.

For instance, if your project implements `collect()` and `assess(reading)`, name the acquisition node's ID `reading` to supply its complete raw result. These method names illustrate your code, not platform-provided interfaces. Positional-only parameters, async interfaces and no-argument functions are supported.

One workflow's calls to the same project share a persistent isolated Python process and class instance; module functions retain globals too. Workflows are isolated, native references cannot cross project processes, and the business project manages parallel thread safety. Raw objects stay in Python. The UI receives JSON display projections, types and text representations; `repr` is never substituted for the original object in downstream calls.

## 6. Start the current workflow

1. Open **Diagnostic execution** and check the current diagram's nodes, connections and bindings.
2. Enter startup inputs from registered class/factory signatures, leaving blanks for defaults. Add name/value rows for extra data. If needed expand advanced initial-variable JSON and enable **Use JSON instead of form**; only JSON is used, without merging the form.
3. Click **Start execution**. The backend validates the definition, prepares its matching worker automatically, and deploys/starts the process. Normal execution needs no downloaded bundle or manual worker command.
4. Follow automatically updated canvas states, executed paths and result cards. Handle human waits by confirming, choosing a branch or rechecking. Structural simulation animation is not evidence of real execution.

Each start creates a new instance using the current diagram and does not reuse debug objects. Editing the diagram does not change running instances. States come from actual Flowable execution; distinguish running, human waits, task errors and completed processes.

## 7. Inspect results and errors

Result cards show business return values. A chart appears only when a result dictionary contains a `chartSvg` string. Returning a file path does not display an image automatically; the platform does not invent business curves as execution results.

Raw activity history, variables and exceptions live in the collapsed **Raw execution details**. Expand failure details for the Python traceback and follow the business file/call location. Service logs live in `backend/.local/logs/`; worker logs use `backend/.local/executions/<content-hash>/<launch-uuid>.log`. The directory identifies the execution definition's content hash, and each worker launch has a separate UUID log. A path without a matching branch is a diagnostic failure, distinct from a Python exception.

## 8. Design diagnostic nodes and investigation paths

### 8.1 Node content and connections

Every diagnostic node has a name and details. New nodes have no default names. Details generate a summary that fits the node dimensions; manual names are preserved, while automatic summaries adjust when resized. **General → Node type** is read-only. For conclusions, a name entered without content is copied into the conclusion content, and content entered without a name generates a name summary.

Investigations also require data to inspect, acquisition instructions, an assessment method, and a reference file. Describe actions and remediation in their details, and state conclusions explicitly. You can export an unfinished draft, although it may not qualify for execution.

The main connection sequence is Start → Investigation; Investigation Action → Investigation; Investigation → Conclusion → Remediation; completed remediation can reach Problem Solved. Investigations cannot connect directly to Remediation or Problem Solved, and Remediation cannot connect directly back to Investigation. Jump represents a handoff whose target must be implemented by the integration; node text alone does not execute another diagram.

Investigation uses a diamond, Investigation Action an upright trapezoid, Conclusion a rectangle, Remediation an inverted trapezoid, Jump an ellipse, Problem Solved a triangle, and Escalation a star. Deep Diagnosis retains its existing style. Resize with the node border. Validation reports illegal connections and missing content.

### 8.2 Yes/No groups and dependencies

An investigation can have Yes and No output groups, each connecting to multiple distinct nodes. Either group may be absent. Change a connection's canvas label to `是`, `否`, `yes`, or `no` to change its group; English is case-insensitive. Other labels are rejected.

Connect independent methods as siblings in the same group after their common prerequisite. If B requires A to finish first, connect B after A. Drawing one sibling connection before another does not give it priority in parallel mode.

A judgment with no matching successor records a failed path. This is a normal diagnostic outcome, distinct from a Python exception, which is a task-execution error.

### 8.3 Parallel and serial modes

Select the process and choose its investigation mode:

| Situation                            | Parallel                                                                  | Serial                                                        |
| ------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Several successors in the same group | Start them concurrently, with no priority                                 | Try them in order                                             |
| A path has no matching successor     | End and record that path; other active paths continue                     | Move to the next pending path                                 |
| A path reaches Problem Solved        | Record its success; other active paths continue under their existing flow | Pause any remaining paths and let the user finish or continue |
| All paths fail                       | The investigation fails                                                   | The investigation fails                                       |

In serial mode, select a connection and enter a number under **Execution order**. Lower numbers run first; missing or equal numbers retain connection order in the definition. Parallel mode ignores this setting. Multiple remediation nodes may connect to one Problem Solved node; each arrival proceeds without requiring an extra gateway that waits for every path. Loops need a reachable exit.

Parallel nodes may call methods on one object simultaneously. The business project controls whether concurrent access is valid and how equipment access or shared state is protected.

## 9. Handle human waits, rechecks, and interruptions

For registration, import steps, triggers, and review actions for eight diagrams, see [section 13: automatic decisions and human handoff](#13-examples-automatic-decisions-and-human-handoff) in this guide.

### 9.1 Request a human decision

Enable **Human decision / confirmation** on an investigation. With no Python interface it waits directly; with an interface it executes that interface before requesting review. This switch belongs only to investigations that make a judgment and choose a branch.

When the workflow waits, inspect automatically updated **Diagnostic execution**, inspect the evidence and assessment instructions, select Yes or No, and continue. Escalation also waits for human review. Serial success with remaining paths offers **Finish investigation** and **Continue remaining paths**.

### 9.2 Request human help for unimplemented judgment code

Engineers can explicitly request human handling with the supplied decision component:

```python
from diagnostic_components import decision

@decision(instructions='Confirm whether the voltage curve is below its rating')
def inspect_voltage(data):
    raise NotImplementedError('Automatic judgment is not implemented yet')
```

The component's human request is handled by the UI without additionally enabling the human switch. You can also extend `DecisionComponent` and implement `decide`, or return `HumanDecisionRequest` directly. Return the request object itself.

Only an unimplemented component or an explicit `NotImplementedError` handled by that component invokes this fallback. Raising that exception in an ordinary function remains a task error. `pass` or `None` does not mean unimplemented. Synchronous and asynchronous functions are supported. Class methods are better served by the component base class; the decorator uses a plain function's first argument or its `data` argument as evidence.

The worker supplies the import path for `diagnostic_components`. Add this repository's `backend` to the import path when running business code independently. Optional request choices should be Yes/No groups or match all successor flow IDs. This protocol applies only to investigation nodes.

### 9.3 Recheck an earlier node

During an investigation or escalation human wait, select a **previously executed node**, provide a reason and optional recheck input variables, then click **Recheck**. The system retains previous history, results, and the reason; it clears results requiring recomputation and runs again from the selected node.

Rechecking does not undo equipment actions or restore an older Python object state. It reruns methods on the current instance, and actions may occur again. The current node, unvisited nodes, and completed instances are not arbitrary recheck targets. Running automatic tasks do not expose this intervention. At a serial-success pause, choose continue or finish rather than recheck.

### 9.4 Stop, restart, and update

Closing the execution drawer pauses polling; the backend workflow continues. Reopening it resumes monitoring in the same panel. Refreshing the page or recreating the modeler does not restore monitoring of the previous instance. Ctrl+C stops services and workers owned by the launcher; reused external services remain running. Exiting the application and rechecking cannot undo equipment commands already issued. Arrange active equipment and investigations according to business procedures.

After a task reaches dead letter, **Run the current diagram again** asks for confirmation and starts a new instance from the current diagram. It does not cancel the old instance or undo completed equipment actions, and actions may run again. Previous instance IDs remain available in the current panel; record them before refreshing the page or recreating the modeler.

Flowable saves progress and display results, not the entire Python memory. Restarting the worker or business subprocess loses its device instances. Continuing an old workflow then reports session loss; neither `repr` nor historical display data can reconstruct those objects.

Account for active investigations before updating business code. Reload interfaces after editing code; starting a new workflow automatically prepares its matching worker. Binding, connection, group or order edits apply to new starts; existing instances retain their definition. Do not terminate their workers merely to update a new diagram. Restarting services loses current sessions. The worker releases business sessions after observing process completion; unfinished failed processes retain sessions for subsequent handling.

## 10. Save workflows and reference files

### 10.1 Choose a format for your purpose

| What you need                                                     | Command                                          | Output                                           |
| ----------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
| Diagnostic logic and resources for moving and restoring           | **Export diagnostic project**                    | ZIP containing `workflow.json` and `assets/`     |
| Complete editing state, including layout, size, colors, and fonts | **Export complete BPMN with layout and styles**  | Full BPMN editor snapshot                        |
| Run the current diagram on Flowable                               | **Diagnostic execution → Start execution**        | Actual process instance and online results        |
| Offline Python code for further implementation                    | **Export Python skeleton**                       | Code and resources described in section 11       |

A portable diagnostic project's main definition is version 4 `workflow.json`. It keeps node content, bindings, connections, Yes/No groups, serial order, and investigation mode. It omits layout, dimensions, colors, and fonts. Resources live separately in the directory; JSON records relative paths, embeds no file data, and adds no duplicate BPMN file.

Move the complete directory together. Restore it with **Import project directory**, which reads JSON and resources and creates a layout. Importing `workflow.json` alone can still restore nodes and connections, but its resources are separate. If resources are reported missing, import the full directory instead. Older JSON versions are accepted; older connections without an explicit Yes/No group need updating.

These exports do not package the business Python project, interpreter, or local registrations. On another computer, prepare the business project and dependencies, register it again, and start the required services.

### 10.2 Add and open reference files

Select a file under a node's **Reference file**. Common images, PDFs, text, CSV, Markdown, JSON, and some audio/video can be previewed in the UI, depending on browser support. Active documents such as HTML, SVG, and XML, and other formats, are opened through the Windows local service in a local application.

If no default association exists, the system application chooser opens. Scripts, executables, and shortcuts always require choosing a viewing application. External applications receive a temporary copy: edits do not automatically update the project. To replace a reference, save the edited file and select it again.

Each reference file is limited to 50 MiB. Combined deployment/start requests are limited to 70 MiB, including encoding and JSON overhead, so several large files can also exceed the total. Portable export still writes them as separate resources referenced by relative paths.

If business Python code needs the same file, read it from the appropriate project path and deploy it with that project. Attaching it to a node does not automatically add a file argument or modify paths in Python code.

## 11. Alternative execution and advanced settings

### 11.1 Structural simulation

**Start structural simulation** only animates BPMN tokens. It permits nodes without Python bindings and does not validate functions, parameters, real judgments, or diagnostic serial-success pauses. Use **Diagnostic execution** to check business behavior.

### 11.2 Export an offline Python skeleton

Use **Export Python skeleton** when engineers will implement business logic from the diagram's content. It retains the same `workflow.json` and resources, adding a runner and business modules. It does not automatically execute saved external-module bindings.

Extract to a new directory and use Python 3.10+:

```powershell
python runner.py
python runner.py --data inputs.json --no-images
```

Read the generated `IMPLEMENTATION.md` first, locating business functions by node ID. Each function begins with node content, inputs, outputs, call relationships, and successors.

| File                      | Work to implement                                                               |
| ------------------------- | ------------------------------------------------------------------------------- |
| `acquisition.py`          | Raw data acquisition                                                            |
| `parsing.py`              | Parsing, validation, and unit conversion; defaults to returning input unchanged |
| `display.py`              | Charts and reference-file display                                               |
| `diagnosis.py`            | Automatic judgment                                                              |
| `actions.py`              | Business actions                                                                |
| `routing.py`, `runner.py` | Generated flow control, usually left as supplied                                |

Explicit `NotImplementedError` placeholders in acquisition, judgment, and actions invoke command-line human fallback. Other exceptions stop execution; parsing/display errors do not count as success. Default actions require manual completion followed by `yes` confirmation.

Copy `inputs.example.json` to `inputs.json` and provide known acquisition data by node ID to skip that acquisition and continue parsing and judgment. Command-line acquisition also accepts text, JSON, or `@JSON-file-path`. `--no-images` disables automatically opening references. The default limit is 1,000 steps, adjustable with `--max-steps`; the business project manages function timeouts.

The offline call chain is `runner → acquisition → parsing → display → diagnosis → routing → successor`; actions are called through `runner → actions`. Engineers can import existing business packages from those functions. `Context.ask/show` can adapt the interface, and `context.data[node_id]` holds `raw/parsed/result`. Programmatic callers can use `run(supplied={node_id: raw_data})`. After a serial pause, pass the returned `state` into `run(..., resume=state, success_action='continue'|'finish')`.

The offline skeleton also supports ordinary nested subprocesses and exclusive selection. Condition text is displayed, not evaluated. Jump is a handoff and does not automatically run its target. This wider scope does not mean the current Flowable compiler can deploy the same diagram.

Regenerate into a new directory and migrate implementations by stable node ID to avoid overwriting business code. `node_N` numbering changes with export order.

### 11.3 Optional operations settings (outside normal use)

| Situation                                              | Configuration                                                                                                                             |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Registration file is elsewhere                         | Add worker option `--registry D:/config/projects.json`                                                                                    |
| Run an older, unregistered module                      | Supply roots with repeatable `--project D:/equipment/diagnostics`; without a matching registration, execution uses the worker interpreter |
| Same module name is registered in several directories  | Select the current root with `--project` to resolve ambiguity                                                                             |
| Business calls need more time                          | Add worker option `--timeout 600`; for debug calls adjust the backend's `--timeout`                                                       |
| Maven cache is incomplete but an executable JAR exists | `scripts/rebuild-flowable-local.py` can rebuild from its existing dependencies; Maven remains the normal build method                     |

See [Flowable technical documentation](../backend/FLOWABLE.md) for full commands and environment settings. Desktop plotting libraries that require a main thread or interactive desktop should be launched in a suitable desktop process by the business entry; business interfaces are invoked on worker threads.

The current Flowable compiler supports one top-level process, one plain start event, and this project's diagnostic nodes. It rejects subprocesses, complex events, ordinary parallel gateways, handwritten conditions, and default flows. Use diagnostic connections and investigation mode for parallelism, and investigation Yes/No results for judgments.

Legacy explicit mappings still support `$NodeID.field`, `$variable`, `$` for all variables, dictionary/array paths, and `$$` for a literal dollar sign. New integrations normally do not need them.

## 12. Find the right place to troubleshoot

| Symptom                                 | First check                                                                  | Next step                                                                                        |
| --------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Python projects cannot connect          | Backend, page origin, and proxy port                                         | Verify addresses using section 2                                                                 |
| Registration cannot import the module   | Project root, module name, interpreter, and dependencies                     | Confirm importability in that interpreter; use a module name, not a file path                    |
| Required interface is absent            | Public export, re-export, and factory return-class annotation                | Update exports/annotations, then reload interfaces                                               |
| Missing or ambiguous arguments          | Parameter names, node IDs, startup inputs, and executed results              | Establish a unique source using section 5; signatures alone cannot supply values                 |
| Animation works but execution does not  | Structural simulation versus actual execution; whether the worker is running | Run pnpm dev and choose Diagnostic execution → Start execution                               |
| Automatic tasks remain waiting          | Java service state, startup errors and worker logs                                        | Inspect `backend/.local/logs/` and `backend/.local/executions/<content-hash>/<launch-uuid>.log`                                             |
| Worker already exists                   | Conflicting backends or manually started workers                                        | Keep one backend manager and stop only identified owned conflicts                                |
| Unexpected routing                      | Explicit judgment value and matching output group                            | Distinguish a normal failed path from a Python task error                                        |
| Python task fails                       | Original traceback in failure details                                        | Follow its business file and call location; repeating an action can affect equipment again       |
| Session is lost                         | Worker or business subprocess restart                                        | Handle the actual equipment state, then start a new investigation; history cannot restore memory |
| Missing or unopenable reference         | JSON-only import or missing local application                                | Import the full directory or select a supporting application                                     |
| Recheck did not restore equipment state | Whether recheck was mistaken for undo                                        | Recheck reruns logic; it does not rewind equipment or object state                               |

For lower-level interface and runtime details, see [Python integration](../backend/README.md) and [Flowable technical documentation](../backend/FLOWABLE.md).

## 13. Examples: automatic decisions and human handoff

This independent Python project demonstrates automatic routing, human review, component fallback,
and an intentional Python failure. It has no factory and requires no third-party business dependencies.
It uses supplied voltage data; it does not acquire data from or operate equipment.

### 13.1 Preparation and project registration

Complete the platform preparation in the [user guide](#2-prepare-once-then-start-each-run),
then run `pnpm dev` from the repository root. The launcher manages the required services and workers.

Open **Python projects** and register:

| Field | Value |
| --- | --- |
| Project directory | `backend/examples/manual_handling_project` (relative to the repository root) |
| Entry module | `manual_handling` |
| Interpreter | The executable path of your local Python 3.9+ interpreter |
| Class or factory | Leave blank; the entry points are module functions |
| Name | Any recognizable label, such as `Manual handling examples` |

Register this module even for the manual-only diagram: its later Record action calls
`record_result()`. The business interpreter does not need the Flowable SDK. The platform worker
supplies the import path for `diagnostic_components`; do not install it as a third-party dependency.

### 13.2 Import and start

Start with **05-decorator-fallback.bpmn** to see an unimplemented automatic judgment preserve its evidence and request human review.

1. Save your current canvas before importing.
2. Use the main designer's **Import BPMN or workflow.json** control and select one standalone `.bpmn`
   file from this project's [diagrams](../backend/examples/manual_handling_project/diagrams/) directory. These files are not entries in an execution
   example menu. Starting the app does not automatically replace your canvas with an example.
3. Select Check and inspect its **Python project**, **Call interface**, and **Human decision / confirmation**
   settings against the table below. Choose the registered project if the local registration has not
   been associated with the imported binding. Record must use the same project and `record_result()`.
   Manual-only Check intentionally has no Python binding.
4. Open **Diagnostic execution**, then click **Start execution**. The default voltage is `21.2` V.
   To demonstrate the automatic Yes branch, add an extra startup input named `voltage` with the
   numeric value `24` before starting a new execution. Leave it absent for the default No branch.

The manual-only diagram uses a static 21.2 V example in its node instructions. Its Check makes no
Python call, so a `voltage` startup input does not change that text or its example evidence.

Every diagram follows Start → Check. Yes goes through Conclusion → Record → Problem Solved;
No goes to Escalation. `record_result()` is only an example record step: it returns `None` without
writing files or touching equipment.

### 13.3 Eight diagrams and expected results

The human switch below refers to **Human decision / confirmation** on Check.

| Diagram | Check interface / human switch | Trigger | Expected result |
| --- | --- | --- | --- |
| [01-automatic.bpmn](../backend/examples/manual_handling_project/diagrams/01-automatic.bpmn) | `automatic_decision` / off | Returns Yes when `voltage >= 22`, otherwise No | Check routes automatically; `21.2` reaches Escalation, `24` reaches Problem Solved |
| [02-manual-only.bpmn](../backend/examples/manual_handling_project/diagrams/02-manual-only.bpmn) | No Python interface / on | Check is configured for direct human judgment | Waits for a human Yes/No choice without a Python call at Check |
| [03-bound-manual.bpmn](../backend/examples/manual_handling_project/diagrams/03-bound-manual.bpmn) | `collect_evidence` / on | Python returns evidence, then the node requests review | Shows evidence and waits for a human Yes/No choice |
| [04-base-fallback.bpmn](../backend/examples/manual_handling_project/diagrams/04-base-fallback.bpmn) | `base_fallback` / off | `DecisionComponent.decide` is not overridden | Component protocol requests human judgment |
| [05-decorator-fallback.bpmn](../backend/examples/manual_handling_project/diagrams/05-decorator-fallback.bpmn) | `decorator_fallback` / off | A function wrapped by `@decision` raises `NotImplementedError` | Decorator converts the unimplemented judgment into a human request |
| [06-explicit-review.bpmn](../backend/examples/manual_handling_project/diagrams/06-explicit-review.bpmn) | `explicit_review` / off | Explicitly returns a human judgment request | Waits for a human Yes/No choice without requiring the node's human switch |
| [07-ordinary-error.bpmn](../backend/examples/manual_handling_project/diagrams/07-ordinary-error.bpmn) | `ordinary_unimplemented` / off | An ordinary function directly raises `NotImplementedError` | Expected Python execution failure with traceback; no human review occurs |
| [08-empty-result.bpmn](../backend/examples/manual_handling_project/diagrams/08-empty-result.bpmn) | `empty_decision` / off | The function body uses `pass`, returning `None` | Expected `ValueError`: an investigation must return Yes/No; no human review occurs |

### 13.4 Handle the review card

Human handling appears in the **Diagnostic review** card inside the right-hand **Diagnostic execution**
drawer. It does not open a separate dialog automatically. If you close the drawer, open it again
yourself to resume monitoring the current execution.

For diagrams 02–06, read the evidence and reference/assessment instructions. When supplied by Python,
the default evidence is `voltage: 21.2`, `threshold: 22`, `unit: V`; the manual-only diagram supplies
its context through the node's instructions. Under **Next step**, select Yes or No, then click
**Confirm and continue**. The question is whether voltage is at least 22 V, so the default evidence
supports No. A human can select either branch to inspect its behavior.

- **Yes** continues through Conclusion and Record to Problem Solved.
- **No** reaches Escalation and waits again. Click **Confirm escalation and finish** to finish this
  escalation. This second wait also occurs for diagram 01 with its default automatic No result.
- Diagram 07 should show the Python failure. Expand **Original Python traceback** in the failure
  details to locate the intentional exception; this is not a successful fallback or a completed review.
- Diagram 08 should fail with `ValueError` because its investigation returns no branch decision.
  Inspect its traceback in the same failure details; it must not open a human review.

### 13.5 Boundaries

Only the component protocol turns an unimplemented judgment into human handling. A plain `pass` or
`None` return does not request human review, as diagram 08 demonstrates. Diagram 03
waits because its human switch is enabled, not because returning evidence itself implies fallback.

These examples cover investigation judgments. The execution UI currently has no unified form for
manually entering acquisition results or confirming completion of arbitrary business actions.
The Yes/No review must not be presented as either of those capabilities. This guide describes the
expected behavior; it does not claim that the examples have been run on your machine.

For the project files and standalone instructions, see the [example project README](../backend/examples/manual_handling_project/README.md).
