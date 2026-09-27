#!/usr/bin/env python3
"""Download and verify wrist-only UNIVERSE members using resumable HTTP ranges.

Pickle files are downloaded as opaque bytes and never executed or deserialized.
Requires requests. Data, cached indexes and manifests stay in the ignored data/ tree.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import struct
import threading
import time
import zipfile
import zlib

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RECORD = "https://zenodo.org/api/records/10371068"
LOCAL = threading.local()


def selected(name: str) -> bool:
    path = PurePosixPath(name)
    parts = path.parts
    return (
        ("Raw" in parts and "Empatica" in parts)
        or ("Labeled" in parts and path.name.startswith("e4_"))
        or ("Preprocessed" in parts and path.name in {
            "BVP_filtered.pickle", "EDA_filtered.pickle", "TEMP_filtered.pickle"})
        or ("Features" in parts and path.name in {
            "HRV_features.pickle", "EDA_features.pickle", "TEMP_features.pickle"})
        or ("Raw" in parts and "Psychopy" in parts)
        or path.name in {"stretched_empatica.csv", "Task_Labels.csv"}
        or path.suffix.lower() == ".pdf"
    )


def target_path(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive path")
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Archive path escapes destination")
    return target


def session():
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update({
            "User-Agent": "NEURASIGN-research/0.2",
            "Accept-Encoding": "identity",
        })
    return LOCAL.session


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def local_record(path: Path, member: dict) -> dict | None:
    if not path.is_file() or path.stat().st_size != member["bytes"]:
        return None
    digest = hashlib.sha256()
    crc = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            crc = zlib.crc32(chunk, crc)
    if f"{crc:08x}" != member["crc32"]:
        return None
    return {**member, "sha256": digest.hexdigest()}


def parse_ranges(body: bytes, headers, ranges, archive_size):
    """Parse exact byte ranges, including Zenodo's LF-only multipart responses.

    Zenodo can return multipart bodies with application/octet-stream headers.
    Boundaries are read from framing; binary payloads are consumed by byte count.
    """
    expected = set(ranges)
    if len(expected) != len(ranges):
        raise ValueError("Repeated range request")
    content_range = headers.get("Content-Range")
    if content_range:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
        if not match:
            raise ValueError("Invalid Content-Range")
        start, end, total = map(int, match.groups())
        if total != archive_size or expected != {(start, end)} or len(body) != end-start+1:
            raise ValueError("Server returned a different byte range")
        return {(start, end): body}
    prefix = re.match(rb"[\r\n]*(--[^\r\n]{1,200})\r?\n", body)
    if not prefix:
        raise ValueError("Missing range framing; refusing archive response")
    boundary = prefix.group(1)
    position = prefix.end()
    result = {}
    while True:
        separator = re.search(rb"\r?\n\r?\n", body[position:position+8192])
        if not separator:
            raise ValueError("Missing multipart headers")
        header = body[position:position+separator.start()]
        match = re.search(rb"(?im)^Content-Range: bytes (\d+)-(\d+)/(\d+)\r?$", header)
        if not match:
            raise ValueError("Missing multipart Content-Range")
        start, end, total = map(int, match.groups())
        key = (start, end)
        if total != archive_size or key not in expected or key in result:
            raise ValueError("Unexpected or repeated multipart range")
        position += separator.end()
        end_position = position + end-start+1
        result[key] = body[position:end_position]
        if len(result[key]) != end-start+1:
            raise ValueError("Truncated range")
        position = end_position
        while body[position:position+1] in (b"\r", b"\n"):
            position += 1
        if not body.startswith(boundary, position):
            raise ValueError("Invalid multipart boundary")
        position += len(boundary)
        if body[position:position+2] == b"--":
            if body[position+2:].strip(b"\r\n") or set(result) != expected:
                raise ValueError("Incomplete or oversized multipart response")
            return result
        if body[position:position+2] == b"\r\n":
            position += 2
        elif body[position:position+1] == b"\n":
            position += 1
        else:
            raise ValueError("Invalid boundary separator")


def extract_member(block: bytes, range_start: int, member: dict) -> bytes:
    offset = member["header_offset"] - range_start
    header = block[offset:offset+30]
    if len(header) != 30:
        raise ValueError("Truncated local ZIP header")
    signature, version, flags, method, mtime, mdate, crc, compressed, size, names, extra = struct.unpack(
        "<4s5H3I2H", header)
    if signature != b"PK\x03\x04" or flags & 1:
        raise ValueError("Invalid or encrypted ZIP member")
    encoded_name = block[offset+30:offset+30+names]
    name = encoded_name.decode("utf-8" if flags & 0x800 else "cp437")
    if name != member["member"]:
        raise ValueError("ZIP filename differs from verified index")
    start = offset+30+names+extra
    payload = block[start:start+member["compressed_bytes"]]
    if len(payload) != member["compressed_bytes"]:
        raise ValueError("Truncated compressed member")
    if method == 0:
        data = payload
    elif method == 8:
        inflater = zlib.decompressobj(-15)
        data = inflater.decompress(payload, member["bytes"]+1)
        if not inflater.eof or inflater.unconsumed_tail or inflater.unused_data:
            raise ValueError("Invalid compressed member")
    else:
        raise ValueError(f"Unsupported ZIP compression: {method}")
    if len(data) != member["bytes"] or f"{zlib.crc32(data):08x}" != member["crc32"]:
        raise ValueError("Member size or CRC verification failed")
    return data


class Transfer:
    def __init__(self, maximum, workers):
        self.lock = threading.Lock()
        self.maximum = maximum
        self.received = 0
        self.reserved = 0
        self.next_request = 0.0
        self.requests = 0
        self.retries = 0

    def fetch(self, archive, batches):
        ranges = [(b["start"], b["end"]) for b in batches]
        limit = sum(end-start+1 for start, end in ranges) + len(ranges)*2048 + 8192
        for attempt in range(9):
            with self.lock:
                if self.received+self.reserved+limit > self.maximum:
                    raise RuntimeError("Transfer budget exceeded; resume with a larger --max-download-mb")
                self.reserved += limit
                scheduled = max(time.monotonic(), self.next_request)
                self.next_request = scheduled + 0.65
            received = 0
            delay = min(45, 2**attempt)
            try:
                time.sleep(max(0, scheduled-time.monotonic()))
                with session().get(archive["url"], headers={
                    "Range": "bytes=" + ",".join(f"{a}-{b}" for a,b in ranges)
                }, stream=True, timeout=(20, 90)) as response:
                    with self.lock:
                        self.requests += 1
                    if response.status_code in (429, 500, 502, 503, 504):
                        delay = min(60, max(delay, int(response.headers.get("Retry-After", "0"))))
                        raise requests.RequestException(f"Retryable HTTP {response.status_code}")
                    response.raise_for_status()
                    if response.status_code != 206:
                        raise ValueError("Server ignored HTTP Range; full archive download refused")
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > limit:
                        raise ValueError("Response exceeds exact range budget")
                    data = bytearray()
                    for chunk in response.iter_content(64*1024):
                        received += len(chunk)
                        if received > limit:
                            raise ValueError("Oversized HTTP range response")
                        data.extend(chunk)
                    return parse_ranges(bytes(data), response.headers, ranges, archive["size"])
            except (requests.RequestException, ValueError) as error:
                if attempt == 8:
                    raise RuntimeError(f"Range request failed after retries: {error}") from error
                with self.lock:
                    self.retries += 1
                print(f"Retry {attempt+1}: {error}; waiting {delay}s", flush=True)
            finally:
                with self.lock:
                    self.reserved -= limit
                    self.received += received
            time.sleep(delay)


def load_indexes(directory):
    response = session().get(RECORD, timeout=(20, 45))
    response.raise_for_status()
    metadata = response.json()
    archives = []
    for item in sorted(metadata["files"], key=lambda row: row["key"]):
        cache = directory / (item["key"] + ".index.json")
        index = json.loads(cache.read_text()) if cache.exists() else None
        if not index or index.get("archive_bytes") != item["size"] or index.get("checksum") != item["checksum"]:
            # Reuse the existing bounded central-directory reader; no full ZIP download.
            path = REPO / "neurasign_server_dashboard/scripts/download_universe.py"
            spec = importlib.util.spec_from_file_location("universe_index_reader", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            remote = module.RemoteZipReader(item["links"]["self"], item["size"], 16*1024*1024)
            with zipfile.ZipFile(remote) as source:
                index = {"record": "https://zenodo.org/records/10371068", "archive": item["key"],
                         "archive_bytes": item["size"], "checksum": item["checksum"], "members": [
                    {"member": f.filename, "bytes": f.file_size, "compressed_bytes": f.compress_size,
                     "header_offset": f.header_offset, "crc32": f"{f.CRC:08x}"}
                    for f in source.infolist() if not f.is_dir()]}
            save_json(cache, index)
        archives.append({"name": item["key"], "size": item["size"], "checksum": item["checksum"],
                         "url": item["links"]["self"], "members": sorted(index["members"], key=lambda f:f["header_offset"])})
    return archives


def make_batches(archive, pending):
    # Consecutive selected members share a range. Gaps containing excluded files
    # are not coalesced; multipart requests avoid one HTTP request per file.
    ranges = []
    run = None
    files = archive["members"]
    for i, row in enumerate(files):
        if row["member"] not in pending:
            run = None
            continue
        # Next non-directory local header bounds payload and any empty directory headers.
        # The final file uses a generous local-header bound; ZIP CRC validates extraction.
        end = files[i+1]["header_offset"]-1 if i+1 < len(files) else min(
            archive["size"]-1, row["header_offset"]+30+len(row["member"].encode())+65535+row["compressed_bytes"]-1)
        if run and end-run["start"] < 16*1024*1024:
            run["end"] = end
            run["members"].append(row)
        else:
            run = {"start": row["header_offset"], "end": end, "members": [row]}
            ranges.append(run)
    batches = []
    current = []
    size = 0
    for part in ranges:
        part_size = part["end"]-part["start"]+1
        if current and (len(current) >= 48 or size+part_size > 16*1024*1024):
            batches.append(current)
            current = []
            size = 0
        current.append(part)
        size += part_size
    if current:
        batches.append(current)
    return batches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"data/universe")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-download-mb", type=float, default=2300)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or args.max_download_mb <= 0:
        parser.error("Use 1–8 workers and a positive transfer budget")
    args.output.mkdir(parents=True, exist_ok=True)
    extracted = args.output / "extracted"
    started = time.monotonic()
    archives = load_indexes(args.output)
    selection = [{"archive": archive["name"], **row} for archive in archives for row in archive["members"] if selected(row["member"])]
    save_json(args.output/"acquisition-plan.json", {
        "record": RECORD, "selection": "Empatica raw, synchronized, labeled, processed, features; timing logs, labels and notes; no EEG",
        "files": selection, "compressed_bytes": sum(row["compressed_bytes"] for row in selection),
        "extracted_bytes": sum(row["bytes"] for row in selection),
        "source_archives": [{k:v for k,v in a.items() if k!="members"} for a in archives],
    })
    print(f"Selection: {len(selection):,} files, {sum(r['compressed_bytes'] for r in selection)/1e6:.1f} MB compressed, {sum(r['bytes'] for r in selection)/1e9:.2f} GB extracted", flush=True)
    verified = {}
    pending = set()
    for row in selection:
        path = target_path(extracted, row["member"])
        record = local_record(path, row)
        if record:
            verified[row["member"]] = record
        else:
            pending.add(row["member"])
    print(f"Verified existing: {len(verified):,}; remaining: {len(pending):,}", flush=True)
    transfer = Transfer(int(args.max_download_mb*1e6), args.workers)
    write_lock = threading.Lock()
    progress = {"completed":len(verified), "bytes":sum(r["bytes"] for r in verified.values()), "last":0.0}
    errors = []
    def work(archive, batch):
        blocks = transfer.fetch(archive, batch)
        for part in batch:
            block = blocks[(part["start"],part["end"])]
            for row in part["members"]:
                data = extract_member(block, part["start"], row)
                path = target_path(extracted, row["member"])
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix+".part")
                temporary.write_bytes(data)
                temporary.replace(path)
                record = {"archive":archive["name"],**row,"sha256":hashlib.sha256(data).hexdigest()}
                with write_lock:
                    verified[row["member"]] = record
                    with (args.output/"verified-files.jsonl").open("a") as log:
                        log.write(json.dumps(record)+"\n")
                    progress["completed"] += 1
                    progress["bytes"] += len(data)
                    now = time.monotonic()
                    if now-progress["last"] > 15:
                        progress["last"] = now
                        print(f"Verified {progress['completed']:,}/{len(selection):,} files | extracted {progress['bytes']/1e9:.2f} GB | received {transfer.received/1e6:.1f} MB | elapsed {(now-started)/60:.1f} min",flush=True)
    if pending and not args.verify_only:
        batches = [(archive,batch) for archive in archives for batch in make_batches(archive,pending)]
        print(f"Downloading {len(batches):,} multipart requests with {args.workers} workers; completed files survive interruptions",flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(work,archive,batch) for archive,batch in batches]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    errors.append(str(error))
                    print(f"Batch failed; completed members retained: {error}",flush=True)
    missing = [row["member"] for row in selection if row["member"] not in verified]
    summary = {
        "status":"complete" if not missing else "incomplete", "record":RECORD,
        "selected_files":len(selection),"verified_files":len(verified),
        "compressed_member_bytes":sum(r["compressed_bytes"] for r in selection),
        "verified_extracted_bytes":sum(r["bytes"] for r in verified.values()),
        "received_bytes_this_run":transfer.received,"requests_this_run":transfer.requests,
        "retries_this_run":transfer.retries,"elapsed_seconds":round(time.monotonic()-started,2),
        "participants":sorted({part for row in verified.values() for part in PurePosixPath(row["member"]).parts if re.fullmatch(r"UN_1\d\d",part)}),
        "verification":"Every member verified by uncompressed byte size and source ZIP CRC32; SHA-256 saved for local provenance. Complete ZIP MD5 not verified for subset transfer.",
        "missing":missing,"errors":errors,
    }
    save_json(args.output/"verification.json",summary)
    save_json(args.output/"manifest.json",{"summary":summary,"files":list(verified.values())})
    print(json.dumps({k:v for k,v in summary.items() if k not in {"missing","errors"}},indent=2),flush=True)
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
