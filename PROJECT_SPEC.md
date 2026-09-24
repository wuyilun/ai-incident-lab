# Incident Agent Lab v0.1

实现可重复、可观察的故障响应实验室。原始需求参考 `project_prompt.md`；本规格定义实际 v0.1 范围。

## 验收闭环
`docker compose up --build` → 打开控制台 → 注入连接泄漏 → 因果退化 → 阈值告警 → Agent 经 MCP 观察 → 加载诊断 Skill → 检索 SOP → 安全策略审核 → 重启 Worker → 连续采样验证 → 独立评估 → 历史回放。

默认 Reference Agent 不需要密钥，明确标示为确定性基线；LLM Agent 使用相同 MCP 合约。模拟 API、Redis、Worker 是逻辑服务，不伪装为真实生产 Redis。

## 合约
- Event: version, sequence, event_id, timestamp, event_type, source, incident_id, run_id, payload；SQLite 递增序号作为流和回放游标。
- Scenario: Pydantic 严格验证 JSON；包含 fault、target、ground_truth、allowed/forbidden actions、success；禁止代码执行。
- MCP: 官方 Python SDK Streamable HTTP，观察、SOP、受限操作、结构化进度、生命周期工具。运行令牌绑定 incident/run，禁止读取评估和场景真值。
- 生命周期: degrading → detected → investigating → diagnosing → planning → acting → verifying → resolved / failed / cancelled。
- 评估结果只依赖真实环境状态、隐藏真值和持久化轨迹；不信任 Agent 自报成功。

## 实施检查表
- [x] 0 基础结构、合约、配置
- [x] 1 种子驱动模拟、因果退化、恢复
- [x] 2 SQLite 事件、控制 API、SSE
- [x] 3 MCP、作用域、安全策略
- [x] 4 Reference / LLM Agent、Skill、预算、取消
- [x] 5 独立确定性评估
- [x] 6 React 控制台、指标、轨迹、回放
- [x] 7 多 seed / trial 基准和汇总
- [x] 8 单元、集成、E2E、lint、构建、文档、Compose 启动和闭环验收
