# Agent runner

独立进程，仅通过 MCP 观察和操作。输入：绑定事件的运行令牌和执行模式；输出：结构化证据与工具调用。Reference 基线和 LLM 适配器共享 ToolClient。部署不包含模拟器、评估器、数据库或 SOP 文件。

验证：`pytest tests/test_integration.py`（Python 命令从仓库根目录运行，前端命令在 apps/frontend 运行）。

扩展步骤见仓库 `docs/architecture/extensions.md`。
