# 扩展指南

保持一个完整闭环，再扩展行为。任何合约变化同时检查模拟器、MCP、Agent、评估器、API、前端和测试。

## 添加 Scenario

在 `simulator/scenarios/` 增加符合 `packages.contracts.Scenario` 的 JSON。现有 connection_leak 支持 intensity、seed、success 阈值变化。公开目录只投影 id/name/severity，MCP 从不返回整个定义。给新的期待添加参数化测试。新故障类型需要先扩展 Fault 的受限枚举。

## 添加 Fault Behavior

在 `simulator/world.py` 扩展受控状态与 advance 分支，保持有因果关系的指标计算和可重复随机源。不要把可执行表达式写到 JSON。实现正向退化、错误动作、正确动作恢复的测试。多个行为真正出现后再提取行为注册表。

## 添加 SOP / Skill

SOP 是 `knowledge/sop/*.json`，包括症状、调查前提、修复工具和验证阈值；`get_sop` 按症状检索。不要放场景 ID、seed、评估期待或隐藏标签。Skill 是 `knowledge/skills/*.md`，描述可复用调查方法；Agent 镜像只包含这些方法文件。Reference 是显式的规则基线，不负责解释任意自然语言 Skill；LLM 使用完整 Skill 作为系统上下文。

## 添加 MCP 观察工具

在 `lab_mcp/server.py` 注册带类型注解和文档的工具，使用 `audited` 装饰器。仅返回明确列出的观测字段，不序列化 World 的内部属性。增加真实 MCP 客户端测试，检查令牌、工具 schema、数据和真值隔离。

## 添加 MCP 动作工具

先实现世界状态转移，再添加 `Runtime.action` 的安全调度分支。所有动作必须经过 `assess` 并写入 attempt/completed 事件；同步 scenario allowlist/forbidden list，默认拒绝。扩展客户端动作预算集合和评估器，测试允许、拒绝、预算耗尽和恢复。不要添加通用 shell 或任意配置写入工具。

## 添加 Evaluator

`evaluator/grader.py` 只接收 Scenario、公开状态和事件。新增一个可解释指标，保持现有字段兼容。根因/责任服务匹配私有期待；恢复由当前指标和连续健康 tick 验证；采样验证从实际 MCP 返回记录计算，不能相信 Agent 自报计数。将未恢复、假验证、错误根因作为负例。

## 添加前端可视化

使用 `types.ts` 的 API/Event 合约。以当前选中事件的 persisted events 为输入，并用 replay cursor 截断。可视化必须同步回放时间，不读取未来 event 或将当前环境代入历史。新图表放在独立组件里。

## 添加 Agent

内置 Agent 只依赖 `apps/agent/client.py`，通过官方 MCP discovery/call_tool 访问环境。新增实现接收 ToolClient，保留超时/迭代/动作上限，输出 report_progress，验证后 resolve。外部 Agent 使用 README 的 external connection API；不得调用控制面数据接口进行诊断。使用同一 scenario × seed × trial 基准比较。

## MCP SDK

采用官方 Python SDK 的 v1 稳定系列（精确版本在 uv.lock），而非自行实现 JSON-RPC。协议资料：https://github.com/modelcontextprotocol/python-sdk/tree/v1.x 。升级主版本时需重新验证 transport 生命周期、上下文注入、结构化返回与取消。
