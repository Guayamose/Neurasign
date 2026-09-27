"""Export verified anonymous model inputs and create a local server-only access token."""
from pathlib import Path
import os
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT.parent / 'neurasign engine'


def main():
    python = Path(os.getenv('MODEL_ENGINE_PYTHON', str(ENGINE / '.venv/bin/python')))
    if not python.is_file():
        raise SystemExit('Prepare the research engine Python environment and verified artifacts first. See docs/model-engine.md.')
    bundle = ROOT / 'var/model-engine'
    if bundle.is_dir() and not any(bundle.iterdir()):
        bundle.rmdir()  # Docker may have created an empty mount directory.
    if not (bundle / 'manifest.json').is_file():
        subprocess.run([str(python), str(ENGINE / 'scripts/export_dashboard_models.py'), '--output', str(bundle)], check=True)
    else:
        print('Existing model bundle retained. The service verifies its pinned hashes before inference.')
    access = ROOT / 'var/model-engine-access.env'
    if not access.exists():
        descriptor = os.open(access, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write('MODEL_ENGINE_TOKEN=' + secrets.token_urlsafe(48) + '\n')
    else:
        os.chmod(access, 0o600)
    print('Model bundle and private local proxy configuration are ready. Existing .env files were not changed.')
    print('Start the local stack with: docker compose up --build -d')


if __name__ == '__main__':
    main()
