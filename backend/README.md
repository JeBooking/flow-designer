# Local Python project integration / 本地 Python 工程接入

## 启动 / Start

在仓库根目录开两个终端 / From the repository root:

```sh
python backend/server.py
pnpm dev
```

打开 Vite 提示的网页，点击顶栏 **Python 项目**。开发服务器将 `/api` 转发给
`127.0.0.1:8765`。修改 Vite 配置后需要重启 `pnpm dev`。
Alternatively run `pnpm build-only`, then open
`http://127.0.0.1:8765/vue-bpmn-designer/`; the Python server also serves `dist`.

## 接入已有工程 / Register a project

1. 将外部工程复制到本仓库的任意子目录，或保留在已有目录。
2. 填写该目录；相对路径从本仓库根目录计算，绝对路径也支持。
3. 填写 Python 入口模块，例如 `plotting.api` 或导出函数的包名 `plotting`。
4. 可指定工程虚拟环境中的 Python，例如 `D:\plotting\.venv\Scripts\python.exe`；
   留空使用后端的 Python。依赖必须已经安装在选定环境中。
5. 点击接入，查看函数名、签名和文档，选择函数后即可调用。

注册只引用本地路径，不自动下载、安装、复制或覆盖工程。
The project remains a normal, independently maintained Python project. Register
its local path and importable entry module. Choose an existing interpreter if it
requires a virtual environment; dependencies are not installed automatically.

入口包可用正常的 Python 导出方式 / Ordinary Python exports:

```python
# plotting/__init__.py
from .charts import draw_chart
from .parser import parse_data

__all__ = ['draw_chart', 'parse_data']
```

有 `__all__` 时只展示其导出的函数；没有时展示入口模块自身定义的公开函数。
平台会把工程的 `src/`、根目录和父目录加入该次执行的 Python 搜索路径，支持普通包和 src 布局。
If `__all__` is present it selects exported functions, including re-exports;
otherwise only public functions defined by the entry module are exposed.

## 快速验证 / Quick check

点击“填入示例项目”，然后“接入项目”，选择 `summarize`：

- 位置参数 / args: `[[2, 4, 6]]`
- 关键字参数 / kwargs: `{}`
- 结果 / result: `{"count": 3, "mean": 4.0}`

`draw_chart` 示例会在示例工程目录生成 SVG，并返回路径。
这只是接入示例，不要求实际项目采用它的数据格式或绘图方法。

## Platform API

- `GET /api/projects`: 已登记工程和接口列表。
- `POST /api/projects`: `{ "path": "...", "module": "plotting", "python": "可选", "name": "可选" }`
- `POST /api/projects/{id}/refresh`: 重新导入并读取接口。
- `POST /api/projects/{id}/call`: `{ "function": "draw_chart", "args": [], "kwargs": {} }`
- `POST /api/projects/{id}/remove`: 移除登记，不删除源文件。

调用只是把通用 JSON 位置/关键字参数传给 Python 函数，不定义业务输入输出协议。
JSON 兼容返回值直接传回；其他 Python 对象返回 `repr` 文本并标记 `representation: "repr"`，
不等于把该对象传递给另一模块。函数内部可以自由导入和组合工程中的其他能力。
Python stdout/stderr 和异常详情保留在响应中，前端只展示原始结果。

Each discovery/call runs in a separate Python process, with the project directory
as its working directory. No cross-call Python object/session state is retained.
Desktop-window calls may wait until the window closes; use a noninteractive entry
when appropriate. The default operation timeout is 120 seconds, adjustable with
`python backend/server.py --timeout 600`. A timeout stops the worker but cannot
undo external side effects. The current scope is project registration/discovery/
invocation, not BPMN node binding or full workflow execution.

登记在 `backend/.local/projects.json` 持久保存。后端绑定本机回环地址；当前是本地开发工具，
不作为带认证的多用户远程执行服务。非默认本机前端来源可通过 `--origin URL` 添加。

## Verification

```sh
python scripts/verify-python-projects.py
```

使用临时目录和真实 HTTP 请求，验证工程接入、函数发现、调用、图表文件生成、同名模块隔离、
登记持久化、刷新、移除和失败返回。
