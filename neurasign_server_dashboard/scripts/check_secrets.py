"""Check source and client build outputs for exact configured credential values.

No credential values are printed, including on failures.
"""
from pathlib import Path
import sys

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    values = dotenv_values(ROOT / ".env")
    secrets = [value.encode() for name, value in values.items()
               if value and len(value) >= 12 and any(word in name.lower() for word in ("key", "token", "secret"))]
    findings = []
    checked = 0
    skip = {".venv", "node_modules", ".git", "__pycache__", "data"}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in skip for part in relative.parts) or not path.is_file() or path.name.startswith(".env"):
            continue
        if ".next" in relative.parts and "static" not in relative.parts:
            continue
        if path.stat().st_size > 20_000_000:
            continue
        blob = path.read_bytes()
        checked += 1
        if any(secret in blob for secret in secrets):
            findings.append(str(relative))
    if findings:
        print("Credential exposure found in these files (values suppressed):", *findings, sep="\n")
        return 1
    print(f"No configured credential values found in {checked} source, artifact and client-build files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
