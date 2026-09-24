"""Black-box validation against an already running local or Compose lab."""

import argparse
import json
import time
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--frontend", default="http://127.0.0.1:5173")
args = parser.parse_args()
with httpx.Client(timeout=5) as client:
    for _ in range(60):
        try:
            if client.get(args.url + "/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(1)
    else:
        raise SystemExit("Control service did not become healthy")
    response = client.get(args.frontend)
    response.raise_for_status()
    assert 'id="root"' in response.text
    injected = client.post(args.url + "/api/incidents", json={"seed": 42})
    injected.raise_for_status()
    incident_id = injected.json()["id"]
    for _ in range(120):
        response = client.get(args.url + f"/api/incidents/{incident_id}")
        response.raise_for_status()
        incident = response.json()
        if incident["status"] in {"resolved", "failed", "cancelled"}:
            break
        time.sleep(1)
    assert incident["status"] == "resolved", incident
    assert incident["evaluation"]["root_cause_correct"], incident
    assert incident["evaluation"]["recovery_verified"], incident
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/smoke-result.json").write_text(json.dumps(incident, indent=2))
    print(
        json.dumps(
            {
                "incident_id": incident_id,
                "before": incident["before"]["metrics"],
                "after": incident["after"]["metrics"],
                "evaluation": incident["evaluation"],
            },
            indent=2,
        )
    )
