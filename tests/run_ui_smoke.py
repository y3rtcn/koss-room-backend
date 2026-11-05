"""Optional real-browser test. Requires Node + a separate Playwright installation.

PLAYWRIGHT_MODULE=/absolute/path/to/playwright-core/index.mjs \
BROWSER_EXECUTABLE=/absolute/path/to/chrome python tests/run_ui_smoke.py
Creates its own temporary SQLite database and random demo password. No real DB writes.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parent.parent
work = Path(tempfile.mkdtemp(prefix="koss-room-ui-check-"))
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
password = secrets.token_urlsafe(24)
env = {**os.environ, "DB_ENGINE": "sqlite", "SQLITE_PATH": str(work / "test.sqlite3"),
       "DJANGO_DEBUG": "1", "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
       "WS_ALLOWED_ORIGINS": base, "KOSS_DEMO_PASSWORD": password,
       "UI_TEST_PASSWORD": password, "UI_TEST_BASE": base, "UI_TEST_ARTIFACTS": str(work / "screenshots")}
for command in (["migrate", "--noinput"], ["seed_demo"]):
    subprocess.run([sys.executable, "manage.py", *command], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
with (work / "server.log").open("w") as log:
    server = subprocess.Popen([sys.executable, "-m", "daphne", "-b", "127.0.0.1", "-p", str(port), "config.asgi:application"], cwd=root, env=env, stdout=log, stderr=log)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError(f"Server failed; see {work / 'server.log'}")
            try:
                with urllib.request.urlopen(base, timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Test server did not become ready")
        subprocess.run(["node", "tests/ui-smoke.mjs"], cwd=root, env=env, check=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
print(f"Isolated browser test artifacts retained in {work}")
