# Diagnostic Workflow User Guide

[简体中文](USER-GUIDE.zh-CN.md) · [Project overview](../README.md)

This guide takes you from an existing Python project to a workflow that calls its functions or object methods. Follow sections 1–6 to complete a real run. Later sections explain branching, human decisions, recovery, file storage, and alternative ways to run the diagram.

The walkthrough uses the included device-voltage example. It collects a Python object, checks for low voltage, then restores and verifies the device. All equipment operations in this example are simulated. Once it works, replace the example directory, module, and class with your own project.

## 1. Understand the parts you will run

The diagram defines dependencies and execution paths. Python interfaces perform the business work: acquisition, calculation, equipment access, state changes, and remediation. Flowable advances the workflow using node results and stores its progress, waiting states, and history.

A real run uses four cooperating programs. Keep them running while they are needed:

| Program          | Responsibility                                                               | When to start it                                                 |
| ---------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Frontend         | Edit the diagram, bind interfaces, and display results                       | When you open the platform                                       |
| Local backend    | Register Python projects and provide debugging and execution services        | Before registering a project                                     |
| Flowable service | Schedule nodes, branches, and human waits                                    | Before running the complete workflow                             |
| Python worker    | Receive Flowable tasks and call Python in the business project's environment | After exporting the execution bundle, before starting a workflow |

Use **Python projects** to register and debug interfaces, and **Flowable execution** to run the complete diagram. **Start structural simulation** only animates BPMN tokens. It does not execute Python or prove that interfaces and diagnostic rules work.

## 2. Prepare the environment and open the platform

### 2.1 First-time setup

Running from source requires Node.js 22, pnpm, Python 3.9+, Java 21, and Maven 3.9. Install business-specific Python packages in the business project's own interpreter environment.

From this repository's root directory, prepare the frontend dependencies, worker environment, and Java service:

```powershell
pnpm install
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
mvn -f flowable-runtime/pom.xml package
```

Reuse existing environments where available. `backend/.local/venv` contains the official Flowable client used by the worker. It can be separate from the business project's virtual environment: the worker reads the registration and uses its interpreter for business calls.

### 2.2 Start the editor and local backend

Open two terminals, both in this repository's root directory.

Start the backend in the first terminal:

```powershell
python backend/server.py
```

Start the frontend in the second:

```powershell
pnpm dev
```

Open the address printed by Vite. By default, `/api` requests go to `127.0.0.1:8765`. The backend accepts frontend ports 5173 and 5174 by default. For another port, specify the page origin when starting the backend, for example:

```powershell
python backend/server.py --origin http://localhost:5175
```

Alternatively, run `pnpm build-only`, then open `http://127.0.0.1:8765/vue-bpmn-designer/` through the backend. Vite need not remain running in that case.

### 2.3 Start Flowable

Open another terminal. From the repository root, enter the Java service directory and start it:

```powershell
cd flowable-runtime
java -jar target/diagnostic-flowable-1.0.0.jar
```

The default address is `http://127.0.0.1:8080`; the local example credentials are `diagnostic` / `local-demo`. If you change them, the backend and worker must use matching `FLOWABLE_URL`, `FLOWABLE_USER`, and `FLOWABLE_PASSWORD` environment variables.

You can now register projects and edit diagrams. Start the worker in section 6, after exporting its `bindings.json`.

## 3. Register a Python project and check its interfaces

### 3.1 Register the device example

Click **Python projects** in the toolbar and enter:

| Field                               | Value for this example             | Meaning                                                                                                |
| ----------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Project name (optional)             | Device voltage example             | A recognizable display name                                                                            |
| Project directory                   | `backend/examples/session_project` | Business project root; relative paths start at this repository's root                                  |
| Entry module                        | `device_session`                   | An importable Python module name, not a file path                                                      |
| Session class or factory (optional) | `Device`                           | The class whose methods this example calls                                                             |
| Python executable                   | Leave blank                        | Uses the backend interpreter; for your own project, supply its actual virtual-environment `python.exe` |

Click **Register project**. The interface list should contain `ready`, `collect`, `is_low`, `restore`, `verify`, and `restore_and_verify`.

Registration does not copy or modify the business project. Paths refer to **the computer running the backend**. A `src/` project layout is supported: the project's `src/`, root, and parent directory are added to the import search path. Business calls use the project root as their working directory.

### 3.2 Make consecutive calls to check state retention

In the same registered project:

