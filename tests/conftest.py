import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_lab(tmp_path_factory):
    """Actual isolated agent/control processes, actual HTTP MCP (no tool mocks)."""
    path = tmp_path_factory.mktemp("live-lab")
    control_port, agent_port = free_port(), free_port()
    control = f"http://127.0.0.1:{control_port}"
    agent = f"http://127.0.0.1:{agent_port}"
    env = dict(
        os.environ,
        LAB_DB=str(path / "lab.sqlite"),
        TICK_SECONDS="0.08",
        AGENT_POLL_SECONDS="0.08",
        AGENT_URL=agent,
        MCP_URL=control + "/mcp",
        LLM_API_KEY="",
    )
    logs = []
    processes = []
    try:
        for module, port in [
            ("apps.control_api.main:app", control_port),
            ("apps.agent.main:app", agent_port),
        ]:
            log = (path / f"{port}.log").open("w+")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        module,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                    cwd=Path(__file__).resolve().parents[1],
                )
            )
        with httpx.Client(timeout=2) as client:
            for url in [control + "/api/health", agent + "/health"]:
                for _ in range(150):
                    try:
                        if client.get(url).status_code == 200:
                            break
                    except httpx.HTTPError:
                        time.sleep(0.1)
                else:
                    for log in logs:
                        log.seek(0)
                        print(log.read())
                    raise RuntimeError("Lab failed to start")
        yield control
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
