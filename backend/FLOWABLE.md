# Flowable external Python execution

## Current Yes/No execution contract

Investigations require both Yes and No groups (`flowable:diagnosisBranch` on sequence flows).
All matching edges activate through an inclusive gateway without priority. Other action fan-outs
are parallel; move conditional decisions into investigations. Merges continue per arrival, and
Problem Solved ends each incoming path without waiting for other paths. Only investigations create
human decision tasks. Conclusions may contain text without a Python binding.

The worker discovers parameters with `inspect.signature`: explicit legacy mappings, exact workflow
variable names, unique fields in upstream result dictionaries, then defaults. Missing/ambiguous
values fail with the parameter name; positional-only, async, zero-input and void actions work.
Return `True`/`False`, `yes`/`no`, or `{"next": "yes"}` from an investigation. A legacy flow ID
selects its entire group. No parameter language is required in the node panel.

Use the new **Parallel investigations and dependencies** example. Older examples and their legacy
engine scenario scripts below require topology migration; their former exclusive semantics do not
apply to the current compiler. Unmarked investigation edges are rejected instead of guessed.
Current offline checks: `python scripts/verify-diagnosis-design.py`,
`python scripts/verify-python-bindings.py`, and `pnpm exec node scripts/verify-code-export.mjs`.

The editor keeps the diagnostic nodes and their descriptions. The exporter maps them to
Flowable external service tasks, exclusive gateways and end events. Flowable 7.1.0 schedules
the process; the official Python client 1.0.2 acquires jobs and reports completion.

## Start

Requires Java 21, Maven 3.9, Python 3.9+ and the existing pnpm environment.

```powershell
cd flowable-runtime
mvn package
java -jar target/diagnostic-flowable-1.0.0.jar
```

The example binds to localhost:8080 with `diagnostic / local-demo` and stores its H2 database
in the working directory's `data/` folder. Use `FLOWABLE_USER` and `FLOWABLE_PASSWORD` to
configure credentials. The Python bridge and worker use these same settings and `FLOWABLE_URL`
(default `http://127.0.0.1:8080`). Configure deployment access and a suitable database before
exposing it beyond this local example.

From the repository root, in separate terminals:

```powershell
python -m venv backend/.local/venv
backend/.local/venv/Scripts/python.exe -m pip install -r backend/requirements-flowable.txt
python backend/server.py
pnpm dev
```

## Example

Open **Flowable execution**, select and load a diagnostic example (export your current diagram first),
then export and extract the execution bundle. Keep `source.bpmn` for editing; deploy
`workflow.bpmn20.xml` and give `bindings.json` to the worker:

```powershell
backend/.local/venv/Scripts/python.exe backend/flowable_worker.py C:/path/to/bindings.json --project backend/examples/diagnostic_demo
```

Deploy and start from the drawer with `{"scenario":"recover"}` and refresh results to see
activities, variables and the actual temperature charts. SVG files are stored under
`backend/examples/diagnostic_demo/output/`.

All eight diagnostic node types are included. Scenarios: `normal` and `recover` reach
problem solved; `action` also exercises investigation action and rechecking; `escalate`
performs deep diagnosis before escalation; `severe` escalates directly after remediation;
`jump` records a handoff request and ends the local chain. The target chain is not executed
by this example. Temperature samples and machine actions are simulated; chart generation
and threshold calculations run real Python code.

The gallery contains six independent diagrams, all using the same `diagnostic_demo` project.
Select a scenario after loading a diagram to fill initial variables, and use that diagram's
exported bindings with the worker:

| Diagram         | Scenarios                                       | Focus                                                       |
| --------------- | ----------------------------------------------- | ----------------------------------------------------------- |
| Human decisions | recover, severe, normal                         | Confirmation, branch choices and rechecks before escalation |
| Temperature     | recover, normal, action, escalate, severe, jump | All eight node types                                        |
| Power supply    | recover, normal, severe                         | Lower-limit analysis and recovery results                   |
| Communication   | recover, normal, offline                        | Async checks and reset/recheck loop, at most three attempts |
| Dual sensors    | sensor-a, sensor-b, normal, severe              | Exclusive branches and a shared conclusion                  |
| Pressure        | stable, leak, unknown                           | Ordered actions, deep analysis and handoff                  |

All machine samples and actions are simulated, while plots, numerical analysis and process
execution are real. Revisited nodes update their result variable; activity history retains each
visit. Bound pure-diagnostic graphs use exclusive routing and do not wait for other branches at
joins. Ordinary BPMN parallel-flow join validation remains enabled.

## Escalation review and rechecking

