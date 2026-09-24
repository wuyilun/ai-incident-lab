# Deterministic evaluator

输入：私有 scenario 期待、实际环境状态、事件轨迹。输出：结果、根因、修复、安全、效率的独立指标。不得信任 Agent 自报成功或健康计数。

验证：`pytest tests/test_core.py tests/test_integration.py`（Python 命令从仓库根目录运行，前端命令在 apps/frontend 运行）。

扩展步骤见仓库 `docs/architecture/extensions.md`。
