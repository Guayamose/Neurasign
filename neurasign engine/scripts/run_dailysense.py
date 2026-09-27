#!/usr/bin/env python3
"""Prepare and evaluate daily fatigue using reserved DailySense participants."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from neurasign_engine import dailysense_data
from neurasign_engine.reference_benchmark import run, save, sha, split_people, verify

TARGETS = ('classification', 'regression')
PROFILE_NAMES = ('cardiac_day', 'autonomic_day', 'day_last_hour', 'with_history')


def prepare():
    for kind in TARGETS:
        if (ROOT/f'experiments/018-dailysense-{kind}-protocol.json').exists():
            raise ValueError('Frozen protocol already exists; use run or verify')
    frame, audit = dailysense_data.prepare(ROOT)
    folder = ROOT/'data/prepared/dailysense-v1'
    available = json.loads((folder/'profiles.json').read_text())
    profiles = {key: available[key] for key in PROFILE_NAMES}
    blocked = {'row_id', 'participant', 'unit_id', 'date', 'rating', 'target'}
    assert all(not blocked.intersection(columns) for columns in profiles.values())
    assert frame.rating.between(0, 100).all()
    split = split_people(frame.participant.unique())
    for kind in TARGETS:
        name = f'dailysense-{kind}-v1'
        path = ROOT/'data/prepared'/name/'references.csv.gz'
        path.parent.mkdir(parents=True, exist_ok=True)
        data = frame.copy()
        data['target'] = (data.rating >= 50).astype(int) if kind == 'classification' else data.rating
        data.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
        protocol = {
            'experiment': 18,
            'kind': kind,
            'target_definition': (
                'DailySense drm_vas1 observed daily fatigue VAS: high >=50 versus low <50; no middle labels removed. Research midpoint, not a clinical cutoff.'
                if kind == 'classification' else
                'DailySense drm_vas1 observed daily fatigue VAS, original 0–100 scale.'
            ),
            'source': 'https://zenodo.org/records/10816004',
            'paper': 'https://www.frontiersin.org/journals/public-health/articles/10.3389/fpubh.2023.1196539/full',
            'license': 'CC-BY-4.0',
            'split': split,
            'profiles': profiles,
            'inputs': 'Wrist HR, native IBI, BVP, EDA, temperature and acceleration summaries. No EEG or other questionnaire inputs.',
            'cutoff': 'Scheduled survey day at 21:30 Asia/Tokyo, using SignalDate rather than delayed FinishDate. Only earlier sensor samples on that day; history uses strictly preceding seven calendar days.',
            'unit': 'One original daily reference per row; no multiplication into independent minute labels.',
            'cohort': 'At least 60 usable recording minutes per day, three independently verified channels including cardiac and autonomic evidence, and five paired answers per person. Complete outer archives must match publisher MD5. Individual inner channels must pass CRC; damaged channels remain missing and are audited. No unverified signal bytes become predictors.',
            'preprocessing': 'Training-fold median imputation, missingness indicators and scaling. Person-balanced fitting; classification also balances classes.',
            'selection': 'Four person-disjoint development folds; ten algorithms per profile plus a top-three development ensemble. Minimize MAE or maximize balanced accuracy. One final evaluation of the frozen selection.',
            'weighting': 'Equal weight per person, then equal observed daily answers within person.',
            'gate': (
                'Balanced accuracy >=80% and both class recalls >=70%.' if kind == 'classification' else
                'MAE <=8/100, at least 20% improvement over the training-mean baseline, and R2 >=0.25.'
            ),
            'excluded': 'Identity, calendar fields, all questionnaire answers and target history as predictors. No task-condition substitutes for observed fatigue.',
            'prepared_sha256': sha(path),
            'audit_sha256': sha(folder/'audit.json'),
            'production_enabled': False,
            'code_dependencies': ['src/neurasign_engine/dailysense_data.py', 'scripts/run_dailysense.py'],
        }
        save(ROOT/f'experiments/018-dailysense-{kind}-protocol.json', protocol)
    print(json.dumps({'prepared_rows': len(frame), 'people': frame.participant.nunique(), 'split': split}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'run', 'verify'))
    parser.add_argument('--target', choices=TARGETS)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
        return
    kinds = (args.target,) if args.target else TARGETS
    for kind in kinds:
        name = f'dailysense-{kind}-v1'
        if args.action == 'run':
            run(ROOT, name, f'data/prepared/{name}/references.csv.gz', f'experiments/018-dailysense-{kind}-protocol.json')
        else:
            print(json.dumps(verify(ROOT, name)), flush=True)


if __name__ == '__main__':
    main()
