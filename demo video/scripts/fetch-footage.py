#!/usr/bin/env python3
"""Fetch the selected licensed source clip, with a pinned integrity check.

Raw stock media is a local production dependency, not a repository asset.
See docs/footage-sources.md for attribution, license and editorial restrictions.
"""

from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "public" / "footage" / "workspace-watch-1827.mp4"
URL = "https://assets.mixkit.co/videos/1827/1827-1080.mp4"
EXPECTED_SHA256 = "d843619d58a015228aa67095f225d5de0fbddce0e3a88963316c8ba41554159b"
MAX_BYTES = 50_000_000


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    if DESTINATION.exists():
        if digest(DESTINATION) != EXPECTED_SHA256:
            raise SystemExit(f"Existing file differs from approved source: {DESTINATION}")
        print(f"Verified existing footage: {DESTINATION.name}")
        return

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(".download")
    try:
        request = Request(URL, headers={"User-Agent": "NEURASIGN-video-production/1.0"})
        with urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise RuntimeError("Source exceeds the approved download size.")
                output.write(chunk)
        if digest(temporary) != EXPECTED_SHA256:
            raise RuntimeError("Source has changed; inspect and re-license it before use.")
        temporary.replace(DESTINATION)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Downloaded and verified: {DESTINATION.name}")


if __name__ == "__main__":
    main()
