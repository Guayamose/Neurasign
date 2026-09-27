#!/usr/bin/env python3
"""Publish model fingerprints for experiments 019–022, without participant data."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    (19, 'readiness-refinement-v1', '019-readiness-refinement', ['']),
    (20, 'fatigue-nested-v1', '020-fatigue-nested', ['classification', 'regression']),
    (21, 'workload-improvement-v1', '021-workload-improvement', ['']),
    (22, 'wesad-stress-022', '022-wesad-stress', ['']),
]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    records = []
    for number, name, prefix, report_subdirs in RUNS:
        result = ROOT / 'results' / name
        verification = json.loads((result / 'verification.json').read_text())
        assert verification.get('passed') is True or verification.get('status') == 'passed', name
        evidence = [result / subdir / 'report.json' for subdir in report_subdirs]
        evidence += [result / 'verification.json', ROOT / 'experiments' / f'{prefix}-protocol.json',
                     ROOT / 'experiments' / f'{prefix}-results.md']
        artifacts = sorted((ROOT / 'models' / name).rglob('*.joblib'))
        assert artifacts and all(path.is_file() for path in evidence), f'Incomplete run: {name}'
        records.append({
            'experiment': number, 'name': name, 'production_enabled': False,
            'artifacts': [{'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                           'sha256': sha(path)} for path in artifacts],
            'evidence_sha256': {str(path.relative_to(ROOT)): sha(path) for path in evidence},
        })
    document = {
        'description': 'Fingerprints of verified, locally fitted research artifacts from experiments 019–022. '
                       'No raw data, individual predictions, fitted weights or credentials are published.',
        'limitations': 'Experiments 019–021 revisit development cohorts with nested evaluation; 022 reserves '
                       'three previously unused WESAD participants. Read each report for target and evidence limits. '
                       'Model existence is not proof of live, clinical, cross-device or workplace validity.',
        'artifact_count': sum(len(record['artifacts']) for record in records),
        'experiments': records,
    }
    path = ROOT / 'experiments' / 'improvement-round-artifacts.json'
    path.write_text(json.dumps(document, indent=2) + '\n')
    print(json.dumps({'manifest': str(path.relative_to(ROOT)), 'artifacts': document['artifact_count']}))


if __name__ == '__main__':
    main()
