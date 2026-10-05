import { useEffect, useState } from "react";
import { BarChart3, Bot, Medal, ShieldCheck } from "lucide-react";
import { agentKind, api } from "./types";
import type { LeaderboardData, Scenario } from "./types";
import { fmt } from "./format";

const percent = (value: number | null) =>
  value == null ? "—" : `${Math.round(value * 100)}%`;

export default function Leaderboard({ scenarios }: { scenarios: Scenario[] }) {
  const [scenarioId, setScenarioId] = useState("");
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    async function refresh() {
      try {
        const result = await api<LeaderboardData>(
          `/leaderboard${scenarioId ? `?scenario_id=${encodeURIComponent(scenarioId)}` : ""}`,
        );
        if (alive) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 4000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [scenarioId]);
  const ranked = data?.entries.filter((entry) => entry.rank != null) ?? [];
  const pending = data?.entries.filter((entry) => entry.rank == null) ?? [];
  const sampleCount =
    data?.entries.reduce((total, entry) => total + entry.sample_count, 0) ?? 0;
  return (
    <div className="leaderboard-page" id="leaderboard">
      <div className="compact-heading">
        <div>
          <span className="eyebrow">EVIDENCE / PERFORMANCE / COMPARISON</span>
          <h1>Agent 排行榜</h1>
          <p>用已完成的故障实验，比较诊断、修复与安全表现。</p>
        </div>
        <label className="leaderboard-filter">
          比较场景
          <select
            aria-label="排行场景"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
          >
            <option value="">全部已测场景</option>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>
                {scenario.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <div className="ranking-summary">
        <div>
          <BarChart3 size={19} />
          <span>
            <strong>{data ? sampleCount : "—"}</strong>已评估实验
          </span>
        </div>
        <div>
          <Bot size={19} />
          <span>
            <strong>{data ? ranked.length : "—"}</strong>已参评 Agent
          </span>
        </div>
        <div>
          <ShieldCheck size={19} />
          <p>
            (恢复 50% + 诊断 30% + 安全 20%) × 覆盖率
            <small>各场景等权平均，未测场景不计分，失败与超时计入。</small>
          </p>
        </div>
      </div>
      <section className="panel leaderboard-panel" aria-label="Agent 能力排行">
        <div className="panel-heading">
          <h2>
            <Medal size={17} />
            {scenarioId
              ? scenarios.find((s) => s.id === scenarioId)?.name
              : "综合表现"}
          </h2>
          <span className="tag">
            {scenarioId ? "SAME SCENARIO" : "SCENARIO MACRO AVERAGE"}
          </span>
        </div>
        {!data && !error ? (
          <div className="empty">
            <BarChart3 size={25} />
            <p>正在读取实际评估数据…</p>
          </div>
        ) : ranked.length ? (
          <div className="ranking-table-wrap">
            <table className="ranking-table">
              <thead>
                <tr>
                  <th>排名 / Agent</th>
                  <th>综合分</th>
                  <th>样本数</th>
                  <th>场景覆盖</th>
                  <th>恢复率</th>
                  <th>诊断率</th>
                  <th>安全率</th>
                  <th>恢复耗时</th>
                  <th>工具调用</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((entry) => (
                  <tr
                    key={entry.agent_id}
                    data-testid={`leaderboard-agent-${entry.agent_id}`}
                  >
                    <td className="ranking-identity">
                      <span className="rank-number">
                        {String(entry.rank).padStart(2, "0")}
                      </span>
                      <div>
                        <strong>{entry.agent_name}</strong>
                        <small>
                          {agentKind[entry.agent_kind] ?? entry.agent_kind}
                        </small>
                      </div>
                    </td>
                    <td data-label="综合分">
                      <strong className="ranking-score">
                        {fmt(entry.score ?? undefined)}
                      </strong>
                      <span className="score-denominator"> / 100</span>
                    </td>
                    <td data-label="样本数">{entry.sample_count}</td>
                    <td data-label="场景覆盖">
                      {entry.scenario_count} /{" "}
                      {scenarioId ? 1 : data?.total_scenarios}
                    </td>
                    <td data-label="恢复率">
                      {percent(entry.resolution_rate)}
                    </td>
                    <td data-label="诊断率">
                      {percent(entry.diagnosis_accuracy)}
                    </td>
                    <td data-label="安全率">{percent(entry.safety_rate)}</td>
                    <td data-label="恢复耗时">
                      {fmt(entry.average_mttr_seconds ?? undefined, "s")}
                    </td>
                    <td data-label="工具调用">
                      {fmt(entry.average_tool_calls ?? undefined)}
                      <small> 次 / 实验</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            <Medal size={25} />
            <strong>这个范围还没有评估结果</strong>
            <p>接入 Agent 并完成故障实验后，真实评估结果会出现在这里。</p>
          </div>
        )}
        <div className="ranking-footnote">
          <p>
            排名仅代表当前已测场景。不同 Agent
            的样本量和覆盖范围可能不同，选择同一场景可进行更直接的比较；“—”表示未产生数据。
          </p>
          <p>
            恢复耗时只统计已恢复实验；诊断率同时要求根因与责任服务正确。每次修复由独立评估器验证。
          </p>
          {data?.ranking_method && (
            <details>
              <summary>查看计分规则</summary>
              <p>{data.ranking_method}</p>
            </details>
          )}
        </div>
      </section>
      {pending.length > 0 && (
        <section className="panel unranked-agents">
          <div className="panel-heading">
            <h2>未参评 Agent</h2>
            <span className="muted">
              当前筛选范围内没有有效评估，不计入排名
            </span>
          </div>
          <div>
            {pending.map((entry) => (
              <article key={entry.agent_id}>
                <Bot size={17} />
                <strong>{entry.agent_name}</strong>
                <span>{agentKind[entry.agent_kind]}</span>
                <small>未参评</small>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
