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
                "8000",
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
                "8001",
            ],
            ROOT,
        ),
        (["npm", "run", "dev", "--", "--host", "127.0.0.1"], ROOT / "apps/frontend"),
    ]
    children = [
        subprocess.Popen(command, cwd=cwd, start_new_session=True) for command, cwd in commands
    ]
    print("Incident Lab → http://localhost:5173", flush=True)
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
