# Incident Agent Lab

一个可运行、可回放的 AIOps 故障响应实验室。注入故障后，Agent 通过 **真正的 MCP Streamable HTTP** 调查环境、应用诊断 Skill、检索 SOP、执行安全动作，再由独立评估器确认恢复。

默认 **Reference Agent 是确定性规则基线**，无需 API Key；同时提供兼容 Chat Completions 的 LLM Adapter，以及外部 MCP Agent 接入。

## 快速启动

需要 Docker Engine / Docker Desktop 与 Docker Compose：

```bash
cp .env.example .env
docker compose up --build
```

打开 **http://localhost:5173**，点击 **注入故障**。默认告警后自动启动 Agent。控制 API / Swagger：**http://localhost:8000/docs**。

如果本机 Docker Desktop 在 `docker-credential-desktop list` 卡住，可用临时空配置构建公开镜像，不修改已有 Docker 登录信息：

```bash
mkdir -p /tmp/incidentlab-docker
DOCKER_CONFIG=/tmp/incidentlab-docker docker compose up --build
```


核心路径：

```text
Worker 连接泄漏 → Redis 连接数增长 → API 延迟和错误率上升
→ 阈值告警 → MCP 采集指标/日志/配置 → Skill 诊断 → 检索 SOP
→ restart_service(worker) → 连续健康采样 → 独立评估 → 事件回放
```

**API、Redis、Worker 是有状态的模拟逻辑服务**，不是生产容器。指标来自同一个因果状态机，动作改变该状态；这是一个实验环境，不是真实 Redis 压测或生产修复平台。重启在当前模拟中清除连接泄漏，生产中仍应修复客户端连接生命周期。

## 不使用 Docker

需要 Python 3.12+、uv、Node 22.12+：

```bash
make install
make dev
```

启动三个本地进程：控制服务 8000、Agent 8001、Vite 5173。Ctrl-C 统一停止。SQLite 默认在 `data/lab.sqlite`；Docker 使用 `lab-data` 卷保存历史。`make dev` 可读取根目录 `.env`。

## 控制台

- 概览：累计实验、恢复率、诊断准确率、安全通过率、平均恢复时间和工具/动作数。
- 环境：API / Worker → Redis 拓扑、资源压力、重启次数、故障前后指标。
- 事件：生命周期、完整 MCP 调用/结果、诊断证据、SOP、动作审核、独立评估。
- 回放：拖动事件游标，同步环境状态、指标、诊断和轨迹，不提前显示未来结果。
- 基准：当前种子连续 3 次试验；CLI/API 支持 seed × trial × Agent 配置。

## 真实 LLM

在 `.env` 设置：

```dotenv
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your-model-id
```

重启 Agent 容器/本地服务，在前端选择 **LLM**。要求提供商支持 Chat Completions 的 function tools。密钥仅传给 Agent，控制服务、事件和前端不接收密钥。不会在缺少密钥时偷偷回退到 Reference；事件会明确失败。此适配器的工具路径与 Reference 完全相同，使用 MCP discovery。模型最多 24 次迭代、75 次工具调用、2 次动作，115 秒超时；服务端另有 80 次调用、2 次动作、120 秒上限。

## 外部 Agent 接入

1. `POST /api/incidents`，请求 `{"auto_agent": false}`。
2. 轮询事件直到 `status=detected`。
3. `POST /api/incidents/{id}/agent`，请求 `{"mode":"external"}`。
4. 该响应返回一次性运行连接信息：`token`、`mcp_path`、`timeout_seconds`。
5. 使用 `http://localhost:8000/mcp` 和 `Authorization: Bearer <token>` 创建标准 MCP 客户端。

工具：`get_incident`、`get_alerts`、`get_metrics`、`get_logs`、`get_service_status`、`get_dependencies`、`get_config`、`get_sop`、`restart_service`、`stop_service`、`clear_cache`、`report_progress`、`resolve_incident`、`fail_incident`。

`get_metrics` 包含时钟、近期指标、服务状态和连续健康 tick 数。使用 `report_progress` 发布可观察的结构化诊断产物；格式见工具描述及 `packages/contracts.py`。外部 Agent 应采用 `knowledge/skills/diagnose.md`。令牌只绑定一个活动事件，结束/取消/超时后失效，不写入轨迹。观察工具不提供场景 ID、seed、真值或评估结果。

当前 SOP 允许重启 Worker；停止共享服务、清空缓存等请求被明确拒绝并计入评估。`REQUIRE_ACTION_APPROVAL=true` 返回 `REQUIRE_APPROVAL` 并停止自动执行；v0.1 不提供审批 UI 或批准后继续执行流程。

## CLI / API

```bash
make scenario SCENARIO=redis-connection-leak
make benchmark
uv run python scripts/cli.py benchmark --seed 7 --trials 5 --mode reference
uv run python scripts/smoke.py
```

关键 API：

| API | 用途 |
| --- | --- |
| `GET /api/environment` | 当前模拟状态和服务 |
| `GET /api/scenarios` | 可注入场景的公开目录 |
| `POST /api/incidents` | 注入场景，seed / auto_agent / agent_mode |
| `GET /api/incidents[/{id}]` | 历史和详情 |
| `POST /api/incidents/{id}/agent` | 启动 Reference / LLM / 外部 Agent |
| `DELETE /api/incidents/{id}/agent` | 取消、撤销令牌、记录失败评估 |
| `GET /api/events?after=&incident_id=&run_id=` | 有序事件与分页游标 |
| `GET /api/events/stream?incident_id=` | SSE，支持 Last-Event-ID 重连 |
| `GET /api/incidents/{id}/evaluation` | 独立评估结果，仅控制平面 |
| `GET /api/runs` | 持久化运行记录 |
| `POST /api/benchmarks` | seeds × trials，串行独占模拟环境 |
| `GET /api/benchmarks` | 基准进度和汇总 |

## 验证

```bash
make test                 # 单元、隔离进程 HTTP/MCP 集成、闭环、基准
make lint                 # Ruff、mypy、ESLint、TypeScript、生产构建
cd apps/frontend
npx playwright install chromium
npm run test:e2e           # 自动启动本地服务，真实浏览器注入/回放/取消
```

浏览器测试截图保存在 `artifacts/`；失败保留 Playwright trace。CI 同样执行 Python、前端、浏览器和 Compose smoke 检查。实际执行结果与限制记录在 [docs/verification.md](docs/verification.md)。

## 边界与扩展

- 单一活动模拟环境、单个控制 API worker；基准串行运行，避免引入分布式锁和队列。
- 默认每秒推进一 tick，seed 保证相同 tick 序列的故障演化可复现；模型/网络耗时可能改变动作发生时刻。
- SQLite 持久化事件、事件摘要、运行、评估、基准；控制进程重启时，未完成运行标记失败并保留历史，不自动恢复正在执行的 Agent。
- 前端控制 API 是本机实验接口，无生产鉴权；Compose 公开端口仅绑定 localhost。Agent 容器不含模拟器、场景文件、评估器或数据库，也不挂载 Docker socket。
- 工具输出为结构化证据、假设、决策和验证，不记录模型私有思维链。

参见 [ARCHITECTURE.md](ARCHITECTURE.md)、[PROJECT_SPEC.md](PROJECT_SPEC.md) 和 [扩展指南](docs/architecture/extensions.md)。
