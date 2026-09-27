#!/usr/bin/env python3
"""Acquire public research sources with hashes; never execute downloaded code."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "data/external"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "NEURASIGN research dataset importer"}), timeout=60)


def download(url, destination, expected=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix+".part")
        with get(url) as src, partial.open("wb") as dst:
            while chunk := src.read(1024*1024):
                dst.write(chunk)
        partial.replace(destination)
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with destination.open("rb") as src:
        while chunk := src.read(1024*1024):
            sha.update(chunk); md5.update(chunk)
    if expected is not None and md5.hexdigest() != expected:
        raise ValueError("Published MD5 mismatch")
    return {"url": url, "path": str(destination.relative_to(ROOT)), "bytes": destination.stat().st_size,
            "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def safe_extract(archive, destination, keep):
    entries = []
    with zipfile.ZipFile(archive) as src:
        for info in src.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or info.is_dir() or not keep(member):
                continue
            path = destination.joinpath(*member.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            # ZipFile validates CRC while reading; never follow archive links.
            data = src.read(info)
            path.write_bytes(data)
            entries.append({"member": info.filename, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def cognitive():
    dest = ROOT / "cognitive_load"
    metadata = json.load(get("https://zenodo.org/api/records/20815030"))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "record.json").write_text(json.dumps(metadata, indent=2))
    item = metadata["files"][0]
    archive = dest / "source.zip"
    record = download(item["links"]["self"], archive, item["checksum"].split(":")[1])
    files = safe_extract(archive, dest / "extracted", lambda p: True)
    (dest / "manifest.json").write_text(json.dumps({"archive": record, "files": files}, indent=2))
    print(json.dumps({"dataset": "cognitive_load", "files": len(files), "bytes": record["bytes"]}), flush=True)


def clacir():
    repo = "unl-cchil/clacir_dataset"
    commit = "4641d3edf6f08c9b436f4d9f789affe75eca4a90"
    dest = ROOT / "clacir"
    archive = dest / "source.zip"
    record = download(f"https://codeload.github.com/{repo}/zip/{commit}", archive)
    files = safe_extract(archive, dest / "extracted", lambda p:
        "/dataset/" in str(p) or p.name in ("README.md", "LICENSE", "SW_LICENSE", "CITATION.cff"))
    (dest / "manifest.json").write_text(json.dumps({"commit": commit, "archive": record, "files": files}, indent=2))
    print(json.dumps({"dataset": "clacir", "files": len(files), "bytes": record["bytes"]}), flush=True)


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href")


def mobile():
    commit="868b2e964ad5788ea9e0ebd19b1879c304d05d14"
    dest=ROOT/"mobile_cogload";archive=dest/"source.zip"
    url=f"https://gitlab.fri.uni-lj.si/api/v4/projects/183/repository/archive.zip?sha={commit}"
    record=download(url,archive)
    files=safe_extract(archive,dest/"extracted",lambda p:p.name=="README.md" or p.name.endswith(("_meritve.csv","_rrInterval.csv","_vprasalnik.csv")))
    document={"source":url,"commit":commit,"sha256":record["sha256"],"files":files}
    # Preserve an existing matching manifest byte-for-byte for provenance.
    path=dest/"manifest.json"
    if not path.exists():path.write_text(json.dumps(document,indent=2))
    else:
        old=json.loads(path.read_text())
        if old['sha256']!=record['sha256']:raise ValueError('Pinned Mobile archive changed')
    print(json.dumps({'dataset':'mobile_cogload','files':len(files)}),flush=True)


def maus():
    commit="7cf608a6ceb616e1842648126b909a15b4d8f9ca";dest=ROOT/'maus_public_features'
    names=['README.md','classification.py','HRV_feature_extraction.py','src/HRV/feature_set.py',
           'feature_data/feat_pix_ppg.pkl','feature_data/label.pkl','feature_data/obj_position.pkl']
    files=[]
    for name in names:
        url=f'https://raw.githubusercontent.com/rickwu11/MAUS_dataset_baseline_system/{commit}/{name}'
        r=download(url,dest/name);files.append({'member':name,'bytes':r['bytes'],'sha256':r['sha256']})
    path=dest/'manifest.json'
    if not path.exists():path.write_text(json.dumps({'commit':commit,'files':files},indent=2))
    print(json.dumps({'dataset':'maus_public_features','files':len(files),'raw_access':'IEEE login required'}),flush=True)


def cogwear():
    base = "https://physionet.org/files/consumer-grade-wearables/1.0.0/"
    dest = ROOT / "cogwear"
    def crawl(url):
        parser = Links(); parser.feed(get(url).read().decode())
        files, folders = [], []
        for href in parser.links:
            if href.startswith(("?", "..", "/", "http", "#")):
                continue
            link = urllib.parse.urljoin(url, href)
            if not link.startswith(base):
                continue
            if href.endswith("/"):
                folders.append(link)
            elif "muse" not in href.lower() and (href.lower().endswith((".csv", ".txt")) or "LICENSE" in href):
                files.append(link)
        return files, folders
    todo, urls = [base], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        while todo:
            results = list(pool.map(crawl, todo))
            urls.extend(u for files, _ in results for u in files)
            todo = [u for _, folders in results for u in folders]
        def acquire(url):
            relative = urllib.parse.unquote(url[len(base):])
            return download(url, dest / relative)
        records = []
        for record in pool.map(acquire, sorted(urls)):
            records.append(record)
            if len(records) % 100 == 0:
                print(json.dumps({"dataset": "cogwear", "downloaded": len(records), "total": len(urls)}), flush=True)
    (dest / "manifest.json").write_text(json.dumps({"files": records, "excluded": "Muse EEG"}, indent=2))
    print(json.dumps({"dataset": "cogwear", "files": len(records), "bytes": sum(x["bytes"] for x in records)}), flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["cognitive", "clacir", "cogwear", "mobile", "maus"])
    args = parser.parse_args()
    globals()[args.dataset]()
