# Execution monitoring and business recovery

[简体中文](RECOVERY.zh-CN.md)

## Monitoring existing instances

The latest monitored instance ID and ten recent IDs are persisted. Refreshing the page or recreating
the modeler reconnects the latest instance; no business results are stored in browser persistence.
In **Diagnostic execution**, enter or select an ID and choose **Resume monitoring** to inspect another
instance and continue its pending tasks. **Stop monitoring** detaches the view without cancelling it.

Import the original workflow to associate the canvas. The backend compares execution signatures;
until they match, history and task cards remain available and canvas highlights stay hidden.
Changing the diagram invalidates that association. A failed attempt to connect another ID preserves
an already loaded monitor. An unavailable or deleted instance can be detached to start another run.

History requests use opaque cursors and variable revisions. Only changed values, new/completed
activities, removals and changed task/failure information are transferred. Unchanged polling backs
off from 1.5 to at most 10 seconds; a review immediately refreshes it. Expired cursors, backend restart
and cache eviction trigger a full snapshot. Ended instances continue to read historical data.

## Enabling business checkpoints

Flowable persists execution and human waits. A business checkpoint additionally saves Python state
that the project has explicitly declared recoverable. It is independent of display projections and
never reconstructs native values from `repr`. Interface-debug sessions remain temporary.

A module with no mutable business globals can declare:

```python
__diagnosis_stateless__ = True
```

This applies to module globals, not factory instances. A module that does maintain global state
provides synchronous or async `__diagnosis_checkpoint__()` and `__diagnosis_restore__(state)` hooks
instead; its exported state must be JSON compatible. Restore must not replay past equipment actions.

Factory instances and native objects in results provide synchronous object hooks:

```python
__diagnosis_stateless__ = True

class Device:
    def __diagnosis_checkpoint__(self):
        return {'count': self.count, 'latest': self.latest}

    @classmethod
    def __diagnosis_restore__(cls, state):
        device = object.__new__(cls)
        device.__dict__.update(state)
        return device
```

If `latest` is native, its class also implements these hooks. The codec preserves shared object
identity between instance state and node results. JSON scalars, string-keyed dictionaries, lists and
tuples are supported; custom-object cycles require a different project representation. Types must
belong to the registered project. No pickle, arbitrary constructor replay or automatic conversion of
display projections is used. The [device session example](../backend/examples/session_project/README.md)
implements the protocol for both `Device` and `Reading`.

Device connections and external handles should export stable identifiers/configuration and reconnect
in the restore hook. Reconnecting must not issue an earlier remediation again. Projects remain
responsible for the correctness of their declared state and for thread safety during parallel calls.

## Persistence and restart behavior

Before a business call, the worker atomically records that an action is in flight. Once all concurrent
calls in that session have finished, it captures state and caches their responses before acknowledging
Flowable jobs. A recovered delivery of the same job uses its cached response; it does not invoke the
business function again. Confirmed jobs release their response cache.

When all work is waiting for humans, a complete checkpoint allows the idle business interpreter to
exit. The coordinator remains subscribed. Backend startup scans active definitions and recreates
missing coordinators; the next call restores the session and native references. Expired worker locks
still follow Flowable's lock lifecycle; restart never steals a lock. Completed instances release their
local checkpoints once observed by the worker.

Checkpoints are under `backend/.local/checkpoints/`, scoped to engine URL, execution version, instance
and project identity. Writes use temporary files, flush/fsync and atomic replacement. Snapshots are
limited to 64 MiB and validate source files, Python/dependency versions and the original session ID.
Keep this directory with the local engine data when moving a recoverable installation.

The execution panel shows whether the latest call saved a recoverable checkpoint. Unsupported state
retains the live interpreter and reports the missing protocol. A crash during an unfinished action,
a missing/incomplete checkpoint, changed source or dependencies, or a failed restore refuses automatic
recovery. Confirm actual equipment state before deciding how to continue; neither a restart nor a
checkpoint can prove the outcome of an external action interrupted before its result was recorded.
An explicit recheck still reruns business code on current state and may repeat actions.

## Prebuilt Java runtime

Download `diagnostic-flowable-runtime` from a successful **Verification** workflow for the same source
commit. Place both the JAR and its `.manifest.json` under `flowable-runtime/target/`. The launcher checks
source and JAR hashes, normalizing text line endings. Changed checkout timestamps do not force Maven.
Matching artifacts need Java 17+, Python 3.9+, Node/pnpm and frontend dependencies; source builds need
JDK 17+ and Maven 3.8.8+. No automatic download from an unverified release is performed.

Run `pnpm verify` for regression coverage, including incremental history, persisted monitor IDs,
native checkpoint identity, idle release, backend restart and concurrent review records.
