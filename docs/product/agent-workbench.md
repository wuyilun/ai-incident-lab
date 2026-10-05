# Agent 接入与故障实验台 — v0.2 产品及接口设计

## 目标
用户先注册并接入 Agent，选择该 Agent 注入故障。真实阈值告警产生后自动路由；Agent 收到告警、经 MCP 调查环境、运用 Skill / SOP 修复。左右并排观察世界与执行过程，共用下方事件标注趋势图与回放游标。

## 信息架构
- 故障实验台：顶部实验选择/已注册响应 Agent/注入；左侧环境拓扑、状态、可观测指标；右侧 Agent 身份、告警接收状态、过程/诊断报告切换；下方三个同步横轴趋势图和关键事件。
- Agent 接入中心：注册（内置 Reference、内置 LLM、外部 Agent）；连接状态、最后联系时间、启停、连接检查、凭据轮换；外部注册后仅本次显示接入令牌和可复制启动命令。
- 历史实验：在实验台选择历史事件，所有视图按同一事件游标回放。报告从当前可见事件生成，不能提前暴露未来诊断或评估。

## 接入协议
本机实验产品采用 authenticated polling inbox，不要求外部 Agent 开放入站端口；对外环境操作仍严格限定 MCP。提供可运行的 connector（reference/llm），其他 Agent 可替换 handler。

### 注册接口（控制平面）
- `GET /api/agents` -> `Agent[]`
- `POST /api/agents` body `{name,kind:"reference"|"llm"|"external",description?:string}` -> `{agent:Agent,credentials?:Credentials}`
- `PATCH /api/agents/{id}` body `{name?:string,description?:string,enabled?:boolean}` -> `Agent`
- `POST /api/agents/{id}/test` -> `{ok:boolean,detail:string,agent:Agent}`（内置真实 runner health；外部检查新鲜 heartbeat）
- `POST /api/agents/{id}/rotate-token` -> `{agent:Agent,credentials:Credentials}`；执行中不允许轮换。
- Agent: `{id,name,kind,description,enabled,connection_status,last_seen,created_at}`。connection_status: `ready|online|offline|disabled|busy|unavailable`。内置默认注册项 IDs 为 `builtin-reference`、`builtin-llm`；LLM 未配置密钥时检查需明确不可用。
- Credentials: `{agent_id,token,poll_path}`；token 不写事件、不出现在 GET/list 中，数据库仅保存哈希。

### Connector 接口（注册令牌 Bearer 鉴权）
- `GET /api/agent-gateway/{agent_id}/next` -> `{assignment:null|Assignment}`；刷新在线状态。轮询间隔默认 1s；未确认任务可重取。
- `POST /api/agent-gateway/{agent_id}/heartbeat` -> `{status:"online"}`；执行任务时继续心跳，15s TTL。
- `POST /api/agent-gateway/{agent_id}/assignments/{run_id}/ack` -> `{accepted:true}`；幂等确认当前任务，记录真实接收事件和启动时间。跨 Agent、失效和终止任务必须拒绝。
- Assignment: `{incident_id,run_id,token,mcp_path:"/mcp",alert,timeout_seconds:120}`。token 是独立短期运行令牌，不能当注册令牌使用。不得包含 scenario_id、seed、ground_truth、evaluation。
- Connector 从配置的 control origin 拼接 mcp_path；ack 后用运行令牌进入 MCP，先接收/展示告警，然后执行 reference 或 llm handler。连接 token 从 `INCIDENTLAB_AGENT_TOKEN` 环境变量读取。命令：`uv run python -m apps.agent.connector --url http://localhost:8000 --agent-id ID --mode reference`。

### 实验兼容性
`InjectRequest` 和 `StartRequest` 新增可选 `agent_id`。显式选择优先；未传时继续支持旧 agent_mode/mode，映射内置注册项。保留旧 mode=external 的单次手工 MCP 接口以兼容已有测试/调用。Incident 增加 `agent_id`、`agent_name`、`agent_mode`（kind），持久化身份快照。

## 路由与状态
- `fault.injected`（tick=0）→ `alert.generated` → `alert.dispatched`（指定接收者）。
- 外部 Agent 等待确认时 status=`dispatching`。确认后 `agent.alert_received`、`agent.started`，status=`investigating`；内置 Agent 的收到事件应基于实际请求/工具调用，不能伪造外部心跳。
- 无接收确认在 30s 后显式失败；不得静默切换其他 Agent。执行有既有 120s 预算。
- 最终状态、取消、重启撤销短期凭据。繁忙 Agent 禁止停用/轮换。注册、凭据、告警任务不泄漏场景真值。
- 原先的单环境限制、SQLite、独立 evaluator、安全动作策略保持不变。

## 可视化合约
所有 incident-scoped event 的 payload 增加 simulator `tick`（向后兼容；旧事件可由最近 metric 的 tick 推导）。一条事件由 sequence 唯一标识，timestamp 用于显示具体时间。
- 必需标记：故障注入、告警触发、Agent 接收/介入、首次诊断、每次修复、验证完成、事件恢复。
- 同 tick 不同事件不能互相覆盖：趋势图用事件序号/标签或单独 marker rail 排列，点击定位同一 replay cursor；图上保留垂直参考线。
- 三个指标分别用自己的单位和量纲，横轴一致；基线/异常/恢复阶段标示，hover 展示指标与当时事件。移动端左/右视图顺序堆叠。
- 最终报告：Agent 身份、诊断、证据、SOP、实际执行动作、验证、独立评估、故障前后指标；允许下载，缺失内容明确“未产生”，不能用固定成功文案填充。

## 验收
1. 页面完成注册并得到凭据，未连接显示离线；启动 connector 后显示在线。
2. 选择该 Agent 注入，自动投递并确认告警；独立进程的 Agent 只经 MCP 完成修复。
3. 右侧显示注册身份和真实进度/报告，左侧环境随故障与修复变化。
4. 三条趋势图至少可见注入、接收、修复、恢复的事件标记；点击标记同步回放且无未来信息泄露。
5. 认证/跨 Agent/重复领取确认/禁用/凭据轮换/无接收超时有回归测试；既有闭环与基准兼容。
6. 前端 lint/typecheck/build、Python lint/mypy/tests、浏览器注册和实验闭环、Compose 验收。