1. Select `collect`, leave initialization fields blank, and click **Call Python function**. It uses device `M01` and threshold `24`, returning a `Reading` object with voltage `22.6`.
2. Select and call `restore`. It changes the current device instance's recovery state and returns `None`, displayed as `null`. This is a normal void return.
3. Select and call `verify`. It collects again on the same instance, obtains voltage `24.5`, and returns `true`.
4. Click **Reset debug session**, then call `verify` again. The new instance has not been restored, so the result should be `false`.

These steps establish that imports work, synchronous and asynchronous methods run, consecutive calls reuse the instance, and resetting starts with fresh state.

Input fields come from the Python signature. Numbers, booleans, `null`, arrays, and objects are parsed automatically; other input is text. Enter `""` for an empty string. Leave optional fields blank to preserve Python defaults. You do not enter `self` or the object's internal attributes. Variadic `*args` and `**kwargs` have advanced fields that ordinary calls need not use.

Do not manually construct the `Reading` required by `is_low` in this single-interface check. The workflow will pass that object in the next section. Copying its displayed text back into a field does not recreate the native object.

Debugging calls the selected interface, not the complete diagram, and uses an instance separate from real workflow runs. Switching projects, reloading interfaces, or unregistering closes the corresponding debug session. Calls time out after 120 seconds by default; adjust this with `python backend/server.py --timeout 600`. A timeout closes that session.

### 3.3 Replace the example with your own project

Suppose `Device` is defined or exported in `D:/equipment/diagnostics/machine/api.py`. Set the project directory to `D:/equipment/diagnostics`, entry module to `machine.api`, session class or factory to `Device`, and executable to the interpreter actually used by that project.

There are three entry styles:

| Existing interface                                              | Session class or factory field | How it is called                                                                 |
| --------------------------------------------------------------- | ------------------------------ | -------------------------------------------------------------------------------- |
| Ordinary module functions                                       | Leave blank                    | Call the module's public functions                                               |
| An existing class, such as `Device`                             | Class name                     | Create an instance per investigation and call its public methods                 |
| A factory returning a business object, such as `create_session` | Public factory name or path    | Call the factory once per investigation, then call the returned object's methods |

Without `__all__`, function discovery lists public functions defined in the entry module. Use `__all__` to list functions re-exported from other modules. Instance-method signatures omit `self`.

Registering a class inspects its methods without constructing it, so required constructor parameters are supported. A factory with a return-class annotation also supports discovery without being called, as in `create_session(...) -> Device`. A factory without that annotation is called temporarily with defaults to discover its methods. If such a factory has required parameters, add a return-class annotation first.

After changing code or signatures, click **Reload interfaces**. Registrations are stored in `backend/.local/projects.json`. **Unregister (keep files)** removes only the registration, not the business project.

## 4. Import the example workflow and inspect its bindings

Click **Import project directory** and select this repository's `backend/examples/session_project` folder. It includes `workflow.json` and its reference file; the importer generates a layout. Importing replaces the current diagram, so export existing work first.

The example contains one recovery path:

```text
Start
  ↓
Entry investigation: ready ──Yes──→ Acquisition action: collect
                                            ↓
                              Low-voltage investigation: is_low
                                            │ Yes
                                            ↓
                                        Conclusion
                                            ↓
                             Remediation: restore_and_verify
                                            ↓
                                      Problem Solved
```

Select nodes to inspect the following bindings. Every business node uses module `device_session` and class `Device`. Leave the job topic blank.

| Node ID      | Node type            | Interface            | What happens                                                                               |
| ------------ | -------------------- | -------------------- | ------------------------------------------------------------------------------------------ |
| `Ready`      | Investigation        | `ready`              | Create `Device` on first use; its `True` result leads to acquisition                       |
| `reading`    | Investigation Action | `collect`            | Return a native `Reading` object and retain it as this node's result                       |
| `Check`      | Investigation        | `is_low`             | Receive that original object and test for low voltage                                      |
| `Conclusion` | Conclusion           | None                 | Record the low-voltage conclusion                                                          |
| `Repair`     | Remediation          | `restore_and_verify` | Restore the same instance, verify asynchronously, and raise an error if verification fails |
| `Solved`     | Problem Solved       | None                 | Mark this recovery path complete                                                           |

Bind investigations under **Execution and human decisions**, and action/remediation nodes under **Interface binding**. A text-only conclusion needs no interface. Problem Solved and Escalation nodes do not bind business functions. Select `collect` as the function name; do not enter a call expression such as `Device.collect()`.

To draw the example manually, use the same node types and bindings. The acquisition node's **General → ID** must be `reading`, matching the parameter in the example's judgment method. Choose your own display names or let details generate them.

