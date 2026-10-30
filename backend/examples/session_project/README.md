# Native Python device session

[简体中文](README.zh-CN.md)

Register project directory `backend/examples/session_project`, module `device_session`,
and factory `Device`. Use the existing Python 3.9+ environment; no extra dependencies
are needed. `create_session` is an alternative factory returning the same class.

Follow the [user guide](../../../docs/USER-GUIDE.md) for the complete walkthrough.
This directory includes `workflow.json` and `assets/voltage-reference.txt`. Choose
**Import project directory** and select this folder to restore the bound example workflow.

In **Python Projects**, call `collect`, `restore`, then `verify` in the same debug
session. The initial reading is 22.6 V; verification after recovery returns `True`.
Reset the session and collect again to get the initial reading. These actions are simulated.

For a workflow, use this sequence, following the existing node connection rules:

1. Start → an investigation bound to `ready`, whose Yes group leads to acquisition.
2. An investigation action with node ID **`reading`**, bound to `collect` → an
   investigation bound to `is_low`. Its `reading` parameter receives the original
   `Reading` instance stored under that node ID.
3. The `is_low` Yes group → a conclusion → a remediation bound to
   `restore_and_verify` → Problem Solved.

`restore_and_verify` performs recovery and async verification in the same instance;
failed verification raises a task error instead of reporting the problem solved.
For this recovery-only example, leave the `is_low` No group without an outlet:
a normal reading records this idea as failed. A broader normal-check path needs
its own valid conclusion/outcome chain. Fill required node descriptions and reference
files as usual. Investigations do not connect directly to Problem Solved, and
remediations do not lead back to investigations.

In the execution startup form, set `device_id` to `M01` and `threshold` to `24`, or
leave them blank to use constructor defaults. The advanced JSON override is optional:
`{"device_id":"M01","threshold":24}` (or `{}` for defaults).
`ready` returns `True`. `restore` needs no parameters and returns `None`; `verify`
is async, and `restore_and_verify` is an async action returning `None`. Internal
`latest`, `attempts`, and `recovered` remain on the instance and need no form inputs.
`Reading` remains a Python object; the browser/Flowable representation is only a
display projection. Rechecking reruns a method on the current instance and does
not roll its state back. The module declares stateless globals, and `Device`/`Reading` implement checkpoint hooks. Real workflow execution can restore the same native reference graph after worker/backend restart without calling the device constructor or replaying completed actions. Safe interpreters are released at human waits. Interface-debug sessions remain temporary. See [recovery](../../../docs/RECOVERY.md).
