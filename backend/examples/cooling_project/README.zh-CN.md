# 冷却系统：独立 Python 工程与流程接入示例

[English](README.md) · [完整使用步骤](../../../docs/USER-GUIDE.zh-CN.md#7-第二个完整示例冷却系统-python-工程)

这是一个仅用 Python 标准库实现的业务工程。设备、采集对象、阈值文件和温度图表都由工程自己管理；不导入 Flowable 或平台执行器。所有设备操作均为模拟。

从仓库根目录先独立运行：

```powershell
python backend/examples/cooling_project/run_demo.py --scenario fan
```

风机故障场景会把温度从 85 C 恢复至 42 C。可选择 `filter`、`fan`、`healthy`、`unknown`、`fan_stuck`；后两者分别表示未匹配原因和处置报错。加 `--report PATH.svg` 可保存温度图。

接入平台并生成执行包：

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs
```

准备脚本创建本工程的 `.venv`、登记模块 `cooling_lab.api` 和类 `CoolingSession`，并生成 `backend/.local/cooling-example-parallel/`。脚本与业务工程分离，因此业务代码仍可独立运行。默认 Python 不可用时，加 `--python` 指定现有解释器。

在页面导入本目录，或导入生成的 `source.bpmn`；按用户手册启动 Java 服务和相应 worker。默认启动输入是 `scenario=fan`、`device_id=COOL-01`，可直接使用默认值。

`workflow.json` 的两条并列思路分别使用 `air_sample` 和 `fan_sample` 节点返回的原生 `Measurement` 对象。命中的故障经过结论和处置后复采，确认温度正常才到问题解决，并返回可显示的 SVG 图表。

切换串行示例时运行：

```powershell
pnpm exec node scripts/prepare-cooling-example.mjs --mode serial
```

导入 `backend/.local/cooling-example-serial/source.bpmn`，使用同目录的 `bindings.json` 启动 worker。`filter` 场景会成功暂停，用户可选择结束或继续另一条思路。每个场景只预设一种可恢复故障；本例不实现多故障联合恢复。

`assets/limits.csv` 同时是 Python 读取的真实阈值文件和图上的参考文件；修改后为新运行重新准备执行包并重新导入图，以保持两者一致。移动或分发时带上整个工程；导出诊断项目只保存流程和资源，不包含 Python 源码及环境。
