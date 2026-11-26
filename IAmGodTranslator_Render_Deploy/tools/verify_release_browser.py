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

    pwa = sys.argv[1:] == ["--pwa"]
    locators = sys.argv[1:] == ["--locators"]
    if pwa or locators:
        from profile_v11_6_seeded import seed_database as seed_reader
        from app import main as website

        seed_reader(website, novel_count=1, large_chapters=24)

    if locators:
        from qa_v11_rc2_postgres_auth import TEST_AUTH_SECRET, TEST_USERS

        os.environ.update(GT_TEST_AUTH_ENABLED="1", GT_TEST_AUTH_SECRET=TEST_AUTH_SECRET, APP_ENV="ci")
        for user_id, email, role in TEST_USERS.values():
            website.database.ensure_user_profile(user_id, email, role, f"{role.title()} fixture")

    if pwa:
        from fastapi.responses import Response

        @app.get("/fixture-prior-sw.js")
        def prior_worker():
            return Response("self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));",
                            media_type="application/javascript")

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
            if pwa:
                for script in ("browser_v11_6_pwa_smoke.py", "browser_v11_6_reader_cache_smoke.py"):
                    command = [sys.executable, f"tools/{script}", "--base-url", env["GT_RC1_BASE_URL"]]
                    print(f"Fixture command {command!r}", file=sys.stderr, flush=True)
                    result = subprocess.run(command, env=env, check=False)
                    if result.returncode:
                        return result.returncode
                return 0
            if locators:
                command = [sys.executable, "tools/browser_reading_locators.py", "--base-url", env["GT_RC1_BASE_URL"]]
                print(f"Fixture command {command!r}", file=sys.stderr, flush=True)
                return subprocess.run(command, env=env, check=False).returncode
            command = [env["GT_VERIFY_NODE"], "tools/qa_v11_rc1_browser_smoke.js"]
            # Log the resolved loopback URL and nested command used for the evidence.
            print(f"Browser fixture URL {env['GT_RC1_BASE_URL']}. Command {command!r}", file=sys.stderr, flush=True)
            return subprocess.run(command, env=env, check=False).returncode
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