This example implements only the low-voltage recovery path. Both investigations have only a Yes group. A No result without a matching successor records a failed path; it does not mean that a normal-voltage success path has been modeled. Add a separate path following the connection rules if you need that outcome.

## 5. Understand parameter and object passing

The central calls in this example are equivalent to:

```python
device = Device(device_id='M01', threshold=24)
device.ready()
reading = device.collect()
device.is_low(reading)
# When the judgment succeeds, call async restore_and_verify on this instance.
```

Nodes using the same module and class/factory reuse the same instance within an investigation. Existing Python methods maintain its attributes; you do not configure `latest`, `attempts`, or `recovered` again as platform parameters. Another investigation gets its own process and instance.

For inputs declared in a function signature, the platform searches in this order:

1. A same-name startup variable or complete node result. Parameter `reading`, for example, receives the original result of node `reading`.
2. A unique same-name field in an already executed upstream result dictionary. A `voltage` field can supply a later method's `voltage` parameter.
3. The function's Python default.

Legacy explicit parameter mappings, when present, take precedence. New workflows do not require parameter code or expressions in nodes. Missing data produces a Python missing-argument error. Multiple same-name field candidates produce an ambiguity error rather than a guessed value.

Original objects remain inside that business project's Python session. Flowable and the UI store a displayable result. Objects that cannot be encoded directly as JSON show their type and textual representation; that text never replaces the original object passed to a later method. Native references cannot cross between different project subprocesses.

An investigation must return an explicit judgment: `True`, `False`, `yes`, `no`, `是`, `否`, or a dictionary with `next`, such as `{'next': 'yes', 'voltage': 22.6}`. English judgments ignore case. A compatible legacy flow-ID result selects that flow's whole group. Numbers and arbitrary objects are not routed using Python truthiness.

Actions can take no inputs and return `None`. Only investigations that choose a branch must provide a judgment. You can bind `async def` methods directly.

## 6. Export the execution bundle and run the whole workflow

### 6.1 Export the bundle

Click **Flowable execution → Export execution bundle**. Extract the download to a fixed directory, such as `D:/exports/device-session`. The three files have different roles:

| File                  | Purpose                                                       |
| --------------------- | ------------------------------------------------------------- |
| `source.bpmn`         | Complete snapshot for continuing to edit the original diagram |
| `workflow.bpmn20.xml` | Executable definition deployed to Flowable                    |
| `bindings.json`       | Node/interface bindings read by the worker                    |

The worker command below must point to the extracted `bindings.json`. Continue editing with `source.bpmn`, rather than treating the compiled executable definition as the original diagram.

### 6.2 Start the worker

Open another terminal in this repository's root and run:

```powershell
backend/.local/venv/Scripts/python.exe backend/flowable_worker.py D:/exports/device-session/bindings.json
```

`Subscribed:` followed by task topics means the worker is listening. It reads `backend/.local/projects.json` by default and uses registered interpreters and working directories for business calls. You need not reinstall business dependencies into the worker environment.

Run one worker for the same execution bundle on the same Flowable service. It can manage multiple investigations at once, each with an independent business process. Duplicate local workers are rejected. Also keep one coordinator across machines: the local lock cannot coordinate different computers.

### 6.3 Supply startup inputs and start

Return to **Flowable execution**. The startup form reads initialization parameters from registered classes or factories. For this example, enter `M01` for `device_id` and `24` for `threshold`, or leave both blank to use `Device` defaults.

Use **Add startup input** for other name/value inputs. Ordinary method parameters may come from upstream results, so they are not all treated as required startup fields. Initialization data generated earlier in the workflow can also be supplied upstream. Startup variables are shared globally by name: entering one value affects all same-name factory parameters, while blank fields preserve each factory's own default.

Click **Deploy and start**. The platform deploys the current diagram and creates a process instance. Recovery state from single-interface debugging does not carry into this workflow.

For compatibility, expand **Advanced: initial variables JSON** and enable **Use JSON instead of the form**. That JSON object then replaces the form inputs; the two sources are not merged. It defaults to `{}`. For built-in diagnostic examples, select an example scenario from the dropdown.

### 6.4 Confirm the result

Click **Refresh execution results**. With default inputs, this example should visit `Ready → reading → Check → Conclusion → Repair → Solved`, then show that the process completed.

**Execution details** contains node results and history. Acquisition shows a display representation of `Reading`. A `null` remediation result is normal. If recovery verification fails—for example, with threshold `30`—`Repair` fails and the workflow does not reach Problem Solved.

