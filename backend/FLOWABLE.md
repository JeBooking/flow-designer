# Flowable external Python execution

## Current Yes/No execution contract

Investigations support optional Yes and No groups (`flowable:diagnosisBranch` on sequence flows),
each with unlimited edges. No matching successor records a failed path in `diagnosticFailures`.
The process property `flowable:diagnosisMode` chooses `parallel` (default) or `serial`.
Parallel mode activates matching siblings concurrently without priority; a failure ends only that
path and never restarts siblings. Merges continue per arrival without a mandatory join gateway.
Serial mode uses a persisted queue, trying siblings by ascending `flowable:diagnosisOrder` with
XML order as fallback. Failure advances to the next pending path; exhaustion without success sets
`diagnosticStatus=failed`. Success pauses remaining paths (`diagnosticStatus=paused`). The review
UI offers finish or continue; review requests use `action=confirm`, `next=finish` or `continue`,
and `mode=success`. Continue resumes the retained queue without replaying completed paths.
Move conditional decisions into investigations. Conclusions may contain text without a Python binding.
Exported Python runners follow the same mode and failure rules and expose paused state through
`run(..., resume=state, success_action='continue'|'finish')`.

The worker discovers parameters with `inspect.signature`: explicit legacy mappings, exact workflow
variable names, unique fields in upstream result dictionaries, then defaults. Missing/ambiguous
values fail with the parameter name; positional-only, async, zero-input and void actions work.
Return `True`/`False`, `yes`/`no`, or `{"next": "yes"}` from an investigation. A legacy flow ID
selects its entire group. No parameter language is required in the node panel.

Unmarked investigation edges are rejected instead of inferred from their order.

The editor keeps the diagnostic nodes and their descriptions. The exporter maps them to
Flowable external service tasks, exclusive gateways and end events. Flowable 7.1.0 schedules
the process; the official Python client 1.0.2 acquires jobs and reports completion.

## Prepare once

Requires Java 21, Maven 3.9+, Python 3.9+ and the existing Node.js/pnpm environment.
From the repository root, install dependencies and build the local runtime:

```powershell
pnpm install
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
mvn -f flowable-runtime/pom.xml package
```

Install business-project dependencies in the interpreter registered for that project.
The launcher checks the environment; it does not install dependencies or build the Java jar.
On Linux/macOS, replace `backend/.local/venv/Scripts/python.exe` with
`backend/.local/venv/bin/python`.
Rebuild the jar after Java runtime changes, then restart the owned services.

The local runtime binds to `127.0.0.1:8080` with `diagnostic / local-demo` and stores its H2
database in `flowable-runtime/data/`. Set `FLOWABLE_USER` and `FLOWABLE_PASSWORD` to configure
credentials; the Python bridge and worker use the same settings. Configure access controls
and a suitable database before exposing this local configuration beyond the machine.

## Daily execution

From the repository root:

```powershell
pnpm dev
```

This starts the frontend, Python backend and local Java engine together. Open the printed
editor address (`http://127.0.0.1:5173/vue-bpmn-designer/` by default). Healthy existing
services are reused only after validation; a reused backend must report the same Flowable URL.
Explicitly setting `FLOWABLE_URL` selects an external engine: the launcher connects to that
engine and does not start a local Java replacement. Its default is `http://127.0.0.1:8080`.

For production, prepare `dist/` with `pnpm build`, then run `pnpm start`; production startup
requires that existing build. `pnpm dev:frontend` starts only Vite for advanced use with
separately managed services.

1. Register your existing business project in **Python projects**, then select its interfaces
   on the current diagram's nodes.
2. Open **Diagnostic execution**. Fill required class/factory initialization inputs; blank
   optional inputs retain Python defaults. Add name/value rows for extra startup data.
   The collapsed advanced initial JSON option can replace the form (default `{}`).
   Ordinary method arguments continue to match upstream results automatically.
3. Click **Start execution**. The backend compiles the current diagram, prepares or reuses
   the matching worker through `execution_manager.py`, then deploys and starts the instance.
   No execution-bundle export or manual worker launch is needed for this browser flow.
4. Results update automatically. Actual executed/waiting/failed nodes are highlighted on
   the canvas. Result cards show object fields and array tables; a returned `chartSvg`
   displays a chart. Raw execution details stay collapsed until expanded. Failure details
   include the original Python traceback when available.
5. Complete any human decision or escalation review in the same drawer; the rules below
   explain confirmation and rechecking.

