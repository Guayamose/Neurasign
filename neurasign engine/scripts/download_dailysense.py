#!/usr/bin/env python3
"""Resume contiguous DailySense downloads and verify publisher checksums."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import zipfile
import requests

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'https://zenodo.org/api/records/10816004'
CHUNK = 16 * 1024 * 1024
RANGE_WORKERS = 8


def digests(path):
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def get_range(url, start, end):
    """Never accept a full-body response in place of an exact byte range."""
    error = None
    for attempt in range(5):
        try:
            # The byte-specific query avoids proxy cache collisions between ranges.
            response = requests.get(
                url + ('&' if '?' in url else '?') + f'neurasign_range={start}-{end}',
                headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'},
                timeout=(15, 90),
            )
            response.raise_for_status()
            if response.status_code != 206:
                raise ValueError('Server did not honor the requested byte range')
            if not response.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
                raise ValueError('Unexpected Content-Range')
            if len(response.content) != end-start+1:
                raise ValueError('Truncated byte range')
            return response.content
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(min(30, 2 ** (attempt + 1)))
    raise RuntimeError(f'Failed to acquire range {start}-{end}') from error


def acquire(item, dest):
    if Path(item['key']).name != item['key']:
        raise ValueError('Unsafe source file name')
    path = dest/item['key']
    expected = item['checksum'].split(':', 1)[1]
    if path.exists():
        md5, sha = digests(path)
        if path.stat().st_size != item['size'] or md5 != expected:
            raise ValueError(f'Existing file failed publisher verification: {path.name}')
        return {'name': path.name, 'bytes': path.stat().st_size, 'md5': md5, 'sha256': sha}
    tmp = path.with_suffix(path.suffix+'.part')
    offset = tmp.stat().st_size if tmp.exists() else 0
    if offset > item['size']:
        raise ValueError(f'Partial file exceeds published size: {path.name}')
    ranges = [(start, min(start+CHUNK, item['size'])-1) for start in range(offset, item['size'], CHUNK)]
    print(json.dumps({'archive': path.name, 'resumed_mb': round(offset/1e6)}), flush=True)
    # Keep memory bounded and append in order, so another process may inspect
    # complete CRC-verified ZIP members in the growing contiguous prefix.
    with ThreadPoolExecutor(max_workers=RANGE_WORKERS) as pool, tmp.open('ab') as output:
        for index in range(0, len(ranges), RANGE_WORKERS):
            batch = ranges[index:index+RANGE_WORKERS]
            futures = [pool.submit(get_range, item['links']['self'], start, end) for start, end in batch]
            for (start, end), future in zip(batch, futures):
                assert output.tell() == start
                output.write(future.result())
                output.flush()
            if batch:
                print(json.dumps({'archive': path.name, 'downloaded_mb': round((batch[-1][1]+1)/1e6)}), flush=True)
    md5, sha = digests(tmp)
    if tmp.stat().st_size != item['size'] or md5 != expected:
        raise ValueError(f'Publisher checksum or size mismatch: {path.name}')
    tmp.replace(path)
    print(json.dumps({'verified': path.name, 'mb': round(path.stat().st_size/1e6)}), flush=True)
    return {'name': path.name, 'bytes': path.stat().st_size, 'md5': md5, 'sha256': sha}


def publish_indexes(dest, records):
    """Create the preparation inputs on a clean checkout, after file verification."""
    for record in records:
        if not record['name'].endswith('.zip'):
            continue
        path = dest/record['name']
        with zipfile.ZipFile(path) as archive:
            members = [
                {'member': item.filename, 'bytes': item.file_size,
                 'compressed_bytes': item.compress_size, 'crc32': f'{item.CRC:08x}',
                 'header_offset': item.header_offset}
                for item in archive.infolist() if not item.is_dir()
            ]
            index_path = dest/(path.name+'.index.json')
            if index_path.exists():
                if json.loads(index_path.read_text()) != members:
                    raise ValueError('Existing ZIP index differs from verified archive')
            else:
                index_path.write_text(json.dumps(members, indent=2)+'\n')
            for item in members:
                name = item['member']
                if not (name.endswith('/rawdata/questionnaire/project_DRM.csv') or '/user_table_term' in name):
                    continue
                target = (dest/'inspection'/name).resolve()
                if not target.is_relative_to((dest/'inspection').resolve()):
                    raise ValueError('Unsafe ZIP member path')
                payload = archive.read(name)  # ZIP verifies the questionnaire/map CRC.
                if target.exists() and target.read_bytes() != payload:
                    raise ValueError('Existing source labels differ from verified archive')
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(payload)


def main():
    dest = ROOT/'data/external/dailysense'
    dest.mkdir(parents=True, exist_ok=True)
    response = requests.get(RECORD, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    (dest/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda item: acquire(item, dest), metadata['files']))
    publish_indexes(dest, records)
    manifest = {'source': 'https://zenodo.org/records/10816004', 'license': 'CC-BY-4.0', 'files': records}
    (dest/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
