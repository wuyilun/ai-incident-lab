import argparse
import json
import time

import httpx

parser = argparse.ArgumentParser(description="Incident Lab control client")
parser.add_argument("command", choices=["inject", "benchmark"])
parser.add_argument("--scenario", default="redis-connection-leak")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--trials", type=int, default=3)
parser.add_argument("--mode", choices=["reference", "llm"], default="reference")
parser.add_argument("--url", default="http://localhost:8000")
args = parser.parse_args()
with httpx.Client(base_url=args.url, timeout=10) as client:
    if args.command == "inject":
        response = client.post(
            "/api/incidents",
            json={"scenario_id": args.scenario, "seed": args.seed, "agent_mode": args.mode},
        )
    else:
        response = client.post(
            "/api/benchmarks",
            json={
                "scenario_id": args.scenario,
                "seeds": [args.seed],
                "trials": args.trials,
                "agent_mode": args.mode,
            },
        )
    response.raise_for_status()
    item = response.json()
    print(json.dumps(item, indent=2))
    if args.command == "benchmark":
        while item["status"] == "running":
            time.sleep(1)
            item = next(r for r in client.get("/api/benchmarks").json() if r["id"] == item["id"])
        print(json.dumps(item, indent=2))
        if item["status"] != "completed":
            raise SystemExit(1)
