# 冷却系统：独立 Python 工程与流程接入示例

[English](README.md) · [完整使用步骤](../../../docs/USER-GUIDE.zh-CN.md#14-示例冷却系统工程接入)

这是一个仅用 Python 标准库实现的业务工程。设备、采集对象、阈值文件和温度图表都由工程自己管理；不导入 Flowable 或平台执行器。所有设备操作均为模拟。

## 在平台中执行

1. 按[用户手册](../../../docs/USER-GUIDE.zh-CN.md)准备平台环境，然后在仓库根目录启动平台：

   ```powershell
   pnpm dev
   ```

2. 打开 **Python 项目**，登记已有工程：

   | 字段 | 值 |
   | --- | --- |
   | 项目目录 | `backend/examples/cooling_project`（相对仓库根目录），或绝对路径，例如 `D:/workspace/vue-bpmn-designer/backend/examples/cooling_project` |
   | 解释器 | 已准备好的现有 Python 解释器可执行文件路径；本例只用标准库，不强制创建工程 `.venv` |
   | 模块 | `cooling_lab.api` |
   | 类 | `CoolingSession` |

3. 选择 **导入项目目录**，选中整个 `backend/examples/cooling_project` 目录，一起恢复 `workflow.json` 和相对路径引用的参考文件。
4. 打开 **诊断执行**，保留默认输入 `scenario=fan`、`device_id=COOL-01`，开始执行。平台会在开始执行时自动准备 worker。

风机故障场景会把温度从 85 C 恢复至 42 C。可选择 `filter`、`fan`、`healthy`、`unknown`、`fan_stuck`；后两者分别表示未匹配原因和处置报错。

`workflow.json` 的两条并列思路分别使用 `air_sample` 和 `fan_sample` 节点返回的原生 `Measurement` 对象。命中的故障经过结论和处置后复采，确认温度正常才到问题解决，并返回可显示的 SVG 图表。

切换串行执行时，在流程属性中切换执行模式，然后开始新实例，无需重新生成执行包。`filter` 场景会成功暂停，用户可选择结束或继续另一条思路。每个场景只预设一种可恢复故障；本例不实现多故障联合恢复。

`assets/limits.csv` 同时是 Python 读取的真实阈值文件和图上的参考文件；修改后重新导入工程目录，或重新选择参考文件，再开始新实例，以保持参考内容与业务文件一致。这不会更新旧实例。移动或分发时带上整个工程；导出诊断项目只保存流程和资源，不包含 Python 源码及环境。

## 可选的独立演示与准备工具

独立演示不是接入平台的前置条件。需要时，在仓库根目录运行：

```powershell
python backend/examples/cooling_project/run_demo.py --scenario fan
```

加 `--report PATH.svg` 可保存温度图。

需要离线准备或调试编译产物时，也可以使用仓库提供的可选脚本：

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs
```

脚本会在需要时创建本工程的 `.venv`，登记模块 `cooling_lab.api` 和类 `CoolingSession`，并将 `source.bpmn` 和编译后的执行包写入 `backend/.local/cooling-example-parallel/`。加 `--python EXECUTABLE` 可选择运行准备脚本和创建示例环境的解释器；加 `--mode serial` 会将产物写入 `backend/.local/cooling-example-serial/`。这些产物用于调试，普通平台执行不需要此步骤。打开平台，导入生成的 `source.bpmn` 并开始执行，平台会自动准备 worker。
