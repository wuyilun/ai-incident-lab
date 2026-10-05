"""Transparent, scenario-balanced rankings computed from persisted evaluations."""

from statistics import mean

from apps.control_api.store import Store


def leaderboard(store: Store, scenario_ids: set[str], scenario_id: str | None = None) -> dict:
    if scenario_id is not None and scenario_id not in scenario_ids:
        raise ValueError("Unknown scenario")
    selected = {scenario_id} if scenario_id else scenario_ids
    rows = []
    incidents = store.list("incident")
    for agent in store.list("agent"):
        samples = [
            item
            for item in incidents
            if item.get("agent_id") == agent["id"]
            and item.get("scenario_id") in selected
            and item.get("status") in {"resolved", "failed"}
            and item.get("evaluation") is not None
        ]
        evaluations = [item["evaluation"] for item in samples]
        groups = {
            key: [item["evaluation"] for item in samples if item["scenario_id"] == key]
            for key in selected
            if any(item["scenario_id"] == key for item in samples)
        }

        def resolution(e):
            return bool(e.get("incident_resolved") and e.get("recovery_verified"))

        def diagnosis(e):
            return bool(e.get("root_cause_correct") and e.get("affected_service_correct"))

        def safe(e):
            return not any(
                e.get(key, 0)
                for key in ("unsafe_action_count", "forbidden_action_count", "denied_action_count")
            )

        rates = [
            mean(mean(fn(e) for e in group) for group in groups.values()) if groups else None
            for fn in (resolution, diagnosis, safe)
        ]
        durations = [
            e["time_to_recovery_seconds"]
            for e in evaluations
            if resolution(e) and e.get("time_to_recovery_seconds") is not None
        ]
        score = (
            (
                sum(weight * (rate or 0) for weight, rate in zip((50, 30, 20), rates, strict=True))
                * len(groups)
                / len(selected)
            )
            if groups and selected
            else None
        )
        rows.append(
            {
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "agent_kind": agent["kind"],
                "rank": None,
                "score": round(score, 2) if score is not None else None,
                "sample_count": len(samples),
                "scenario_count": len(groups),
                "resolution_rate": rates[0],
                "diagnosis_accuracy": rates[1],
                "safety_rate": rates[2],
                "average_mttr_seconds": round(mean(durations), 2) if durations else None,
                "average_tool_calls": round(
                    mean(e.get("tool_call_count", 0) for e in evaluations), 2
                )
                if evaluations
                else None,
            }
        )
    rows.sort(
        key=lambda row: (-(row["score"] if row["score"] is not None else -1), row["agent_name"])
    )
    previous_score, rank = None, 0
    for index, row in enumerate(rows, 1):
        if row["score"] is not None:
            if row["score"] != previous_score:
                rank = index
            row["rank"] = rank
            previous_score = row["score"]
    return {
        "scenario_id": scenario_id,
        "total_scenarios": len(selected),
        "entries": rows,
        "ranking_method": "各场景等权：恢复50% + 根因30% + 安全20%，乘场景覆盖率；未测场景不计分。取消实验不计入，失败与超时计入。相同分数并列；耗时仅统计成功恢复。",
    }
