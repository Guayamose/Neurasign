"""Experiment 009: frozen PaPaGei-S embeddings of completed pulse chunks."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import cheby2, filtfilt, resample_poly

from .causal_data import source_manifest, read_segment
from .transfer_training import sha, write_json

WEIGHT_MD5 = 'a4cdb32392e2a7b25999128af92813b5'
DIM = 512


def load_encoder(root):
    import torch
    from .vendor.papagei_resnet import ResNet1DMoE
    path = root/'data/external/papagei/papagei_s.pt'
    if hashlib.md5(path.read_bytes()).hexdigest() != WEIGHT_MD5:
        raise ValueError('Published checkpoint checksum mismatch')
    model = ResNet1DMoE(1, 32, 3, 2, 1, 18, 512, n_experts=3)
    state = torch.load(path, map_location='cpu', weights_only=True)
    model.load_state_dict({k.removeprefix('module.'): v for k, v in state.items()}, strict=True)
    return model.eval().requires_grad_(False)


def prepare_chunk(times, values, end):
    """Only samples strictly earlier than end can influence this completed chunk."""
    start = max(0., end-20.)
    selected = (times >= start-1e-7) & (times < end-1e-7)
    t, x = times[selected], values[selected]
    expected = int(round((end-start)*64))
    if (len(x) != expected or not np.isfinite(x).all() or
            abs(t[0]-start) > .02 or abs(t[-1]-(end-1/64)) > .02 or
            np.max(np.diff(t)) > .05 or np.std(x[-640:]) < 1e-6):
        return None
    # Reconstruct a regular native grid only within the already observed interval.
    x = np.interp(start+np.arange(expected)/64, t, x)
    b, a = cheby2(4, 20, [.5, 12], btype='bandpass', fs=64)
    filtered = filtfilt(b, a, x)[-640:]
    if np.std(filtered) < 1e-6:
        return None
    normalized = (filtered-filtered.mean())/filtered.std()
    result = resample_poly(normalized, 125, 64).astype(np.float32)
    if result.shape != (1250,) or not np.isfinite(result).all():
        raise ValueError('Invalid normalized encoder input')
    return result


def aggregate_embeddings(embeddings, end):
    """Fixed 180-second history; no future chunk, no cross-segment padding."""
    last = int(round(end/10))
    if abs(end-last*10) > 1e-6 or last < 18 or last > len(embeddings):
        return None
    past = embeddings[last-18:last]
    valid = np.isfinite(past).all(axis=1)
    if valid.sum() < 16 or not valid[-6:].all():
        return None
    recent = past[-6:].mean(axis=0)
    return np.stack([recent, np.nanmean(past, axis=0), recent-np.nanmean(past[:-6], axis=0)])


def extract(root):
    import torch
    torch.set_num_threads(4)
    destination = root/'data/prepared/papagei-v1'
    cache = destination/'chunks'
    cache.mkdir(parents=True, exist_ok=True)
    original = root/'data/prepared/causal-v3'
    portable = root/'data/prepared/transfer-v1/universe.csv.gz'
    frame = pd.read_csv(portable)
    windows = pd.read_csv(original/'windows.csv.gz')
    keys = ['participant', 'session', 'unit_id', 'source_end']
    pd.testing.assert_frame_equal(frame[keys], windows[keys])
    split = json.loads((root/'experiments/split-v1.json').read_text())
    assert set(frame.participant) <= set(split['development'])
    assert not set(frame.participant) & set(split['test'])
    provenance = json.loads((original/'provenance.json').read_text())
    provenance = {p['unit_id']: p for p in provenance}
    source, manifest = source_manifest(root)
    model = load_encoder(root)
    fingerprint = {'code': sha(Path(__file__)), 'weights': sha(root/'data/external/papagei/papagei_s.pt'),
                   'vendor': sha(Path(__file__).with_name('vendor')/'papagei_resnet.py'),
                   'input': sha(portable), 'causal': sha(original/'windows.csv.gz'),
                   'protocol': sha(root/'experiments/009-papagei-protocol.json')}
    old = destination/'fingerprint.json'
    if old.exists() and json.loads(old.read_text()) != fingerprint:
        raise ValueError('Extraction provenance changed; use a new cache directory')
    write_json(old, fingerprint)
    output = np.full((len(frame), 3, DIM), np.nan, np.float32)
    chunks_total = chunks_valid = 0
    audit = []
    started = time.monotonic()
    with torch.inference_mode():
        for ordinal, (unit, group) in enumerate(windows.groupby('unit_id', sort=True), 1):
            info = provenance[unit]
            assert info['participant'] in split['development']
            n = int(round(group.window_end.max()/10))
            path = cache/(unit+'.npy')
            if path.exists():
                embeddings = np.load(path, allow_pickle=False)
                assert embeddings.shape == (n, DIM)
            else:
                traces, checked = read_segment(source/info['segment'], source, manifest)
                assert checked['sources'] == info['sources']
                trace = traces['bvp']
                prepared = [prepare_chunk(trace.times, trace.values, (i+1)*10.) for i in range(n)]
                indices = [i for i, x in enumerate(prepared) if x is not None]
                embeddings = np.full((n, DIM), np.nan, np.float32)
                for start in range(0, len(indices), 128):
                    batch_ids = indices[start:start+128]
                    x = torch.from_numpy(np.stack([prepared[i] for i in batch_ids])).unsqueeze(1)
                    encoded = model(x)[0].numpy()
                    assert encoded.shape == (len(batch_ids), DIM) and np.isfinite(encoded).all()
                    embeddings[batch_ids] = encoded
                np.save(path, embeddings, allow_pickle=False)
            chunks_total += n
            chunks_valid += int(np.isfinite(embeddings).all(axis=1).sum())
            for index, row in group.iterrows():
                features = aggregate_embeddings(embeddings, row.window_end)
                if features is not None:
                    output[index] = features
            audit.append({'unit_id': unit, 'participant': info['participant'], 'chunks': n,
                          'valid_chunks': int(np.isfinite(embeddings).all(axis=1).sum()),
                          'cache_sha256': sha(path), 'sources': info['sources']})
            if ordinal % 10 == 0:
                print(json.dumps({'segments': ordinal, 'of': windows.unit_id.nunique(),
                                  'chunks': chunks_total, 'seconds': round(time.monotonic()-started)}), flush=True)
    valid = np.isfinite(output).all(axis=(1, 2))
    selected = frame.loc[valid].copy()
    selected['original_row'] = np.flatnonzero(valid)
    selected['dataset'] = 'universe'
    selected.to_csv(destination/'windows.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    np.save(destination/'embeddings.npy', output[valid], allow_pickle=False)
    write_json(destination/'audit.json', {'fingerprint': fingerprint, 'original_windows': len(frame),
               'accepted_windows': len(selected), 'coverage': float(valid.mean()),
               'people': int(selected.participant.nunique()), 'tasks': int(selected.unit_id.nunique()),
               'original_tasks': int(frame.unit_id.nunique()), 'chunks': chunks_total, 'valid_chunks': chunks_valid,
               'elapsed_seconds': time.monotonic()-started, 'sources': audit,
               'windows_sha256': sha(destination/'windows.csv.gz'), 'embeddings_sha256': sha(destination/'embeddings.npy'),
               'per_person': {str(p): {'original': len(g), 'eligible': int(valid[g.index].sum())}
                              for p, g in frame.groupby('participant')}})
    print(json.dumps({'accepted_windows': len(selected), 'coverage': float(valid.mean()), 'people': int(selected.participant.nunique())}), flush=True)