After a task error, refresh and expand its failure details to see the original Python traceback, including the business file, call location, and exception. Worker terminal output provides additional context. A result dictionary containing a `chartSvg` string can display a chart; returning a local file path alone does not display an image.

## 7. Extend the example with more investigation paths

### 7.1 Node content and connections

Every diagnostic node has a name and details. New nodes have no default names. Details generate a summary that fits the node dimensions; manual names are preserved, while automatic summaries adjust when resized. **General → Node type** is read-only. For conclusions, a name entered without content is copied into the conclusion content, and content entered without a name generates a name summary.

Investigations also require data to inspect, acquisition instructions, an assessment method, and a reference file. Describe actions and remediation in their details, and state conclusions explicitly. You can export an unfinished draft, although it may not qualify for executable export.

The main connection sequence is Start → Investigation; Investigation Action → Investigation; Investigation → Conclusion → Remediation; completed remediation can reach Problem Solved. Investigations cannot connect directly to Remediation or Problem Solved, and Remediation cannot connect directly back to Investigation. Jump represents a handoff whose target must be implemented by the integration; node text alone does not execute another diagram.

Investigation uses a diamond, Investigation Action an upright trapezoid, Conclusion a rectangle, Remediation an inverted trapezoid, Jump an ellipse, Problem Solved a triangle, and Escalation a star. Deep Diagnosis retains its existing style. Resize with the node border. Validation reports illegal connections and missing content.

### 7.2 Yes/No groups and dependencies

An investigation can have Yes and No output groups, each connecting to multiple distinct nodes. Either group may be absent. Change a connection's canvas label to `是`, `否`, `yes`, or `no` to change its group; English is case-insensitive. Other labels are rejected.

Connect independent methods as siblings in the same group after their common prerequisite. If B requires A to finish first, connect B after A. Drawing one sibling connection before another does not give it priority in parallel mode.

A judgment with no matching successor records a failed path. This is a normal diagnostic outcome, distinct from a Python exception, which is a task-execution error.

### 7.3 Parallel and serial modes

Select the process and choose its investigation mode:

| Situation                            | Parallel                                                                  | Serial                                                        |
| ------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Several successors in the same group | Start them concurrently, with no priority                                 | Try them in order                                             |
| A path has no matching successor     | End and record that path; other active paths continue                     | Move to the next pending path                                 |
| A path reaches Problem Solved        | Record its success; other active paths continue under their existing flow | Pause any remaining paths and let the user finish or continue |
| All paths fail                       | The investigation fails                                                   | The investigation fails                                       |

In serial mode, select a connection and enter a number under **Execution order**. Lower numbers run first; missing or equal numbers retain connection order in the definition. Parallel mode ignores this setting. Multiple remediation nodes may connect to one Problem Solved node; each arrival proceeds without requiring an extra gateway that waits for every path. Loops need a reachable exit.

Parallel nodes may call methods on one object simultaneously. The business project controls whether concurrent access is valid and how equipment access or shared state is protected.

## 8. Handle human waits, rechecks, and interruptions

### 8.1 Request a human decision

Enable **Human decision / confirmation** on an investigation. With no Python interface it waits directly; with an interface it executes that interface before requesting review. This switch belongs only to investigations that make a judgment and choose a branch.

When the workflow waits, refresh **Flowable execution**, inspect the evidence and assessment instructions, select Yes or No, and continue. Escalation also waits for human review. Serial success with remaining paths offers **Finish investigation** and **Continue remaining paths**.

### 8.2 Request human help for unimplemented judgment code

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

### 8.3 Recheck an earlier node

During an investigation or escalation human wait, select a **previously executed node**, provide a reason and optional recheck input variables, then click **Recheck**. The system retains previous history, results, and the reason; it clears results requiring recomputation and runs again from the selected node.

Rechecking does not undo equipment actions or restore an older Python object state. It reruns methods on the current instance, and actions may occur again. The current node, unvisited nodes, and completed instances are not arbitrary recheck targets. Running automatic tasks do not expose this intervention. At a serial-success pause, choose continue or finish rather than recheck.

### 8.4 Stop, restart, and update

Flowable saves progress and display results, not the entire Python memory. Restarting the worker or business subprocess loses its device instances. Continuing an old workflow then reports session loss; neither `repr` nor historical display data can reconstruct those objects.

Account for active investigations before updating business code. Reload interfaces after editing code and start the updated worker for new runs; restarting loses its current sessions. Changes to bindings, connections, groups, or order also require a new execution bundle. Old instances still need their matching old worker. The worker releases business sessions after observing process completion; unfinished failed processes retain sessions for subsequent handling.

