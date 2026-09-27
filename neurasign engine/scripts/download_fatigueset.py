#!/usr/bin/env python3
"""Acquire original FatigueSet wrist channels and reference tables, checking ZIP CRC."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://drive.usercontent.google.com/download?id=1i-LPuF6j91T77tAjmZ7TqZfYYPBlTE5_&export=download&confirm=t'
SIZE = 641686295
SOURCE = 'https://www.esense.io/datasets/fatigueset/'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected(name):
    path = Path(name)
    return (len(path.parts) == 2 or path.name.startswith(('wrist_', 'exp_')))


def main():
    destination = ROOT/'data/external/fatigueset'
    destination.mkdir(parents=True, exist_ok=True)
    helper = load_module('verified_acquisition', ROOT/'scripts/download_universe.py')
    ranges = load_module('bounded_ranges', ROOT.parent/'neurasign_server_dashboard/scripts/download_universe.py')
    with zipfile.ZipFile(ranges.RemoteZipReader(URL, SIZE, 8*1024**2)) as archive:
        members = [{'member': i.filename, 'bytes': i.file_size, 'compressed_bytes': i.compress_size,
                    'header_offset': i.header_offset, 'crc32': f'{i.CRC:08x}'}
                   for i in archive.infolist() if not i.is_dir() and selected(i.filename)]
    helper.save_json(destination/'selection.json', {'source': SOURCE, 'url': URL, 'archive_bytes': SIZE,
                      'method': 'HTTP ranges; exact size and ZIP CRC per member, archive digest not checked',
                      'members': members})

    def acquire(member):
        path = helper.target_path(destination/'extracted', member['member'])
        record = helper.local_record(path, member)
        if record:
            return record
        start = member['header_offset']
        end = min(SIZE-1, start+30+len(member['member'].encode())+65535+member['compressed_bytes']-1)
        for attempt in range(4):
            try:
                response = helper.session().get(URL, headers={'Range': f'bytes={start}-{end}'}, timeout=(15, 60))
                response.raise_for_status()
                if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{SIZE}':
                    raise ValueError('Unexpected byte range')
                data = helper.extract_member(response.content, start, member)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix+'.part')
                temporary.write_bytes(data)
                temporary.replace(path)
                return {**member, 'sha256': hashlib.sha256(data).hexdigest()}
            except Exception as error:
                print(json.dumps({'download_error': type(error).__name__, 'detail': str(error), 'member': member['member'], 'attempt': attempt}), flush=True)
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
    records = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(acquire, m) for m in members]):
            records.append(future.result())
            if len(records) % 40 == 0:
                print(json.dumps({'completed': len(records), 'total': len(members)}), flush=True)
    helper.save_json(destination/'manifest.json', {'source': SOURCE, 'files': sorted(records, key=lambda r:r['member']),
                     'files_verified': len(records), 'extracted_bytes': sum(r['bytes'] for r in records)})
    print(json.dumps({'status': 'verified', 'files': len(records)}), flush=True)


if __name__ == '__main__':
    main()
