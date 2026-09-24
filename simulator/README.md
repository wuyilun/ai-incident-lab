# Causal world

JSON Scenario 经共享 schema 校验，种子驱动连接资源随 tick 演化。输入：故障注入/受控动作；输出：指标、日志、配置的公开投影。私有 leak_intensity 不进入观察。

验证：`pytest tests/test_core.py`（Python 命令从仓库根目录运行，前端命令在 apps/frontend 运行）。

扩展步骤见仓库 `docs/architecture/extensions.md`。
