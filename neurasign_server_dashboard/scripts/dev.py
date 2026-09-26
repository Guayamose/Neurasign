"""Run both services and cleanly stop children on Ctrl+C or service failure."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
children = []


def stop(*_):
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
    for child in children:
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    if not (ROOT / ".venv/bin/uvicorn").exists() or not (ROOT / "apps/web/node_modules").exists():
        print("First install dependencies: make setup", file=sys.stderr)
        sys.exit(1)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "services/api"))
    # Local development defaults always target emulators, never the current gcloud account.
    for key, value in {
        'NEURASIGN_ENV': 'local', 'WORKSPACE_STORE': 'firestore',
        'FIREBASE_PROJECT_ID': 'demo-neurasign', 'FIREBASE_WEB_API_KEY': 'demo-key',
        'FIREBASE_AUTH_DOMAIN': 'localhost', 'FIREBASE_AUTH_EMULATOR_HOST': 'localhost:9099',
        'FIREBASE_AUTH_EMULATOR_URL': 'http://localhost:9099', 'FIRESTORE_EMULATOR_HOST': 'localhost:8088',
    }.items():
        env.setdefault(key, value)
    # Do not source .env into the frontend. The API loads it privately.
    children.append(subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "neurasign.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload", "--reload-dir", "services/api"], cwd=ROOT, env=env, start_new_session=True))
    children.append(subprocess.Popen(["npm", "run", "dev", "--", "--hostname", "127.0.0.1"], cwd=ROOT / "apps/web", start_new_session=True))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    print("NEURASIGN → http://localhost:3000  |  API → http://localhost:8000/docs", flush=True)
    try:
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        sys.exit(next((child.returncode for child in children if child.returncode), 1))
    finally:
        stop()
