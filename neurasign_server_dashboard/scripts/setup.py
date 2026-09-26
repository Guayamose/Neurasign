"""Install local dependencies without touching .env."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


if __name__ == "__main__":
    if not (ROOT / ".venv/bin/python").exists():
        if shutil.which("uv"):
            run(["uv", "venv", ".venv"])
        else:
            run([sys.executable, "-m", "venv", ".venv"])
    if shutil.which("uv"):
        run(["uv", "pip", "install", "--python", ".venv/bin/python", "-r", "services/api/requirements.txt"])
    else:
        run([".venv/bin/python", "-m", "pip", "install", "-r", "services/api/requirements.txt"])
    npm = "ci" if (ROOT / "apps/web/package-lock.json").exists() else "install"
    run(["npm", npm, "--prefix", "apps/web"])
    print("Ready. Run make dev. Your existing .env has been preserved.")
