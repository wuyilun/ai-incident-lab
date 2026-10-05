# 一个 MCP 地址与一个注册令牌

在页面「Agent 接入中心」注册外部 Agent，复制 MCP 服务地址与令牌。
支持 Streamable HTTP 的 Agent 只需配置 URL `http://localhost:5173/mcp` 和 HTTP header `Authorization: Bearer <注册令牌>`。页面提供可复制的 `mcpServers` 配置；不同客户端的配置文件结构可能不同，URL 和 header 相同。不需要 Agent ID、REST inbox、webhook 或额外运行令牌。

给接入 Agent 的操作指令：

> 调用 check_connection 验证接入。每秒调用 receive_alert 等待告警；assignment=null 表示暂无任务。拿到任务后保存 run_id，调用 get_diagnostic_skill，按其方法使用 MCP 指标、日志、配置和依赖调查。报告有证据支持的根因，再检索 get_sop。所有变更与产物工具均传入本次 run_id；修复后采集多个不同 tick 的健康样本，再 resolve_incident。失败时 fail_incident，完成后继续接收下一告警。不要把上一次任务的 run_id 用于新任务。

注册令牌持续用于同一 Agent。空闲轮询/连接自检刷新在线状态；每次任务有独立运行范围。停用或轮换会使旧注册令牌失效；取消、超时或结束后旧 run_id 的动作被拒绝。

## 无模型的直接接入验证

在项目根目录安全设置 `INCIDENTLAB_AGENT_TOKEN` 环境变量，然后执行：

```bash
uv run python scripts/mcp_agent.py --url http://localhost:5173/mcp --once
```

脚本只使用官方 MCP 客户端；打开页面，选择刚注册的在线 Agent 并注入故障。默认 Reference 是确定性的证据诊断基线。省略 `--once` 持续接收任务；`--mode llm` 使用现有 LLM Adapter，需要模型配置。令牌不通过命令行参数传递，也不写入日志。

旧 `apps.agent.connector` 的 REST inbox 协议仅为已有集成兼容保留；新接入使用上述直接 MCP 方式。
