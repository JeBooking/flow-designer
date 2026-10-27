# Automatic decisions and human handling examples

[English](README.md) | [中文](README.zh-CN.md)

This independent Python project demonstrates automatic routing, human review, component fallback,
and an intentional Python failure. It has no factory and requires no third-party business dependencies.
It uses supplied voltage data; it does not acquire data from or operate equipment.

## Start and register once

Complete the platform preparation in the [user guide](../../../docs/USER-GUIDE.md#2-prepare-once-then-start-each-run),
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

## Import a diagram and start it

1. Save your current canvas before importing.
2. Use the main designer's **Import BPMN or workflow.json** control and select one standalone `.bpmn`
   file from this project's [diagrams](diagrams/) directory. These files are not entries in an execution
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

## Coverage and expected behavior

The human switch below refers to **Human decision / confirmation** on Check.

| Diagram | Check interface / human switch | Trigger | Expected result |
| --- | --- | --- | --- |
| [01-automatic.bpmn](diagrams/01-automatic.bpmn) | `automatic_decision` / off | Returns Yes when `voltage >= 22`, otherwise No | Check routes automatically; `21.2` reaches Escalation, `24` reaches Problem Solved |
| [02-manual-only.bpmn](diagrams/02-manual-only.bpmn) | No Python interface / on | Check is configured for direct human judgment | Waits for a human Yes/No choice without a Python call at Check |
| [03-bound-manual.bpmn](diagrams/03-bound-manual.bpmn) | `collect_evidence` / on | Python returns evidence, then the node requests review | Shows evidence and waits for a human Yes/No choice |
| [04-base-fallback.bpmn](diagrams/04-base-fallback.bpmn) | `base_fallback` / off | `DecisionComponent.decide` is not overridden | Component protocol requests human judgment |
| [05-decorator-fallback.bpmn](diagrams/05-decorator-fallback.bpmn) | `decorator_fallback` / off | A function wrapped by `@decision` raises `NotImplementedError` | Decorator converts the unimplemented judgment into a human request |
| [06-explicit-review.bpmn](diagrams/06-explicit-review.bpmn) | `explicit_review` / off | Explicitly returns a human judgment request | Waits for a human Yes/No choice without requiring the node's human switch |
| [07-ordinary-error.bpmn](diagrams/07-ordinary-error.bpmn) | `ordinary_unimplemented` / off | An ordinary function directly raises `NotImplementedError` | Expected Python execution failure with traceback; no human review occurs |
| [08-empty-result.bpmn](diagrams/08-empty-result.bpmn) | `empty_decision` / off | The function body uses `pass`, returning `None` | Expected `ValueError`: an investigation must return Yes/No; no human review occurs |

## Handle the review card

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

## Boundaries

Only the component protocol turns an unimplemented judgment into human handling. A plain `pass` or
`None` return does not request human review, as diagram 08 demonstrates. Diagram 03
waits because its human switch is enabled, not because returning evidence itself implies fallback.

These examples cover investigation judgments. The execution UI currently has no unified form for
manually entering acquisition results or confirming completion of arbitrary business actions.
The Yes/No review must not be presented as either of those capabilities. This guide describes the
expected behavior; it does not claim that the examples have been run on your machine.
