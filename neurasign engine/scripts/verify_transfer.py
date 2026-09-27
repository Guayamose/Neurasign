#!/usr/bin/env python3
"""Independently recalculate saved scores; never refit or select on test data."""
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib,json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_one(path):
    r=json.loads(path.read_text());csv=path.with_name(path.name.replace('.metrics.json','.csv.gz'))
    assert sha(csv)==r['predictions_sha256'];d=pd.read_csv(csv)
    assert not d.duplicated(['participant','unit_id','source_end']).any()
    assert (d.groupby('participant').fold.nunique()==1).all()
    split=json.loads((ROOT/'experiments/split-v1.json').read_text());mobile=json.loads((ROOT/'experiments/008-mobile-split.json').read_text())
    allowed=set(split['development'])|{'mobile:'+p for p in mobile['development']}
    assert set(d.participant)<=allowed
    count=0
    for dataset,g in d.groupby('dataset'):
        saved=r['by_dataset'][dataset];target=r['target']
        unit_counts=g.groupby('participant').unit_id.transform('nunique').to_numpy()
        window_counts=g.groupby('unit_id').unit_id.transform('size').to_numpy()
        w=1/(unit_counts*window_counts)
        if 'coarse' in path.parts:
            truth=g.truth.to_numpy(int);pred=g.prediction.to_numpy(int)
            actual_accuracy=float(np.average(truth==pred,weights=w))
            recalls=[float(np.average(pred[truth==c]==c,weights=w[truth==c])) for c in np.unique(truth)]
            np.testing.assert_allclose(actual_accuracy,saved['accuracy'],atol=1e-10)
            np.testing.assert_allclose(np.mean(recalls),saved['balanced_accuracy'],atol=1e-10);count+=2
        else:
            err=abs(g[target]-g.prediction)
            mae=g.assign(error=err).groupby(['participant','unit_id']).error.mean().groupby('participant').mean().mean()
            np.testing.assert_allclose(mae,saved['mae'],atol=1e-10)
            np.testing.assert_allclose(np.average(err<=saved['tolerance_points'],weights=w),saved['within_tolerance'],atol=1e-10);count+=2
    return count


def main():
    base=ROOT/'results/transfer-v1';paths=sorted(base.rglob('*.metrics.json'))
    total=0
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(check_one,paths)):
            total+=result
            if (i+1)%100==0:print('verified development prediction files',i+1,flush=True)
    final=base/'final/test-report.json';report=json.loads(final.read_text())
    frozen=ROOT/'experiments/008-final-selection.json'
    assert sha(frozen)==report['selection_sha256']
    manifest=ROOT/'models/transfer-v1/manifest.json';assert sha(manifest)==report['models_manifest_sha256']
    for item in json.loads(manifest.read_text())['files']:assert sha(ROOT/item['path'])==item['sha256']
    test_hash=sha(ROOT/'data/prepared/transfer-v1/mobile_test.csv.gz');assert test_hash==report['test_table_sha256']
    independent={}
    for target,r in report['targets'].items():
        p=base/'final'/(target+'-test-predictions.csv.gz');assert sha(p)==r['predictions_sha256']
        d=pd.read_csv(p);per={}
        units=d.groupby('participant').unit_id.transform('nunique');windows=d.groupby('unit_id').unit_id.transform('size');w=1/(units*windows)
        for kind in ['learned','constant']:
            error=abs(d[target]-d[kind]);g=d.assign(error=error).groupby(['participant','unit_id']).error.mean().groupby('participant').mean()
            np.testing.assert_allclose(g.mean(),r[kind]['mae'],atol=1e-10)
            np.testing.assert_allclose(np.average(error<=10,weights=w),r[kind]['within_tolerance'],atol=1e-10)
            per[kind]=g
        change=(per['constant']-per['learned']).to_numpy();rng=np.random.default_rng(20260926)
        bounds=np.quantile(rng.choice(change,(10000,len(change)),replace=True).mean(axis=1),[.025,.975])
        np.testing.assert_allclose(bounds,r['paired_comparison']['paired_person_bootstrap_95_ci'],atol=1e-10)
        assert r['passes_gate']==all(r['gate'].values())
        independent[target]={'learned_mae':float(per['learned'].mean()),'constant_mae':float(per['constant'].mean()),'paired_95_ci':bounds.tolist()}
    assert report['any_head_passes']==any(r['passes_gate'] for r in report['targets'].values())
    result={'status':'passed','development_prediction_files':len(paths),'independently_recalculated_development_metrics':total,
            'heldout_targets':len(independent),'heldout_recalculation':independent,'report_sha256':sha(final),
            'checks':['Prediction file hashes','Disjoint participant folds','Original test exclusion','Frozen selected model hashes',
                      'Independent person/task-weighted arithmetic','Paired user-level bootstrap','Registered gate consistency'],
            'no_refitting':True}
    (base/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
