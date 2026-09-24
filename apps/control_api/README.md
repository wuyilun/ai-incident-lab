# Control API

FastAPI REST/SSE、单环境编排、SQLite 持久化。输入：控制请求和模拟 tick；输出：公开状态、事件、评估。依赖 simulator、MCP、evaluator、共享合约。扩展路由保持真值与 MCP 隔离。

验证：`pytest tests/test_integration.py`（Python 命令从仓库根目录运行，前端命令在 apps/frontend 运行）。

扩展步骤见仓库 `docs/architecture/extensions.md`。
