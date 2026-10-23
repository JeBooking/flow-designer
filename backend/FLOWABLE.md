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

Open **Flowable execution**, load the diagnostic example (export your current diagram first),
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
```

The second command requires a running engine and verifies six complete execution paths,
exclusive routing, threshold results and actual SVG output using the official Python client.
