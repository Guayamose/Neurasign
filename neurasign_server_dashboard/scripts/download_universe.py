#!/usr/bin/env python3
"""Fetch a bounded Empatica subset from UNIVERSE using HTTP Range + ZIP indexing.

No API keys or Python dependencies are required. The two source archives are
about 10 GB each; this script never downloads an entire archive. ZIP member CRCs
are verified by zipfile, and local SHA-256 digests are recorded in the manifest.
The archive-level MD5 cannot be verified from a partial download.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import urllib.request
import zipfile

RECORD = "10371068"
RECORD_URL = f"https://zenodo.org/records/{RECORD}"
API_URL = f"https://zenodo.org/api/records/{RECORD}"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = ("HR.csv", "IBI.csv", "EDA.csv", "TEMP.csv", "ACC.csv", "info.txt")


def open_url(url: str, **headers):
    request = urllib.request.Request(
        url, headers={"User-Agent": "NEURASIGN-research-demo/0.1", **headers}
    )
    return urllib.request.urlopen(request, timeout=30)


def record_metadata() -> dict:
    with open_url(API_URL) as response:
        return json.loads(response.read(2_000_000))


class RemoteZipReader(io.RawIOBase):
    """Seekable, strictly bounded HTTP reader; refuses non-range responses."""

    def __init__(self, url: str, size: int, max_bytes: int):
        super().__init__()
        self.url = url
        self.size = size
        self.max_bytes = max_bytes
        self.position = 0
        self.downloaded_bytes = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET):
        if whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END):
            raise ValueError("Invalid seek mode")
        target = (0 if whence == io.SEEK_SET else self.position if whence == io.SEEK_CUR else self.size) + offset
        if target < 0:
            raise ValueError("Cannot seek before the archive")
        self.position = target
        return self.position

    def read(self, size: int = -1):
        remaining = max(0, self.size - self.position)
        size = remaining if size < 0 else min(size, remaining)
        if size == 0:
            return b""
        if self.downloaded_bytes + size > self.max_bytes:
            raise ValueError("Download byte budget exceeded; select fewer files or explicitly increase --max-download-mb")
        start, end = self.position, self.position + size - 1
        with open_url(self.url, Range=f"bytes={start}-{end}") as response:
            expected = f"bytes {start}-{end}/{self.size}"
            if response.status != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server did not honor the exact byte range; refusing to download the full archive")
            body = response.read(size + 1)
            if len(body) != size:
                raise ValueError("Truncated or oversized HTTP range response")
        self.position += size
        self.downloaded_bytes += size
        return body


def archive_for(participant: str) -> str:
    if not re.fullmatch(r"UN_1(?:0[1-9]|1[0-9]|2[0-4])", participant):
        raise ValueError(f"Participant must be UN_101 through UN_124: {participant}")
    return "UNIVERSE_UN_101_to_UN_112.zip" if int(participant[3:]) <= 112 else "UNIVERSE_UN_113_to_UN_124.zip"


def selected_member(name: str, participants: list[str], session: str, files: list[str]) -> bool:
    parts = PurePosixPath(name).parts
    for participant in participants:
        if participant not in parts:
            continue
        tail = parts[parts.index(participant) + 1:]
        if tail == (session, "Task_Labels.csv"):
            return True
        if len(tail) == 4 and tail[:3] == (session, "Raw", "Empatica") and tail[3] in files:
            return True
    return False


def safe_target(root: Path, member: str) -> Path:
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts or "\\" in member:
        raise ValueError("Unsafe archive member path")
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Archive member escapes output directory")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="List archive names/sizes without downloading archive data")
    action.add_argument("--list-members", action="store_true", help="Inspect only the selected members using the ZIP directory")
    action.add_argument("--download", action="store_true", help="Download only the selected small Empatica files")
    parser.add_argument("--participants", nargs="+", default=["UN_101", "UN_103"])
    parser.add_argument("--session", choices=["Lab1", "Lab2"], default="Lab1")
    parser.add_argument("--files", nargs="+", choices=DEFAULT_FILES, default=list(DEFAULT_FILES))
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "universe" / "raw")
    parser.add_argument("--max-download-mb", type=float, default=32, help="Total network byte budget including ZIP directories (default: 32 MiB)")
    args = parser.parse_args()
    if args.max_download_mb <= 0:
        parser.error("--max-download-mb must be positive")
    try:
        archives = {archive_for(participant) for participant in args.participants}
        metadata = record_metadata()
        available = {item["key"]: item for item in metadata["files"]}
        if args.list:
            print(f"UNIVERSE · {RECORD_URL} · license: {metadata['metadata']['license']['id']}")
            for item in available.values():
                print(f"{item['key']}  {item['size'] / 1e9:.2f} GB  {item.get('checksum', '')}")
            print("Use --list-members or --download to retrieve a bounded subset, not these complete archives.")
            return
        manifest = {
            "record": RECORD_URL,
            "doi": f"10.5281/zenodo.{RECORD}",
            "license": metadata["metadata"]["license"]["id"],
            "method": "HTTP range subset; per-member ZIP CRC checked; complete archive MD5 not checked",
            "files": [],
        }
        downloaded = 0
        max_bytes = int(args.max_download_mb * 1024 * 1024)
        for archive_name in sorted(archives):
            item = available[archive_name]
            url = item["links"].get("self") or item["links"]["download"]
            remote = RemoteZipReader(url, item["size"], max_bytes - downloaded)
            with zipfile.ZipFile(remote) as archive:
                members = [info for info in archive.infolist() if selected_member(info.filename, args.participants, args.session, args.files)]
                if not members:
                    raise ValueError(f"No matching Empatica members in {archive_name}")
                for info in members:
                    print(f"{info.filename}  {info.file_size:,} bytes ({info.compress_size:,} compressed)")
                    if not args.download:
                        continue
                    if info.file_size > 50_000_000:
                        raise ValueError("Selected member exceeds the 50 MB decompressed safety limit")
                    target = safe_target(args.output, info.filename)
                    data = archive.read(info)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(target.suffix + ".part")
                    temporary.write_bytes(data)
                    temporary.replace(target)
                    manifest["files"].append({
                        "archive": archive_name,
                        "member": info.filename,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "zip_crc32": f"{info.CRC:08x}",
                    })
            downloaded += remote.downloaded_bytes
        print(f"Downloaded {downloaded / 1024 / 1024:.2f} MiB of ZIP directory and selected content.")
        if args.download:
            args.output.mkdir(parents=True, exist_ok=True)
            manifest["downloaded_bytes"] = downloaded
            (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            print("Saved manifest.json. Run scripts/preprocess_universe.py --help to import the sessions.")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Download stopped: {error}\nThe bundled fixture remains available.\n")


if __name__ == "__main__":
    main()
