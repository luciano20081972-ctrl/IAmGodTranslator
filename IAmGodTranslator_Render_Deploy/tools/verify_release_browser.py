"""Run the existing browser smoke against a temporary loopback fixture server."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn

from qa_v11_rc1_real_app_smoke import seed_database


def main() -> int:
    # The verifier supplies a private HOME and SQLite path for this check.
    home = Path(os.environ["GT_VERIFY_SCREENSHOTS"])
    if home.resolve() != Path(os.environ["HOME"]).resolve():
        raise ValueError("browser fixture requires the verifier's isolated environment")
    seed_database(home / "browser.sqlite")
    os.environ["AUTH_ENABLED"] = "false"
    from app.main import app

    config = uvicorn.Config(app, lifespan="on", log_level="warning")
    server = uvicorn.Server(config)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError("browser fixture server failed to start")
            env = dict(os.environ, GT_RC1_BASE_URL=f"http://127.0.0.1:{port}")
            command = [env["GT_VERIFY_NODE"], "tools/qa_v11_rc1_browser_smoke.js"]
            # Log the resolved loopback URL and nested command used for the evidence.
            print(f"Browser fixture URL {env['GT_RC1_BASE_URL']}. Command {command!r}", file=sys.stderr, flush=True)
            return subprocess.run(command, env=env, check=False).returncode
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
