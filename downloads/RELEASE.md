内网试用包 / Offline trial

源码版本 / Source revision: 516c29ec794763cf4155a8187d7285203f0768ad

要求：Windows、Node.js 22、Python 3.9+（含 venv/pip）、Java 17 或更高版本。
完整解压到新目录，双击 start.cmd。首次会从自带 wheels 目录离线安装平台 Python 依赖。
浏览器打开 http://127.0.0.1:8765/vue-bpmn-designer/ ，终端保持打开。
无需 pnpm install、前端构建或 Maven，也不需要连接 Maven/Python 软件源。
业务工程需要的依赖、设备连接仍由业务工程提供。
不包含你原有的流程数据、登记信息、密码、日志或虚拟环境。
试用后 Java 源码变更需重新打包；前端源码变更需重新构建前端。
如 JAVA_HOME 指向旧 Java，请先指向 Java 17；可设置 PYTHON 选择 Python 解释器。
关闭终端或 Ctrl+C 停止本次启动的服务。日志位于 backend/.local/logs。

Requires Node.js 22, Python 3.9+ with venv/pip, and Java 17 or later.
Extract fully to a new directory and run start.cmd. Keep the terminal open.
Platform Python dependencies are installed from bundled wheels without network access.
No Maven or frontend installation is needed. Business dependencies remain your responsibility.
The launcher in this bundle uses offline pip arguments; the repository source is otherwise unchanged.
