# Cooling system: standalone Python project and workflow integration

[简体中文](README.zh-CN.md) · [Complete walkthrough](../../../docs/USER-GUIDE.md#7-second-complete-example-a-cooling-system-python-project)

This standard-library business project manages its own simulated equipment, measurement objects, threshold files, and temperature charts. It imports neither Flowable nor the platform executor. All equipment operations are simulated.

Run it independently from the repository root:

```powershell
python backend/examples/cooling_project/run_demo.py --scenario fan
```

The fan fault recovers temperature from 85 C to 42 C. Scenarios are `filter`, `fan`, `healthy`, `unknown`, and `fan_stuck`; the last two mean no matching cause and a remediation error. Add `--report PATH.svg` to save a chart.

Register it with the platform and prepare an execution bundle:

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs
```

The preparation script creates this project's `.venv`, registers module `cooling_lab.api` and class `CoolingSession`, and writes `backend/.local/cooling-example-parallel/`. It is separate from the business project, which remains independently executable. Use `--python` to select an existing interpreter if the default is unavailable.

Import this directory or the generated `source.bpmn` in the editor, then start Java and the matching worker as described in the guide. Startup defaults are `scenario=fan` and `device_id=COOL-01`.

The two sibling paths in `workflow.json` use the original `Measurement` results from `air_sample` and `fan_sample`. A matching cause proceeds through conclusion, remediation, and verification. Only a normal temperature reaches Problem Solved; its report includes a displayable SVG chart.

For the serial example:

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs --mode serial
```

Import `backend/.local/cooling-example-serial/source.bpmn` and start a worker with that directory's `bindings.json`. The `filter` scenario pauses after success so you can finish or continue the other path. Each scenario presets at most one recoverable fault; combined multi-fault recovery is outside this example.

`assets/limits.csv` is both the file actually read by Python and a diagram reference. After editing it, prepare a new bundle and reimport the diagram for new runs so both copies agree. Move or distribute the entire project: portable diagnostic export contains the workflow and resources, not Python source or environments.
