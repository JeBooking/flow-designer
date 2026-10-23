# Flowable external Python execution

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

The gallery contains five independent diagrams, all using the same `diagnostic_demo` project.
Select a scenario after loading a diagram to fill initial variables, and use that diagram's
exported bindings with the worker:

| Diagram | Scenarios | Focus |
| --- | --- | --- |
| Temperature | recover, normal, action, escalate, severe, jump | All eight node types |
| Power supply | recover, normal, severe | Lower-limit analysis and recovery results |
| Communication | recover, normal, offline | Async checks and reset/recheck loop, at most three attempts |
| Dual sensors | sensor-a, sensor-b, normal, severe | Exclusive branches and a shared conclusion |
| Pressure | stable, leak, unknown | Ordered actions, deep analysis and handoff |

All machine samples and actions are simulated, while plots, numerical analysis and process
execution are real. Revisited nodes update their result variable; activity history retains each
visit. Bound pure-diagnostic graphs use exclusive routing and do not wait for other branches at
joins. Ordinary BPMN parallel-flow join validation remains enabled.

## Escalation review and rechecking

Newly exported processes pause at escalation using a Flowable user task. The editor still
shows escalation as a final diagnostic node; only **Confirm escalation and finish** reaches
the actual end event. Problem solved still finishes immediately. Rebuild/restart the Java
service and re-export bindings after upgrading; existing deployments retain their behavior.

Refresh execution results, select a previously executed investigation, and provide a reason.
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

## Bind a project

On non-final nodes, configure module, function and JSON keyword arguments. Repeat `--project`
to add project roots (including `src/`). Install project dependencies into the worker's Python
environment. `$Inspect.data` reads an earlier result; `$` passes the complete variable dictionary. Dot paths support dictionaries and list
indices. `$$device` passes the literal string `$device`. Both synchronous and `async def`
functions are supported. Results must be JSON serializable and are stored under the node ID. Branch functions
must return `{"next":"outgoingFlowId", ...}`. Invalid routing fails the job rather than
executing every branch. The compiler creates exclusive gateways without evaluating arbitrary
user Python or condition expressions.

Topics include process ID and an execution-definition digest. Layout, descriptive text and
XML/argument-JSON formatting changes preserve topics. Re-export and restart the matching worker
after changing connections, bindings or parameters; previous instances still need their original
worker. Topics must be unique in a diagram. Source conditions and default flows are rejected;
Python's `next` result is the single source of branch selection.
Export currently supports one top-level process, one plain start event, and diagnostic nodes.
Unsupported subprocesses and events are rejected. All non-final nodes require bindings. The
example does not provide a human task UI. Real machine operations need business-specific
idempotency because external jobs can be retried. GUI functions requiring the main thread should
launch a separate desktop process from their entry point; client callbacks execute on threads.

## Checks

```powershell
python scripts/verify-flowable.py --unit-only
backend/.local/venv/Scripts/python.exe scripts/verify-flowable.py
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-examples.py
node scripts/verify-diagnostic-lint.mjs
backend/.local/venv/Scripts/python.exe scripts/verify-diagnostic-review.py
```

The second command requires a running engine and verifies six complete execution paths,
exclusive routing, threshold results and actual SVG output using the official Python client.
The third runs thirteen scenarios across the four added diagrams. The last checks all five diagrams
against the complete lint configuration, XML round-trips and ordinary BPMN join validation.
The review script verifies waiting, repeated and selective rechecks, A/B result isolation,
invalid/stale requests and explicit final confirmation. Existing example checks now explicitly
confirm escalation before checking process completion.
