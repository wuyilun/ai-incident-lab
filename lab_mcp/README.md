# MCP and safety

官方 SDK Streamable HTTP。输入：运行令牌和类型化工具参数；输出：经审计的观察/动作结果。所有环境动作经过独立 safety policy，默认拒绝不在 allowlist 的操作。

验证：`pytest tests/test_integration.py`（Python 命令从仓库根目录运行，前端命令在 apps/frontend 运行）。

扩展步骤见仓库 `docs/architecture/extensions.md`。