## 9. Save workflows and reference files

### 9.1 Choose a format for your purpose

| What you need                                                     | Command                                          | Output                                           |
| ----------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
| Diagnostic logic and resources for moving and restoring           | **Export diagnostic project**                    | ZIP containing `workflow.json` and `assets/`     |
| Complete editing state, including layout, size, colors, and fonts | **Export complete BPMN with layout and styles**  | Full BPMN editor snapshot                        |
| Deployment to Flowable                                            | **Flowable execution → Export execution bundle** | The three execution files described in section 6 |
| Offline Python code for further implementation                    | **Export Python skeleton**                       | Code and resources described in section 10       |

A portable diagnostic project's main definition is version 4 `workflow.json`. It keeps node content, bindings, connections, Yes/No groups, serial order, and investigation mode. It omits layout, dimensions, colors, and fonts. Resources live separately in the directory; JSON records relative paths, embeds no file data, and adds no duplicate BPMN file.

Move the complete directory together. Restore it with **Import project directory**, which reads JSON and resources and creates a layout. Importing `workflow.json` alone can still restore nodes and connections, but its resources are separate. If resources are reported missing, import the full directory instead. Older JSON versions are accepted; older connections without an explicit Yes/No group need updating.

These exports do not package the business Python project, interpreter, or local registrations. On another computer, prepare the business project and dependencies, register it again, and start the required services.

### 9.2 Add and open reference files

Select a file under a node's **Reference file**. Common images, PDFs, text, CSV, Markdown, JSON, and some audio/video can be previewed in the UI, depending on browser support. Active documents such as HTML, SVG, and XML, and other formats, are opened through the Windows local service in a local application.

If no default association exists, the system application chooser opens. Scripts, executables, and shortcuts always require choosing a viewing application. External applications receive a temporary copy: edits do not automatically update the project. To replace a reference, save the edited file and select it again.

Each reference file is limited to 50 MiB. Combined deployment/start requests are limited to 70 MiB, including encoding and JSON overhead, so several large files can also exceed the total. Portable export still writes them as separate resources referenced by relative paths.

If business Python code needs the same file, read it from the appropriate project path and deploy it with that project. Attaching it to a node does not automatically add a file argument or modify paths in Python code.

## 10. Alternative execution and advanced settings

### 10.1 Structural simulation

**Start structural simulation** only animates BPMN tokens. It permits nodes without Python bindings and does not validate functions, parameters, real judgments, or diagnostic serial-success pauses. Use **Flowable execution** to check business behavior.

### 10.2 Export an offline Python skeleton

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

### 10.3 Other worker and service settings

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

## 11. Find the right place to troubleshoot

| Symptom                                 | First check                                                                  | Next step                                                                                        |
| --------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Python projects cannot connect          | Backend, page origin, and proxy port                                         | Verify addresses using section 2                                                                 |
| Registration cannot import the module   | Project root, module name, interpreter, and dependencies                     | Confirm importability in that interpreter; use a module name, not a file path                    |
| Required interface is absent            | Public export, re-export, and factory return-class annotation                | Update exports/annotations, then reload interfaces                                               |
| Missing or ambiguous arguments          | Parameter names, node IDs, startup inputs, and executed results              | Establish a unique source using section 5; signatures alone cannot supply values                 |
| Animation works but execution does not  | Structural simulation versus actual execution; whether the worker is running | Start a worker for the correct bundle and inspect the real process                               |
| Automatic tasks remain waiting          | Java service and worker subscriptions                                        | Check `Subscribed:` and the selected `bindings.json`                                             |
| Worker already exists                   | Duplicate workers for the same bundle                                        | Use the existing coordinator; it supports multiple investigations                                |
| Unexpected routing                      | Explicit judgment value and matching output group                            | Distinguish a normal failed path from a Python task error                                        |
| Python task fails                       | Original traceback in failure details                                        | Follow its business file and call location; repeating an action can affect equipment again       |
| Session is lost                         | Worker or business subprocess restart                                        | Handle the actual equipment state, then start a new investigation; history cannot restore memory |
| Missing or unopenable reference         | JSON-only import or missing local application                                | Import the full directory or select a supporting application                                     |
| Recheck did not restore equipment state | Whether recheck was mistaken for undo                                        | Recheck reruns logic; it does not rewind equipment or object state                               |

For lower-level interface and runtime details, see [Python integration](../backend/README.md) and [Flowable technical documentation](../backend/FLOWABLE.md).
