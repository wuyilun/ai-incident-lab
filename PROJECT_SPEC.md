# Incident Agent Lab v0.3

实现可重复、可观察的故障响应实验室。原始需求参考 `project_prompt.md`；本规格定义实际 v0.3 范围。

## 验收闭环
`docker compose up --build` → 打开控制台 → 注入连接泄漏 → 因果退化 → 阈值告警 → Agent 经 MCP 观察 → 加载诊断 Skill → 检索 SOP → 安全策略审核 → 重启 Worker → 连续采样验证 → 独立评估 → 历史回放。

默认 Reference Agent 不需要密钥，明确标示为确定性基线；LLM Agent 使用相同 MCP 合约。模拟网关、API、Worker、Redis、数据库、队列是逻辑服务，不伪装为真实生产 Redis。

## 合约
- Event: version, sequence, event_id, timestamp, event_type, source, incident_id, run_id, payload；SQLite 递增序号作为流和回放游标。
- Scenario: Pydantic 严格验证 JSON；包含 fault、target、ground_truth、allowed/forbidden actions、success；禁止代码执行。
- MCP: 官方 Python SDK Streamable HTTP，观察、SOP、受限操作、结构化进度、生命周期工具。运行令牌绑定 incident/run，禁止读取评估和场景真值。
- 生命周期: degrading → detected → dispatching → investigating → diagnosing → planning → acting → verifying → resolved / failed / cancelled。
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

## v0.3 Agent 接入与可视化
- [x] 注册、连接检查、启停、令牌轮换与在线状态。
- [x] 外部 Connector 主动领取告警，真实接收确认，运行级 MCP 鉴权。
- [x] 左侧环境、右侧执行/报告的双栏实验工作台。
- [x] 三条对齐趋势图、关键事件标记、统一游标回放、报告下载。
- [x] 注册令牌隔离、重复投递、取消撤权与真实 Connector 集成回归。

详细设计与接口约定见 [产品设计](docs/product/agent-workbench.md)；实际验证结果见 [验证记录](docs/verification.md)。

## v0.3 扩展与直接接入
- 六节点配置驱动拓扑，五种因果故障，场景选择和相关指标展示。
- 单注册令牌直连MCP，自检/收警/Skill获取/调查/SOP修复/验证均在MCP内完成。
- 注册令牌的变更请求必须携带本次run_id，旧任务请求不会影响新实验。
- 基于实际评估的排行榜，场景宏平均和覆盖率加权，展示样本量与未参评状态。
- [扩展说明](docs/architecture/extending-environments.md)与[MCP接入](docs/guides/mcp-agents.md)。
