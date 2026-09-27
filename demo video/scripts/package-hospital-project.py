#!/usr/bin/env python3
"""Package the hospital film only; never collect the surrounding app/workspace.

Run after both final renders and the poster finish. Uses Python's standard
library plus ffprobe to reject incomplete/incorrect final MP4s. Originals are
read-only; transformed README/player/package.json exist only inside the ZIP.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = "neurasign-hospital-editable-project"
OUTPUT = ROOT / "exports" / f"{TOP}.zip"
DURATION = 76
FPS = 30
FRAMES = DURATION * FPS
CUE_COUNT = 11
MOVIES = {
    "exports/neurasign-hospital-76s-1080p.mp4": (1920, 1080),
    "exports/neurasign-hospital-76s-4k.mp4": (3840, 2160),
}
POSTER = "review/hospital/poster.png"
REQUIRED = [
    "src/index.ts", "src/Root.tsx", "package.json", "package-lock.json", "tsconfig.json",
    "README.md", "index.html", ".gitignore", "docs/hospital-story.md", "docs/hospital-art.md",
    "docs/hospital-audio.md", "docs/character-art.md", "docs/third-party-notices.md",
    "scripts/create-hospital-audio.py", "scripts/create-hospital-narration.py",
    "scripts/preview-server.py", "scripts/render-storyboard.mjs",
    "scripts/package-hospital-project.py", POSTER, *MOVIES,
]
SECRET_PATTERNS = [
    re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}"),
]
FORBIDDEN_JSON_KEYS = {"api_key", "apikey", "authorization", "access_token", "refresh_token", "private_key", "client_secret", "password", "credentials"}


def fail(message: str) -> None:
    raise SystemExit(f"Packaging stopped: {message}")


def require(relative: str) -> Path:
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        fail(f"missing regular file: {relative}. Finish rendering/preparing assets first.")
    if path.stat().st_size == 0:
        fail(f"empty file: {relative}")
    return path


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_movie(path: Path, dimensions: tuple[int, int]) -> None:
    if not shutil.which("ffprobe"):
        fail("ffprobe is required to verify the finished MP4s; install FFmpeg.")
    command = ["ffprobe", "-v", "error", "-show_entries",
               "format=duration:stream=codec_type,width,height,r_frame_rate,nb_frames", "-of", "json", str(path)]
    try:
        data = json.loads(subprocess.check_output(command, stderr=subprocess.PIPE, timeout=45))
        streams = data["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        duration = float(data["format"]["duration"])
        rate_top, rate_bottom = map(float, video["r_frame_rate"].split("/"))
        correct = (video["width"], video["height"]) == dimensions
        correct = correct and abs(duration - DURATION) < .15 and abs(rate_top / rate_bottom - FPS) < .01
        correct = correct and int(video.get("nb_frames", 0)) == FRAMES
        correct = correct and any(stream["codec_type"] == "audio" for stream in streams)
    except (subprocess.SubprocessError, ValueError, KeyError, StopIteration, ZeroDivisionError):
        fail(f"MP4 is incomplete or unreadable: {path.name}. Wait for the final render.")
    if not correct:
        fail(f"{path.name} must be a finished 76 s, 2,280-frame, 30 fps, {dimensions[0]}×{dimensions[1]} film with audio.")



def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        fail(f"unreadable metadata: {path.name}")
    if not isinstance(value, dict):
        fail(f"metadata must contain an object: {path.name}")
    return value


def validate_audio_master(path: Path) -> None:
    command = ["ffprobe", "-v", "error", "-show_entries",
               "format=duration:stream=codec_type,sample_rate,channels", "-of", "json", str(path)]
    try:
        data = json.loads(subprocess.check_output(command, stderr=subprocess.PIPE, timeout=45))
        audio = next(stream for stream in data["streams"] if stream["codec_type"] == "audio")
        correct = abs(float(data["format"]["duration"]) - DURATION) < .02
        correct = correct and int(audio["sample_rate"]) == 48000 and audio["channels"] == 2
    except (subprocess.SubprocessError, ValueError, KeyError, StopIteration, TypeError):
        fail(f"audio master is incomplete or unreadable: {path.name}")
    if not correct:
        fail(f"{path.name} must be a 76-second, 48 kHz stereo master.")


def current_audio_sources() -> dict[str, Path]:
    """Require all current stems and eleven verified cues; never glob old audio."""
    sources: dict[str, Path] = {}

    def add(name: str) -> Path:
        relative = f"public/audio/{name}"
        sources[relative] = require(relative)
        return sources[relative]

    narration_path = add("hospital-narration.json")
    narration = read_json(narration_path)
    cues = narration.get("cues", [])
    if narration.get("duration_seconds") != DURATION or len(cues) != CUE_COUNT:
        fail("narration manifest must describe the 76-second revision and exactly eleven cues.")
    if [cue.get("cue") for cue in cues] != list(range(1, CUE_COUNT + 1)):
        fail("narration cue IDs must be the ordered sequence 1–11.")
    previous_end = 0.0
    for cue in cues:
        try:
            start, end = float(cue["start"]), float(cue["end"])
        except (KeyError, TypeError, ValueError):
            fail("narration manifest contains an invalid caption window.")
        if not 0 <= previous_end <= start < end <= DURATION:
            fail("narration caption windows must fit the 76-second film without overlap.")
        previous_end = end

    for stem in ("mix", "narration", "score", "effects"):
        master = add(f"hospital-{stem}-76s.wav")
        validate_audio_master(master)
        # Compressed listening copies are optional; current WAV masters are not.
        compressed = ROOT / f"public/audio/hospital-{stem}-76s.m4a"
        if compressed.exists():
            add(compressed.name)
    current_narration_hash = digest_file(sources["public/audio/hospital-narration-76s.wav"])
    if narration.get("narration_sha256") != current_narration_hash:
        fail("narration manifest does not match the current 76-second narration WAV.")
    captions = add("hospital-narration.vtt").read_text()
    if not captions.startswith("WEBVTT") or captions.count("-->") != CUE_COUNT:
        fail("English VTT captions must contain exactly eleven cues.")

    for index, cue in enumerate(cues, start=1):
        stem = f"hospital-cue-{index:02}"
        source = add(f"{stem}-source.wav")
        add(f"{stem}-source.json")
        processed = add(f"{stem}.wav")
        if cue.get("audio_file") != processed.name:
            fail(f"cue {index} names an unexpected processed audio file.")
        if cue.get("source_sha256") != digest_file(source) or cue.get("audio_sha256") != digest_file(processed):
            fail(f"cue {index} audio does not match the current narration manifest.")

    validation_path = add("hospital-audio-validation.json")
    validation = read_json(validation_path)
    if (validation.get("duration_seconds") != DURATION or validation.get("cue_count") != CUE_COUNT
            or validation.get("narration_manifest_sha256") != digest_file(narration_path)):
        fail("audio validation report must match the current 76-second, eleven-cue narration manifest.")

    # An earlier listening review can remain locally without entering this archive.
    review = ROOT / "public/audio/hospital-narration-listening-review.json"
    if review.is_file() and read_json(review).get("narration_sha256") == current_narration_hash:
        add(review.name)
    return sources


def inspect_json(value: object, relative: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "_", str(key).lower())
            if normalized in FORBIDDEN_JSON_KEYS:
                fail(f"credential-like field in packaged metadata: {relative} ({key})")
            inspect_json(child, relative)
    elif isinstance(value, list):
        for child in value:
            inspect_json(child, relative)


def transform(relative: str, source: Path) -> bytes | None:
    if relative == "README.md":
        text = source.read_text()
        text = re.sub(r" The earlier 60-second MP4 exports.*?(?=\n|$)", "", text)
        text = re.sub(r"^\| `exports/neurasign-hospital-editable-project\.zip`.*\n", "", text, flags=re.MULTILINE)
        text = text.replace("The editable archive includes", "This extracted project includes")
        text = text.replace("recorded API data", "application API responses")
        return (text.rstrip() + "\n\n## Archive integrity\n\n"
                "`manifest.sha256.json` records each included file's SHA-256 and size. "
                "The original packager verifies every checksum and ZIP CRC before publishing the archive. "
                "To rebuild this ZIP after editing, finish both MP4 renders and the poster, then run "
                "`python3 scripts/package-hospital-project.py` (FFmpeg/ffprobe required).\n").encode()
    if relative == "index.html":
        text = source.read_text()
        text = re.sub(r'\s*<a\b[^>]*href=["\']exports/neurasign-hospital-editable-project\.zip["\'][^>]*>.*?</a>', "", text, flags=re.DOTALL)
        return text.encode()
    if relative == "package.json":
        data = json.loads(source.read_text())
        data.get("scripts", {}).pop("render:sample", None)
        return (json.dumps(data, indent=2) + "\n").encode()
    if relative == "docs/hospital-audio.md":
        # The archive contains the complete audio pipeline, not the parent repo's venv.
        text = source.read_text()
        text = text.replace("'neurasign engine/.venv/bin/python' 'demo video/scripts/", "python3 'scripts/")
        text = re.sub(r"The original 60-second masters remain.*?(?=\n\n)",
                      "The original 60-second revision and its backup remain in the source workspace; "
                      "this portable archive contains only the current 76-second audio and eleven source cues. "
                      "The original sign-off source is reused as current cue 11.", text, flags=re.DOTALL)
        return text.encode()
    return None


def main() -> None:
    sources = {relative: require(relative) for relative in REQUIRED}
    for relative, dimensions in MOVIES.items():
        validate_movie(sources[relative], dimensions)
    if sources[POSTER].read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        fail("the final poster is not a valid PNG")

    for pattern in ("src/hospital/*.tsx", "public/brand/*.svg"):
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            fail(f"no files match required asset group: {pattern}")
        for path in matches:
            relative = path.relative_to(ROOT).as_posix()
            sources[relative] = require(relative)
    # Explicit current-audio collection excludes older masters and stale reports.
    sources.update(current_audio_sources())

    licenses = {
        "docs/licenses/Manrope-OFL.txt": "node_modules/@fontsource/manrope/LICENSE",
        "docs/licenses/Remotion-LICENSE.md": "node_modules/remotion/LICENSE.md",
    }
    for destination, installed in licenses.items():
        sources[destination] = require(destination if (ROOT / destination).is_file() else installed)

    generated: dict[str, bytes] = {}
    manifest = {"algorithm": "SHA-256", "root": TOP, "duration_seconds": DURATION,
                "frames": FRAMES, "fps": FPS, "narration_cues": CUE_COUNT,
                "note": "This manifest excludes itself.", "files": {}}
    for relative, path in sorted(sources.items()):
        parts = Path(relative).parts
        if ".." in parts or any(part.startswith(".env") or part in {"node_modules", ".git", "capture", "footage"} for part in parts):
            fail(f"forbidden archive path: {relative}")
        content = transform(relative, path)
        if content is not None:
            generated[relative] = content
        if path.suffix.lower() in {".py", ".tsx", ".ts", ".mjs", ".json", ".md", ".html", ".svg", ".txt"}:
            text = content if content is not None else path.read_bytes()
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                fail(f"possible secret value detected in {relative}")
            if relative.startswith("public/audio/") and relative.endswith(".json"):
                inspect_json(json.loads(text), relative)
        manifest["files"][relative] = {
            "sha256": hashlib.sha256(content).hexdigest() if content is not None else digest_file(path),
            "bytes": len(content) if content is not None else path.stat().st_size,
        }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".hospital-project-", suffix=".zip.tmp", dir=OUTPUT.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for relative, path in sorted(sources.items()):
                target = f"{TOP}/{relative}"
                if relative in generated:
                    archive.writestr(target, generated[relative])
                else:
                    compression = zipfile.ZIP_STORED if path.suffix.lower() in {".mp4", ".m4a", ".png"} else zipfile.ZIP_DEFLATED
                    archive.write(path, target, compress_type=compression)
            archive.writestr(f"{TOP}/manifest.sha256.json", json.dumps(manifest, indent=2) + "\n")
        with zipfile.ZipFile(temporary_path, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                fail(f"ZIP CRC failed for {corrupt}")
            for relative, expected in manifest["files"].items():
                digest = hashlib.sha256()
                count = 0
                with archive.open(f"{TOP}/{relative}") as item:
                    for chunk in iter(lambda: item.read(1024 * 1024), b""):
                        count += len(chunk)
                        digest.update(chunk)
                if count != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                    fail(f"archive checksum mismatch: {relative}; a source may still be changing")
        temporary_path.replace(OUTPUT)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"Verified {len(sources)} files + manifest; ZIP CRC and all SHA-256 checks passed.")
    print(f"Editable project: {OUTPUT}")
    print(f"Archive SHA-256: {digest_file(OUTPUT)}")


if __name__ == "__main__":
    main()
