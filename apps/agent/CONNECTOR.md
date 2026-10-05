# 外部 Agent 接入

在页面「Agent 接入中心」注册外部 Agent，保存仅显示一次的令牌和 Agent ID。在仓库根目录运行：

```sh
export INCIDENTLAB_AGENT_TOKEN='<页面生成的注册令牌>'
uv run python -m apps.agent.connector --url http://localhost:8000 --agent-id '<Agent ID>' --mode reference
```

接入状态变为在线后，在实验台选择此 Agent 并触发故障。Connector 轮询告警、确认接收，再使用独立短期令牌通过官方 MCP 客户端执行诊断 Skill、查询 SOP、修复并验证；页面显示同一执行过程。注册令牌只从环境变量读取，不记录到事件或日志。建议用终端安全输入或进程环境注入令牌，避免写入 shell 历史。

`--mode llm` 复用现有 LLM handler，需配置 `LLM_API_KEY`，可选 `LLM_BASE_URL`、`LLM_MODEL`。`--once` 在一个任务结束后退出；`--poll-seconds` 默认 1 秒。退出码 0 表示已验证修复，1 表示配置、接入或任务失败，130 表示手动终止。

执行中每 5 秒心跳并幂等确认当前任务。短暂控制接口断线最多重试三次；失效注册令牌立即退出。任务取消或短期凭据撤销会终止 handler。单次诊断沿用 75 次工具调用、2 次变更动作和至多 115 秒预算；任务失败尽力通过 MCP `fail_incident` 记录。MCP 变更不会因网络错误自动重试，同一进程内重复投递的 run 不会重执行。

扩展其他 Agent 时替换 `connector.execute` 中的 handler，保留 inbox 鉴权、确认、心跳和超时控制。Handler 仅接收 `ToolClient`，通过 `call` / `report` 使用 MCP；不得读取模拟器、持久层、评估器或场景真值。运行结果必须经过新鲜指标验证并调用 `resolve_incident`，失败调用 `fail_incident`。该轮询协议面向单个 connector 进程；请勿为同一注册 Agent 同时启动多个进程。
