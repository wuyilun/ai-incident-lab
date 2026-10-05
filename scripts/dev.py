"""Start local services; terminate all children cleanly on Ctrl-C."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def stop_on_signal(signum, frame):
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, stop_on_signal)
    load_dotenv(ROOT / ".env")
    control_port = os.getenv("LAB_CONTROL_PORT", "8000")
    agent_port = os.getenv("LAB_AGENT_PORT", "8001")
    frontend_port = os.getenv("LAB_FRONTEND_PORT", "5173")
    child_env = dict(
        os.environ,
        AGENT_URL=f"http://127.0.0.1:{agent_port}",
        MCP_URL=f"http://127.0.0.1:{control_port}/mcp",
        LAB_CONTROL_URL=f"http://127.0.0.1:{control_port}",
    )
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.control_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                control_port,
            ],
            ROOT,
        ),
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.agent.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                agent_port,
            ],
            ROOT,
        ),
        (
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                frontend_port,
                "--strictPort",
            ],
            ROOT / "apps/frontend",
        ),
    ]
    children = [
        subprocess.Popen(command, cwd=cwd, env=child_env, start_new_session=True)
        for command, cwd in commands
    ]
    print(f"Incident Lab → http://localhost:{frontend_port}", flush=True)
    try:
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping lab services…", flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return max((p.returncode or 0 for p in children), default=0)


if __name__ == "__main__":
    raise SystemExit(main())