Newly exported processes pause at escalation using a Flowable user task. The editor still
shows escalation as a final diagnostic node; only **Confirm escalation and finish** reaches
the actual end event. Problem solved still finishes immediately. Rebuild/restart the Java
service and re-export bindings after upgrading; existing deployments retain their behavior.

Refresh execution results, select a previously executed node, and provide a reason.
Optionally update input variables (for the sensor example, `{"scenario":"sensor-b"}` supplies
new simulated measurements), then choose **Recheck**. Flowable resumes at that node in the
same instance. You can review again if escalation is reached, or explicitly confirm escalation.

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
Interrupting running automatic nodes is outside this change. Problem solved still ends immediately.

The **Human decisions and rechecks** example combines Python voltage charts, a manual-only
conclusion and simulated recovery with a human choice of solved or escalation. Recheck before
escalation from either the conclusion or recovery step. Machine actions remain simulated.
Rechecking preserves history and clears results needing recomputation; it may repeat actions
and does not undo machine operations.

The existing `/review` API returns `mode` (`decision` or `escalation`), instructions, a reference
image and `options` (outgoing flow IDs and names). POST `action: confirm` requires `next` for
multiple options. Python's `next` is optional advisory data in human mode. Confirmation updates
the node result's `next`, adds `humanConfirmed: true`, and audits the original result. Other object
fields remain intact; non-object results are wrapped in `data`. Manual-only nodes get a confirmation result.
`flowable:humanDecision` persists through undo/redo and XML round-trips. Rebuild/restart Java and
Python services and re-export the bundle for the matching worker. Existing deployments retain their behavior.
Compiled metadata uses a `flowable:diagnosticExecution` extension to avoid the 2000-character
process documentation limit.

## Bind a project

On non-final nodes, configure module, function and JSON keyword arguments. Repeat `--project`
to add project roots (including `src/`). Install project dependencies into the worker's Python
environment. `$Inspect.data` reads an earlier result; `$` passes the complete variable dictionary. Dot paths support dictionaries and list
indices. `$$device` passes the literal string `$device`. Both synchronous and `async def`
functions are supported. Results must be JSON serializable and are stored under the node ID. Branch functions
in automatic mode must return `{"next":"outgoingFlowId", ...}`. Invalid routing fails the job rather than
executing every branch. The compiler creates exclusive gateways without evaluating arbitrary
user Python or condition expressions.

Topics include process ID and an execution-definition digest. Layout, descriptive text and
XML/argument-JSON formatting changes preserve topics. Re-export and restart the matching worker
after changing connections, bindings or parameters; previous instances still need their original
worker. Topics must be unique in a diagram. Source conditions and default flows are rejected;
Automatic mode uses Python's `next`; human mode uses the selected option.
Export currently supports one top-level process, one plain start event, and diagnostic nodes.
Unsupported subprocesses and events are rejected. Non-final nodes require bindings or human mode.
Real machine operations need business-specific
idempotency because external jobs can be retried. GUI functions requiring the main thread should
launch a separate desktop process from their entry point; client callbacks execute on threads.

## Checks

### Automatic human fallback in decision components

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

The worker already exposes this module on its import path. Independent business-project execution must add `backend` to the Python import path. Exported skeletons include the same module and collect human choices through the CLI. See `backend/examples/diagnostic_demo/diagnostic_demo/decisions.py`.

Re-export, redeploy and start the matching worker after upgrading; existing instances require their original worker version. Independent component checks and engine checks (human mode disabled, conclusion/action waits, chart evidence, routing and rechecks):

```powershell
backend/.local/venv/Scripts/python.exe scripts/verify-decision-components.py
backend/.local/venv/Scripts/python.exe scripts/verify-component-decisions.py
```

```powershell
python scripts/verify-flowable.py --unit-only
backend/.local/venv/Scripts/python.exe scripts/verify-flowable.py
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-examples.py
node scripts/verify-diagnostic-lint.mjs
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-review.py
backend/.local/venv/Scripts/python.exe scripts/verify-human-decisions.py
```

The second command requires a running engine and verifies six complete execution paths,
exclusive routing, threshold results and actual SVG output using the official Python client.
The third runs thirteen scenarios across the four added automatic diagrams. The lint command checks all six diagrams
against the complete lint configuration, XML round-trips and ordinary BPMN join validation.
The review script verifies waiting, repeated and selective rechecks, A/B result isolation,
invalid/stale requests and explicit final confirmation. Existing example checks now explicitly
confirm escalation before checking process completion.
The human-decision script verifies the first wait, manual-only nodes, branch selection,
returning to conclusions/actions, cleanup and audit history.
