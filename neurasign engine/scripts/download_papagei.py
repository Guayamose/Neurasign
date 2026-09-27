#!/usr/bin/env python3
"""Fetch the published tensor checkpoint atomically and verify its checksum."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://zenodo.org/records/13983110/files/papagei_s.pt?download=1'
EXPECTED = 'a4cdb32392e2a7b25999128af92813b5'

if __name__ == '__main__':
    directory = ROOT/'data/external/papagei';directory.mkdir(parents=True, exist_ok=True)
    path = directory/'papagei_s.pt'
    if not path.exists() or hashlib.md5(path.read_bytes()).hexdigest() != EXPECTED:
        part = path.with_suffix('.part')
        with urllib.request.urlopen(URL, timeout=90) as response, part.open('wb') as output:
            while block := response.read(1024*1024):
                output.write(block)
        if hashlib.md5(part.read_bytes()).hexdigest() != EXPECTED:
            raise ValueError('Published checkpoint MD5 mismatch')
        part.replace(path)
    payload = path.read_bytes()
    meta = {'url': URL, 'bytes': len(payload), 'md5': EXPECTED, 'sha256': hashlib.sha256(payload).hexdigest()}
    (directory/'weights-manifest.json').write_text(json.dumps(meta, indent=2)+'\n')
    print(json.dumps(meta))
