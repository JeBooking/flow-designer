# Cooling system: standalone Python project and workflow integration

[简体中文](README.zh-CN.md) · [Complete walkthrough](../../../docs/USER-GUIDE.md#14-example-connecting-the-cooling-system-project)

This standard-library business project manages its own simulated equipment, measurement objects, threshold files, and temperature charts. It imports neither Flowable nor the platform executor. All equipment operations are simulated.

## Run in the platform

1. Prepare the platform environment as described in the [user guide](../../../docs/USER-GUIDE.md), then start the platform from the repository root:

   ```powershell
   pnpm dev
   ```

2. Open **Python Projects** and register the existing project with these values:

   | Field | Value |
   | --- | --- |
   | Project directory | `backend/examples/cooling_project` (relative to the repository root), or an absolute path such as `D:/workspace/vue-bpmn-designer/backend/examples/cooling_project` |
   | Interpreter | The executable path of an existing, prepared Python interpreter; this example uses only the standard library and does not require a project `.venv` |
   | Module | `cooling_lab.api` |
   | Class | `CoolingSession` |

3. Choose **Import project directory** and select the entire `backend/examples/cooling_project` directory. This restores `workflow.json` and its relative reference files together.
4. Open **Diagnostic Execution**, keep the default inputs `scenario=fan` and `device_id=COOL-01`, and start execution. The platform prepares the worker automatically when execution starts.

The fan fault recovers temperature from 85 C to 42 C. Scenarios are `filter`, `fan`, `healthy`, `unknown`, and `fan_stuck`; the last two mean no matching cause and a remediation error.

The two sibling paths in `workflow.json` use the original `Measurement` results from `air_sample` and `fan_sample`. A matching cause proceeds through conclusion, remediation, and verification. Only a normal temperature reaches Problem Solved; its report includes a displayable SVG chart.

To run serially, change the execution mode in the process properties and start a new instance; no bundle regeneration is needed. The `filter` scenario pauses after success so you can finish or continue the other path. Each scenario presets at most one recoverable fault; combined multi-fault recovery is outside this example.

`assets/limits.csv` is both the file actually read by Python and a diagram reference. After editing it, reimport the project directory or reselect the reference file, then start a new instance so the reference agrees with the business file. This does not update existing instances. Move or distribute the entire project: portable diagnostic export contains the workflow and resources, not Python source or environments.

## Optional standalone demo and preparation tool

The standalone demo is optional and is not a prerequisite for platform integration. Run it from the repository root:

```powershell
python backend/examples/cooling_project/run_demo.py --scenario fan
```

Add `--report PATH.svg` to save a chart.

For offline preparation or debugging compiled artifacts, the repository also provides an optional script:

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs
```

The script creates this project's `.venv` if needed, registers module `cooling_lab.api` and class `CoolingSession`, and writes `source.bpmn` and the compiled execution bundle to `backend/.local/cooling-example-parallel/`. Use `--python EXECUTABLE` to select the interpreter used by the preparation script and to create the example environment; use `--mode serial` for artifacts under `backend/.local/cooling-example-serial/`. These artifacts are useful for debugging and are not required for ordinary platform execution. Open the platform, import the generated `source.bpmn`, and start execution; the platform prepares the worker automatically.
