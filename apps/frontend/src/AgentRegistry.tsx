import { useState } from "react";
import {
  Bot,
  Check,
  Copy,
  KeyRound,
  PlugZap,
  Plus,
  RefreshCw,
} from "lucide-react";
import { agentKind, agentStatus, api } from "./types";
import type { Agent, Credentials } from "./types";

type Props = { agents: Agent[]; onRefresh: () => Promise<void> };

export default function AgentRegistry({ agents, onRefresh }: Props) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Agent["kind"]>("external");
  const [description, setDescription] = useState("");
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState("");
  const [showToken, setShowToken] = useState(false);
  const mcpUrl = `${window.location.origin}${credentials?.mcp_path ?? "/mcp"}`;
  const mcpConfig = (token: string) =>
    JSON.stringify(
      {
        mcpServers: {
          incidentlab: {
            type: "http",
            url: mcpUrl,
            headers: { Authorization: `Bearer ${token}` },
          },
        },
      },
      null,
      2,
    );
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function copy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
    } catch {
      setError("浏览器未授予剪贴板权限，请选中文本手动复制。");
    }
  }
  return (
    <div className="registry" id="agents">
      <div className="compact-heading">
        <div>
          <span className="eyebrow">CONNECT / REGISTER / RESPOND</span>
          <h1>Agent 接入中心</h1>
          <p>使用 MCP 服务地址与注册令牌，接入你自己的诊断 Agent。</p>
        </div>
        <span className="tag">{agents.length} AGENTS</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      <section className="mcp-guide panel" aria-label="MCP 接入指南">
        <div>
          <PlugZap size={18} />
          <h2>一个 MCP 连接，完成告警到恢复</h2>
          <code>{`${window.location.origin}/mcp`}</code>
        </div>
        <ol>
          <li>
            <b>01</b>
            <span>
              注册并配置 MCP<small>HTTP URL + Bearer 令牌</small>
            </span>
          </li>
          <li>
            <b>02</b>
            <span>
              检查连接、接收告警<small>check_connection → receive_alert</small>
            </span>
          </li>
          <li>
            <b>03</b>
            <span>
              采集证据、诊断修复<small>调用调查工具、Skill 与 SOP</small>
            </span>
          </li>
        </ol>
      </section>
      <div className="registry-grid">
        <section className="panel registration-form">
          <div className="panel-heading">
            <h2>
              <Plus size={17} /> 注册 Agent
            </h2>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void perform(async () => {
                const result = await api<{
                  agent: Agent;
                  credentials?: Credentials;
                }>("/agents", {
                  method: "POST",
                  body: JSON.stringify({
                    name: name.trim(),
                    kind,
                    description: description.trim(),
                  }),
                });
                setCredentials(result.credentials ?? null);
                setShowToken(false);
                setName("");
                setDescription("");
                setNotice(
                  `${result.agent.name} 已注册${result.credentials ? "，请保存下方接入凭据。" : "，可在故障实验台选择。"}`,
                );
              });
            }}
          >
            <label>
              Agent 名称
              <input
                aria-label="Agent 名称"
                required
                maxLength={80}
                placeholder="例如：Redis 值班助手"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Agent 类型
              <select
                aria-label="Agent 类型"
                value={kind}
                onChange={(e) => setKind(e.target.value as Agent["kind"])}
              >
                <option value="external">外部 Agent · MCP 直接接入</option>
                <option value="reference">Reference · 内置诊断流程</option>
                <option value="llm">LLM · 模型自主诊断</option>
              </select>
            </label>
            <p className="form-help">
              {kind === "external"
                ? "将 MCP URL 和注册令牌配置到你的 Agent。通过 check_connection 检查连接，再调用 receive_alert 接收告警。"
                : kind === "llm"
                  ? "由已配置的模型执行诊断。注册后使用连接检查确认模型配置可用。"
                  : "由系统运行 Reference Agent，无需模型密钥，适合验证接入和恢复闭环。"}
            </p>
            <label>
              接入说明
              <textarea
                aria-label="接入说明"
                maxLength={500}
                rows={3}
                placeholder="负责的环境、团队或诊断能力（可选）"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={busy || !name.trim()}
              type="submit"
            >
              <Plus size={15} />
              注册 Agent
            </button>
          </form>
        </section>
        <section className="panel agent-list">
          <div className="panel-heading">
            <h2>
              <Bot size={18} /> 已注册 Agent
            </h2>
            <span className="muted">自动更新连接状态</span>
          </div>
          {agents.length ? (
            agents.map((agent) => (
              <article
                className="agent-card"
                key={agent.id}
                data-agent-id={agent.id}
                data-testid={`agent-card-${agent.id}`}
              >
                <div className="agent-card-heading">
                  <span className="agent-avatar">
                    <Bot size={21} />
                  </span>
                  <div>
                    <h3>{agent.name}</h3>
                    <small>
                      {agentKind[agent.kind]} · <code>{agent.id}</code>
                    </small>
                  </div>
                  <span
                    className={`status ${["offline", "unavailable", "disabled"].includes(agent.connection_status) ? "warning" : ""}`}
                  >
                    {agentStatus[agent.connection_status]}
                  </span>
                </div>
                <p>
                  {agent.description ||
                    (agent.kind === "external"
                      ? "通过 MCP 接收告警、调查环境并执行修复"
                      : "系统托管的告警响应者")}
                </p>
                <div className="agent-contact">
                  最后联系：
                  {agent.last_seen
                    ? new Date(agent.last_seen).toLocaleString("zh-CN", {
                        hour12: false,
                      })
                    : "尚未联系"}
                </div>
                <div className="agent-actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void perform(async () => {
                        const result = await api<{
                          ok: boolean;
                          detail: string;
                        }>(`/agents/${agent.id}/test`, { method: "POST" });
                        setNotice(
                          `${agent.name} · ${result.ok ? "检查通过" : "检查未通过"}：${result.detail}`,
                        );
                      })
                    }
                  >
                    <PlugZap size={14} />
                    连接检查
                  </button>
                  <button
                    disabled={busy || agent.connection_status === "busy"}
                    onClick={() =>
                      void perform(async () => {
                        await api(`/agents/${agent.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({ enabled: !agent.enabled }),
                        });
                        setNotice(
                          `${agent.name} 已${agent.enabled ? "停用" : "启用"}`,
                        );
                      })
                    }
                  >
                    {agent.enabled ? "停用" : "启用"}
                  </button>
                  {agent.kind === "external" && (
                    <button
                      disabled={busy || agent.connection_status === "busy"}
                      onClick={() =>
                        void perform(async () => {
                          const result = await api<{
                            credentials: Credentials;
                          }>(`/agents/${agent.id}/rotate-token`, {
                            method: "POST",
                          });
                          setCredentials(result.credentials);
                          setShowToken(false);
                          setNotice(
                            `${agent.name} 令牌已轮换，请更新 Agent 的 MCP Bearer 令牌。`,
                          );
                        })
                      }
                    >
                      <RefreshCw size={13} />
                      轮换令牌
                    </button>
                  )}
                </div>
              </article>
            ))
          ) : (
            <div className="empty">
              <Bot size={25} />
              <p>还没有注册的 Agent。</p>
            </div>
          )}
        </section>
      </div>
      {credentials && (
        <section
          className="panel credentials"
          aria-label="接入凭据"
          data-testid="agent-credentials"
        >
          <div className="panel-heading">
            <h2>
              <KeyRound size={17} /> 接入凭据 · 仅本次显示
            </h2>
            <button
              onClick={() => {
                setCredentials(null);
                setCopied("");
              }}
            >
              已保存，关闭凭据
            </button>
          </div>
          <div className="credentials-body">
            <p>
              将以下服务地址与 Bearer 令牌配置到你的 Agent 的 HTTP MCP 连接。
              令牌仅本次显示；关闭后可通过轮换生成新令牌。
            </p>
            <label>
              注册令牌
              <div className="copy-row">
                <input
                  aria-label="注册令牌"
                  data-testid="agent-token"
                  type={showToken ? "text" : "password"}
                  readOnly
                  value={credentials.token}
                />
                <button onClick={() => setShowToken(!showToken)}>
                  {showToken ? "隐藏令牌" : "显示令牌"}
                </button>
                <button
                  aria-label="复制令牌"
                  onClick={() => void copy(credentials.token, "token")}
                >
                  {copied === "token" ? (
                    <Check size={15} />
                  ) : (
                    <Copy size={15} />
                  )}
                  复制令牌
                </button>
              </div>
            </label>
            <label>
              MCP 服务地址
              <div className="copy-row">
                <input aria-label="MCP 服务地址" readOnly value={mcpUrl} />
                <button
                  aria-label="复制 MCP 地址"
                  onClick={() => void copy(mcpUrl, "url")}
                >
                  {copied === "url" ? <Check size={15} /> : <Copy size={15} />}
                  复制地址
                </button>
              </div>
            </label>
            <div className="mcp-config">
              <div>
                <strong>HTTP MCP 配置</strong>
                <button
                  aria-label="复制 MCP 配置（含令牌）"
                  onClick={() =>
                    void copy(mcpConfig(credentials.token), "config")
                  }
                >
                  {copied === "config" ? (
                    <Check size={15} />
                  ) : (
                    <Copy size={15} />
                  )}
                  复制配置（含令牌）
                </button>
              </div>
              <pre data-testid="mcp-config">
                {mcpConfig(
                  showToken ? credentials.token : "<YOUR_AGENT_TOKEN>",
                )}
              </pre>
            </div>
            <p className="form-help">
              配置预览默认隐藏令牌，复制会包含真实令牌。不同 MCP
              客户端的配置格式可能不同，核心连接信息为 URL 和 Authorization:
              Bearer 令牌。连接后调用 check_connection，再持续调用 receive_alert
              等待告警。
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