Closing the drawer pauses polling only; it does not stop the workflow or business code.
Reopening it within the same editor session resumes monitoring. A browser refresh or
Modeler recreation does not restore the monitored instance. Keep the instance ID for
operational investigation. A dead-letter failure can be acknowledged to **Run the current
diagram again**; this creates a new instance, does not cancel the old one, and may repeat
equipment actions.

Launcher/service logs are under `backend/.local/logs/`; managed worker logs are under
`backend/.local/executions/<hash>/<uuid>.log`. Exiting the launcher stops only services
it owns (and their managed workers), leaving reused/external services running. Stopping
services does not undo equipment operations; restarting does not restore native sessions.

## Escalation review and rechecking

Compiled processes pause at escalation using a Flowable user task. The editor still
shows escalation as a final diagnostic node; only **Confirm escalation and finish** reaches
the actual end event. At problem solved, serial mode pauses for a finish/continue choice if
pending paths remain; parallel success does not cancel other already-started paths. After Java runtime upgrades,
rebuild the jar and restart services, then start a new execution from the current diagram;
existing deployments retain their behavior.

When automatic monitoring shows a pending human review and the review card identifies the
escalation node, select a previously executed node and provide a reason. Optionally update business input variables, then choose **Recheck**.
Flowable resumes at that node in the same instance. You can review again if escalation is reached, or explicitly confirm escalation.

This reruns logic and may repeat downstream machine actions; it does not undo physical actions.
A deterministic algorithm with the same inputs can produce the same answer again. Upstream
results remain available, while results requiring recomputation and their routing variables
are cleared. Previous values, changed inputs, reasons and timestamps are retained in the JSON
variable `diagnosticReviews`, visible in execution details. Activity history retains every visit.
Cleanup, audit recording and state change share a transaction. Unvisited targets, stale review
tasks and attempts to overwrite results, routing or audit variables are rejected.

The authenticated Java endpoint `GET /diagnosis-api/instances/{id}/review` returns pending
status and eligible nodes. `POST` accepts `action` (`recheck` or `confirm`) and the current
`taskId`; rechecking also requires `targetNodeId` and `reason`, with optional input `variables`.
Ended instances cannot be rechecked.

## Rechecking from any human decision

Enable **Human decision / confirmation** under **Execution and human decisions** on a
non-final diagnostic node. Without a Python binding it waits immediately. With a binding,
it first runs acquisition, plotting or actions, then waits for the human decision.
Multiple outgoing flows require an explicit choice; a single successor offers confirmation.
Every human wait, including escalation, offers a return to an earlier executed investigation,
conclusion or action. Unvisited nodes and the current node are excluded; the first node shows
that no earlier target exists. Returning to a manual node waits again; a bound node reruns Python first.
Interrupting running automatic nodes is outside this change. Problem solved follows the serial
success-pause and parallel-path rules above.

The existing `/review` API returns `mode` (`decision` or `escalation`), instructions, a reference
image and `options` (outgoing flow IDs and names). POST `action: confirm` requires `next` for
multiple options. Python's `next` is optional advisory data in human mode. Confirmation updates
the node result's `next`, adds `humanConfirmed: true`, and audits the original result. Other object
fields remain intact; non-object results are wrapped in `data`. Manual-only nodes get a confirmation result.
`flowable:humanDecision` persists through undo/redo and XML round-trips. After upgrading,
restart the relevant services and start a new execution; existing deployments retain their behavior.
Compiled metadata uses a `flowable:diagnosticExecution` extension to avoid the 2000-character
process documentation limit.

## Bind a project

Register an existing directory, importable module, interpreter and optional factory in
**Python Projects**. A class such as `Device` is the simplest stateful entry: public bound
methods become interfaces without exposing `self`. Discovery inspects a class without
constructing it; constructor inputs come from same-name startup variables or defaults.
Factory functions with a return-class annotation can also be inspected without invocation.
An unannotated factory is temporarily called with defaults; required inputs need a return-class
annotation. Leave factory empty for existing module functions and `__all__` exports.

Configure the business object entry once in **Python projects**. On each non-final node,
select that registered project and its method/function; the entry is carried into the binding
automatically. Existing XML and JSON bindings remain supported. Signature matching
supplies startup variables, complete raw results by node ID and unique dictionary fields,
preserving defaults, positional-only arguments and `async def`. No parameter expressions
are required. Legacy mappings still support `$Inspect.data`, `$` (all variables), dictionary
and list paths, and `$$device` for a literal `$device`. Actions can return `None`.
Investigations return explicit Yes/No (`True`/`False`, `yes`/`no`, or a `next` dictionary).
A legacy outgoing flow ID chooses its whole group; arbitrary object truthiness is rejected.

