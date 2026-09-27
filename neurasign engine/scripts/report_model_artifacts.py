#!/usr/bin/env python3
"""Publish only aggregate provenance and hashes of completed research artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = {
    'mefar-v1': 14,
    'fatigueset-physical-v1': 15,
    'fatigueset-mental-v1': 15,
    'readiness-oura-v1': 16,
    'fatigue-daily-v1': 17,
    'dailysense-classification-v1': 18,
    'dailysense-regression-v1': 18,
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    records = []
    for name, number in EXPERIMENTS.items():
        result = ROOT/'results'/name
        assert (result/'report.json').is_file(), f'Incomplete experiment: {name}'
        files = sorted((ROOT/'models'/name).glob('*.joblib'))
        assert files, f'No actual fitted artifacts: {name}'
        records.append({
            'experiment_number': number,
            'name': name,
            'artifacts': [{'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files],
            'evidence_sha256': {filename: sha(result/filename) for filename in (
                'report.json', 'run-start.json', 'frozen-selection.json', 'evaluation.json')},
            'production_enabled': False,
        })
    manifest = {
        'description': 'Fingerprints of actual locally fitted research models. No participant-level data, predictions or credentials are published.',
        'limitations': 'Artifact existence is not evidence of clinical validity, live readiness or cross-device transfer. Read each experiment report.',
        'experiment_groups': records,
    }
    path = ROOT/'experiments/fatigue-readiness-artifacts.json'
    path.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'manifest': str(path.relative_to(ROOT)), 'actual_artifacts': sum(len(r['artifacts']) for r in records)}))


if __name__ == '__main__':
    main()
