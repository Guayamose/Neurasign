#!/usr/bin/env python3
"""Acquire only Oura physiology/sleep/activity and readiness from the author archive."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import zipfile
from download_fatigueset import load_module

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT/'data/external/ifh_readiness'
    directory.mkdir(parents=True, exist_ok=True)
    helper = load_module('verified_acquisition', ROOT/'scripts/download_universe.py')
    ranges = load_module('bounded_ranges', ROOT.parent/'neurasign_server_dashboard/scripts/download_universe.py')
    response = helper.session().get('https://zenodo.org/api/records/10458511', timeout=30)
    response.raise_for_status()
    metadata = response.json()
    helper.save_json(directory/'zenodo-metadata.json', metadata)
    item = next(f for f in metadata['files'] if f['key'] == 'ifh_affect.zip')
    url, size = item['links']['self'], item['size']
    with zipfile.ZipFile(ranges.RemoteZipReader(url, size, 8*1024**2)) as archive:
        members = [{'member': i.filename, 'bytes': i.file_size, 'compressed_bytes': i.compress_size,
                    'header_offset': i.header_offset, 'crc32': f'{i.CRC:08x}'} for i in archive.infolist()
                   if not i.is_dir() and '/oura/' in i.filename and Path(i.filename).name in
                   ('readiness.csv', 'sleep.csv', 'activity.csv', 'heart_rate.csv')]
    helper.save_json(directory/'selection.json', {'source': 'https://zenodo.org/records/10458511',
                     'archive': item, 'license': metadata['metadata'].get('license'), 'members': members})

    def acquire(member):
        path = helper.target_path(directory/'extracted', member['member'])
        record = helper.local_record(path, member)
        if record:
            return record
        start = member['header_offset']
        end = min(size-1, start+30+len(member['member'].encode())+65535+member['compressed_bytes']-1)
        for attempt in range(4):
            try:
                response = helper.session().get(url, headers={'Range': f'bytes={start}-{end}'}, timeout=(15, 45))
                response.raise_for_status()
                if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                    raise ValueError('Unexpected byte range')
                data = helper.extract_member(response.content, start, member)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix('.part');tmp.write_bytes(data);tmp.replace(path)
                return {**member, 'sha256': hashlib.sha256(data).hexdigest()}
            except Exception as error:
                print(json.dumps({'download_error': type(error).__name__, 'detail': str(error), 'member': member['member'], 'attempt': attempt}), flush=True)
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(acquire, m) for m in members]):
            records.append(future.result())
            if len(records) % 20 == 0:
                print(json.dumps({'completed': len(records), 'total': len(members)}), flush=True)
    helper.save_json(directory/'manifest.json', {'source': 'https://zenodo.org/records/10458511',
                     'verification': 'ZIP CRC and uncompressed size; SHA256 per local member, not whole-archive digest',
                     'files': sorted(records, key=lambda r:r['member']), 'files_verified': len(records),
                     'extracted_bytes': sum(r['bytes'] for r in records)})
    print(json.dumps({'status': 'verified', 'files': len(records)}), flush=True)


if __name__ == '__main__':
    main()