The managed worker uses the prepared official-client environment. By default it reads
`backend/.local/projects.json`, matches module/factory registrations and starts business
subprocesses with each registration's interpreter and project working directory. Business
dependencies belong in the interpreter that actually runs that project. Manual CLI options
are documented under optional operations below.

One workflow's calls to the same project share a persistent isolated subprocess. A factory
instance is created once; ordinary module functions retain their globals. Different workflows
are isolated. Raw results stay under node IDs inside Python and may be arbitrary Python
objects. Flowable stores only JSON display projections, including `native`, `pythonType`
and `representation` metadata where needed; a `repr` display is never used as the original
object. Native references cannot cross project subprocesses. Parallel methods on the same
instance require project-managed thread safety. Flowable continues to own scheduling,
human waits, routing and history; this adds no second workflow engine.

In interface debugging, consecutive calls share a session and **Reset session** starts fresh.
During a real workflow, rechecks rerun methods on current state and do not roll the object back. Finished sessions are released after the
worker observes completion; failed sessions remain for inspection. There is no automatic
checkpoint: restarting a worker/subprocess loses sessions, and affected old workflows report
session loss instead of silently rebuilding instances. History/projections cannot restore them.
Offline skeleton exports retain their existing implementation/manual-fallback rules and do
not automatically execute bindings saved in the diagram.

Use one worker coordinator per execution package/topics on the same Flowable service.
That coordinator supports concurrent workflow runs through their isolated subprocesses.
Duplicate subscriptions on the same machine are rejected by a local singleton lease.
The lease does not span machines: deployments must retain one coordinator across hosts
as well. Compatibility with ordinary stateless functions does not imply that competing
workers can share native objects or safely scale this session model horizontally.

After a Python task failure, automatic monitoring updates the results. Expand the failure
details to inspect the original Python traceback; worker logs provide additional context.

Topics include process ID and an execution-definition digest. Layout, descriptive text and
XML/argument-JSON formatting changes preserve topics. After changing connections, bindings or
parameters, start a new execution from the current diagram; the backend prepares its matching worker.
Previous instances still need their original worker and native session. Topics must be unique
in a diagram. Source conditions and default flows are rejected. Automatic mode uses Python's `next`; human mode uses the selected option.
Export currently supports one top-level process, one plain start event, and diagnostic nodes.
Unsupported subprocesses and events are rejected. Non-final nodes require bindings or human mode.
Real machine operations need business-specific
idempotency because external jobs can be retried. GUI functions requiring the main thread should
launch a separate desktop process from their entry point; client callbacks execute on threads.

## Automatic human fallback in decision components

`backend/diagnostic_components.py` provides reusable Python decision components. Flowable only transports wait requests, persists state and resumes execution. Every Python-bound non-final node supports this protocol without the human checkbox; that checkbox can still require extra review of automatic results.

```python
from diagnostic_components import DecisionComponent, decision

judge = DecisionComponent()

def diagnose(reading):
    return judge.run(reading, instructions='Inspect the curve and select a successor')

@decision(instructions='Inspect the curve and select a successor')
def diagnose_with_decorator(data):
    raise NotImplementedError('Business decision pending')
```

An inherited `decide(self, data)` or explicit `NotImplementedError` returns a `HumanDecisionRequest`. Implement the method/function to return normal JSON, including `{"next": "flow ID", ...}` for branching, and execution proceeds automatically. `pass` / `None` does not mean unimplemented. Other exceptions remain failures. Sync and async functions are supported. Decorators target ordinary functions whose first argument or `data` keyword supplies evidence; use the base class for methods.

Return the typed request directly without converting it into JSON. It carries evidence and optional instructions without blocking the worker. Empty instructions preserve the diagram's diagnosis method; reference images and successor options come from the diagram. Optional `options` must match all outgoing flow IDs. The UI displays evidence and charts, offers successor selection and rechecking, and clears obsolete requests on recheck.

The worker already exposes this module on its import path. Independent business-project execution must add `backend` to the Python import path. Exported skeletons include the same module and collect human choices through the CLI.

After upgrading components, start a new execution with the updated services and worker.
Existing instances require their original worker version and native session.

## Optional manual worker operations

For operations outside the managed browser flow, a prepared bindings manifest can be supplied
explicitly. Do not start a competing manual worker for topics already owned by a managed worker:

```powershell
backend/.local/venv/Scripts/python.exe backend/flowable_worker.py C:/exports/bindings.json
```

`--registry PATH` selects a registration file. Repeated `--project PATH` supports unregistered
legacy modules using the worker interpreter. Manual launches remain subject to the singleton,
native-session and restart limits above; they are not a prerequisite for **Start execution**.
