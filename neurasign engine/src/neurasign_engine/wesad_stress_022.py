"""Experiment 022: wrist-only recognition of WESAD protocol condition.

Scientific non-commercial research only. Not individual stress truth, diagnosis,
employee inference, or a production artifact. No chest signal is a predictor.
"""
from __future__ import annotations

import codecs
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import pickle
from pathlib import Path
import struct
import tempfile
import time
import urllib.request
import zlib

import joblib
import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfilt, welch
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

SEED = 2026022
PEOPLE = [f'S{i}' for i in range(2, 18) if i != 12]
OUT = 'results/wesad-stress-022'
RAW = 'data/external/wesad-022'
PREPARED = 'data/prepared/wesad-stress-022/windows.csv.gz'
PROTOCOL = 'experiments/022-wesad-stress-protocol.json'
URL = 'https://uni-siegen.sciebo.de/public.php/dav/files/HGdUkoNlW1Ub0Gx'
SOURCE = 'https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html'
WINDOW = 60
RATE = {'BVP': 64, 'EDA': 4, 'TEMP': 4, 'ACC': 32}
SUMMARY = ['mean', 'std', 'q10', 'median', 'q90', 'slope', 'abs_diff']
AUTONOMIC = [f'{channel}_{stat}' for channel in ['eda', 'temp', 'bvp'] for stat in SUMMARY] + [
    'eda_peak_count', 'eda_peak_prominence', 'bvp_peak_hr', 'bvp_rmssd',
    'bvp_sdnn', 'bvp_peak_fraction', 'bvp_dominant_hz', 'bvp_spectral_concentration']
MOTION = [f'acc_{axis}_{stat}' for axis in ['x', 'y', 'z', 'norm'] for stat in SUMMARY]
PROFILES = {'autonomic': AUTONOMIC, 'wrist_all': AUTONOMIC + MOTION}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def candidates():
    # 2 profiles x 16 model settings = 32 configurations, fixed before labels.
    settings = ([{'kind': 'logit', 'C': c} for c in [.01, .1, 1, 10]] +
                [{'kind': 'svm', 'C': c, 'gamma': g} for c in [.1, 1, 10] for g in ['scale', .01]] +
                [{'kind': 'extra', 'leaf': n} for n in [3, 8, 15]] +
                [{'kind': 'hist', 'leaf_nodes': n} for n in [3, 7, 15]])
    return [{'profile': profile, **setting} for profile in PROFILES for setting in settings]


def freeze(root):
    path = root / PROTOCOL
    if path.exists():
        print('Frozen protocol exists; preserving it.', flush=True); return
    order = np.random.default_rng(SEED).permutation(PEOPLE).tolist()
    test, development = sorted(order[:3]), sorted(order[3:])
    inner = [sorted(x.tolist()) for x in np.array_split(np.random.default_rng(SEED + 1).permutation(development), 4)]
    write(path, {
        'experiment': 22, 'seed': SEED, 'production_enabled': False,
        'created_before_feature_extraction_or_model_fitting': True,
        'source': SOURCE, 'download': URL, 'paper': 'https://doi.org/10.1145/3242969.3242985',
        'license': 'Scientific, non-commercial use with attribution; no commercial deployment authorization.',
        'target': 'WESAD study condition: baseline (label 1) vs TSST stress condition (label 2).',
        'not_target': 'Not self-reported stress, clinical state, fatigue, readiness, or employee condition.',
        'split': {'development': development, 'test': test}, 'inner_validation_people': inner,
        'window_seconds': WINDOW, 'stride_seconds': WINDOW, 'boundary_rule': 'Every 700 Hz label within each 60 s window must be the same and equal 1 or 2; others excluded.',
        'predictors': PROFILES, 'candidates': candidates(), 'fixed_baseline': {'profile': 'autonomic', 'kind': 'logit', 'C': 1},
        'selection': 'Mean per-person balanced accuracy over four whole-person inner folds. First candidate wins exact ties. No held-out selection.',
        'training_weights': 'Equal participant contribution and equal class contribution within participant.',
        'preprocessing': 'Within-window feature extraction; fit imputation and standardization only on fitting people. No subject calibration or future recording statistics.',
        'timing': 'Trailing 60 seconds; one prediction per completed non-overlapping minute; no instantaneous claim.',
        'uncertainty': 'Participant-cluster bootstrap percentile 95% interval, 2000 resamples, only 3 held-out people; descriptive, unstable.',
        'acceptance': 'Report every metric regardless of result; no retuning after test. Scores are not calibrated confidence.'})
    print(json.dumps({'split': {'development': development, 'test': test}, 'candidates': len(candidates())}), flush=True)


def fetch_range(start, end):
    request = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{end}'})
    for attempt in range(4):
        try:
            response = urllib.request.urlopen(request, timeout=90)
            if response.status != 206:
                response.close(); raise ValueError('Server did not honor byte range')
            with response:
                content = response.read()
                if len(content) != end - start + 1:
                    raise ValueError('Incomplete range response')
                return content
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1 + attempt)


def archive_index(root):
    raw = root / RAW; raw.mkdir(parents=True, exist_ok=True)
    # The official ZIP has a small central directory; validate and preserve it.
    request = urllib.request.Request(URL, headers={'Range': 'bytes=-65536'})
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 206:
            raise ValueError('Expected partial ZIP response')
        total = int(response.headers['Content-Range'].split('/')[-1]); tail = response.read()
    position = tail.rfind(b'PK\x05\x06')
    if position < 0:
        raise ValueError('ZIP directory missing')
    end = struct.unpack_from('<4s4H2LH', tail, position)
    size, offset = end[-3:-1]
    if offset < total - len(tail):
        raise ValueError('Unexpected directory size')
    directory = tail[offset - (total - len(tail)):offset - (total - len(tail)) + size]
    result = []; cursor = 0
    while cursor < len(directory):
        item = struct.unpack_from('<4s6H3L5H2L', directory, cursor)
        if item[0] != b'PK\x01\x02':
            raise ValueError('Invalid central directory')
        n, extra, comment = item[10:13]
        name = directory[cursor + 46:cursor + 46 + n].decode('utf8')
        result.append({'name': name, 'size': item[9], 'compressed': item[8], 'method': item[4], 'crc': item[7], 'offset': item[-1]})
        cursor += 46 + n + extra + comment
    (raw / 'central-directory.bin').write_bytes(directory)
    write(raw / 'archive-index.json', result)
    return result, total


def download(root):
    freeze(root)
    entries, total = archive_index(root)
    selected = [x for x in entries if x['name'].endswith('.pkl') or x['name'] == 'WESAD/wesad_readme.pdf']
    records = []
    for item in selected:
        if item['method'] != 8 or item['size'] > 1_500_000_000:
            raise ValueError('Unexpected ZIP entry')
        filename = Path(item['name']).name
        path = root / RAW / (filename + '.deflate')
        if not path.exists():
            offset = item['offset']; head = fetch_range(offset, offset + 29)
            header = struct.unpack('<4s5H3L2H', head)
            if header[0] != b'PK\x03\x04':
                raise ValueError('Invalid local file header')
            start = offset + 30 + header[-2] + header[-1]
            temp = path.with_suffix('.partial')
            existing = temp.stat().st_size if temp.exists() else 0
            if existing > item['compressed']:
                raise ValueError('Invalid partial download')
            chunks = [(part, min(part + 8 * 1024 * 1024, start + item['compressed']) - 1)
                      for part in range(start + existing, start + item['compressed'], 8 * 1024 * 1024)]
            with temp.open('ab') as stream, ThreadPoolExecutor(max_workers=4) as pool:
                for content in pool.map(lambda bounds: fetch_range(*bounds), chunks):
                    stream.write(content)
            temp.rename(path)
        if path.stat().st_size != item['compressed']:
            raise ValueError('Incorrect member length')
        record = {**item, 'file': str(path.relative_to(root)), 'compressed_sha256': sha(path)}
        records.append(record)
        print(json.dumps({'downloaded': filename, 'compressed_MB': round(item['compressed'] / 1e6, 2)}), flush=True)
    write(root / RAW / 'manifest.json', {'source': SOURCE, 'url': URL, 'archive_bytes': total,
          'transferred_member_bytes': sum(x['compressed'] for x in records), 'central_directory_sha256': sha(root / RAW / 'central-directory.bin'),
          'license': 'Scientific non-commercial use only with attribution.', 'members': records})


def inert_dtype(value, *args):
    dtype = np.dtype(value, *args)
    if dtype.hasobject or dtype.fields or dtype.kind not in 'biuf':
        raise pickle.UnpicklingError('Only basic numeric dtypes are accepted')
    return dtype


def inert_reconstruct(subtype, shape, dtype):
    if subtype is not np.ndarray or shape != (0,) or dtype not in (b'b', 'b'):
        raise pickle.UnpicklingError('Unexpected NumPy reconstruction')
    return np._core.multiarray._reconstruct(subtype, shape, dtype)


def inert_encode(value, encoding='latin1', errors='strict'):
    if not isinstance(value, str) or encoding not in ('latin1', 'latin-1') or errors != 'strict':
        raise pickle.UnpicklingError('Unexpected byte encoding')
    return codecs.encode(value, encoding, errors)


class NumericOnlyUnpickler(pickle.Unpickler):
    """No imported globals except fixed inert numeric-array constructors.

    Never use standard pickle.load on acquired datasets. Source is additionally
    fixed to the authors' archive and original ZIP length/CRC are checked.
    """
    def find_class(self, module, name):
        allowed = {('numpy.core.multiarray', '_reconstruct'): inert_reconstruct,
                   ('numpy._core.multiarray', '_reconstruct'): inert_reconstruct,
                   ('numpy', 'ndarray'): np.ndarray,
                   ('numpy', 'dtype'): inert_dtype,
                   ('_codecs', 'encode'): inert_encode}
        if (module, name) not in allowed:
            raise pickle.UnpicklingError(f'Forbidden global: {module}.{name}')
        return allowed[module, name]

    def persistent_load(self, pid):
        raise pickle.UnpicklingError('Persistent references are forbidden')


def load_subject(root, record):
    path = root / record['file']
    if sha(path) != record['compressed_sha256']:
        raise ValueError('Source digest mismatch')
    decoder = zlib.decompressobj(-15); crc = 0; total = 0
    with tempfile.TemporaryFile() as stream, path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            decoded = decoder.decompress(chunk); total += len(decoded)
            if total > record['size']:
                raise ValueError('Inflated source exceeds declared size')
            crc = zlib.crc32(decoded, crc); stream.write(decoded)
        if not decoder.eof or total != record['size'] or crc != record['crc']:
            raise ValueError('ZIP source integrity mismatch')
        stream.seek(0)
        data = NumericOnlyUnpickler(stream, encoding='latin1').load()
    if not isinstance(data, dict) or set(data) != {'subject', 'signal', 'label'}:
        raise ValueError('Unexpected synchronized schema')
    validate_numeric_tree(data)
    if data['subject'] not in PEOPLE or data['subject'] != Path(record['name']).stem:
        raise ValueError('Subject mismatch')
    labels = data['label']
    if type(labels) is not np.ndarray or labels.ndim != 1 or labels.dtype.hasobject or labels.dtype.kind not in 'ifu' or not np.isin(labels, np.arange(8)).all():
        raise ValueError('Invalid labels')
    wrist = data['signal']['wrist']
    if set(wrist) != set(RATE):
        raise ValueError('Unexpected wrist channels')
    for channel, rate in RATE.items():
        value = wrist[channel]
        if type(value) is not np.ndarray or value.dtype.hasobject or value.dtype.kind not in 'ifu' or value.ndim != 2:
            raise ValueError('Invalid numeric wrist array')
        if value.shape[1] != (3 if channel == 'ACC' else 1) or abs(len(value) / rate - len(labels) / 700) > 1:
            raise ValueError('Unaligned signal dimensions')
    return data['subject'], wrist, labels


def validate_numeric_tree(value, depth=0):
    if depth > 5:
        raise ValueError('Unexpected nested data')
    if type(value) is np.ndarray:
        if value.dtype.hasobject or value.dtype.fields or value.dtype.kind not in 'biuf' or value.nbytes > 1_500_000_000:
            raise ValueError('Only bounded basic numeric arrays accepted')
    elif type(value) is dict:
        if len(value) > 20 or not all(type(key) is str for key in value):
            raise ValueError('Unexpected mapping')
        for child in value.values():
            validate_numeric_tree(child, depth + 1)
    elif type(value) is not str or len(value) > 100:
        raise ValueError('Unexpected object in synchronized data')


def summary(values, rate, prefix):
    x = np.asarray(values, dtype=float)
    if len(x) < 3 or not np.isfinite(x).all():
        return {prefix + '_' + key: np.nan for key in SUMMARY}
    centered = np.arange(len(x), dtype=float) / rate
    centered -= centered.mean()
    values = [x.mean(), x.std(), *np.quantile(x, [.1, .5, .9]), np.dot(centered, x - x.mean()) / np.dot(centered, centered), np.mean(np.abs(np.diff(x)))]
    return {prefix + '_' + key: float(v) for key, v in zip(SUMMARY, values)}


def features(wrist, start, end):
    chunks = {channel: value[start * RATE[channel]:end * RATE[channel]].astype(float) for channel, value in wrist.items()}
    if end - start != WINDOW or any(len(chunks[channel]) != WINDOW * rate or not np.isfinite(chunks[channel]).all() for channel, rate in RATE.items()):
        raise ValueError('Feature window needs complete finite raw channels')
    result = {}
    for channel in ['EDA', 'TEMP', 'BVP']:
        result.update(summary(chunks[channel].ravel(), RATE[channel], {'EDA': 'eda', 'TEMP': 'temp', 'BVP': 'bvp'}[channel]))
    eda = chunks['EDA'].ravel()
    peaks, props = find_peaks(eda, distance=4, prominence=.05)
    result['eda_peak_count'] = float(len(peaks))
    result['eda_peak_prominence'] = float(np.mean(props['prominences'])) if len(peaks) else 0.
    bvp = chunks['BVP'].ravel()
    # Causal filtering uses this completed window only; no following samples.
    filtered = sosfilt(butter(3, [.6, 3.5], btype='bandpass', fs=64, output='sos'), bvp)
    peaks, _ = find_peaks(filtered[128:], distance=19, prominence=max(float(filtered.std()) * .3, 1e-8))
    intervals = np.diff(peaks) / 64
    valid_intervals = (intervals >= .33) & (intervals <= 1.5)
    clean = intervals[valid_intervals]
    clean_fraction = float(len(clean) / max(len(intervals), 1))
    valid = len(clean) >= 20 and clean_fraction >= .8
    adjacent = np.diff(intervals)[valid_intervals[:-1] & valid_intervals[1:]]
    result['bvp_peak_hr'] = float(60 / np.median(clean)) if valid else np.nan
    result['bvp_rmssd'] = float(np.sqrt(np.mean(adjacent ** 2)) * 1000) if valid and len(adjacent) >= 15 else np.nan
    result['bvp_sdnn'] = float(clean.std() * 1000) if valid else np.nan
    result['bvp_peak_fraction'] = clean_fraction
    f, p = welch(filtered[128:], fs=64, nperseg=1024)
    mask = (f >= .6) & (f <= 3.5); band = p[mask]
    energy = float(band.sum())
    valid_spectrum = np.isfinite(energy) and energy > 1e-12
    result['bvp_dominant_hz'] = float(f[mask][np.argmax(band)]) if valid_spectrum else np.nan
    result['bvp_spectral_concentration'] = float(band.max() / energy) if valid_spectrum else np.nan
    acc = chunks['ACC'] / 64.
    for i, axis in enumerate(['x', 'y', 'z']):
        result.update(summary(acc[:, i], 32, f'acc_{axis}'))
    result.update(summary(np.linalg.norm(acc, axis=1), 32, 'acc_norm'))
    return result


def prepare(root):
    protocol = json.loads((root / PROTOCOL).read_text())
    manifest = json.loads((root / RAW / 'manifest.json').read_text())
    rows = []; audits = []
    for record in manifest['members']:
        if not record['name'].endswith('.pkl'):
            continue
        subject, wrist, labels = load_subject(root, record)
        subject_rows = []; excluded = 0; incomplete = 0
        duration = int(len(labels) / 700)
        for start in range(0, duration - WINDOW + 1, WINDOW):
            end = start + WINDOW; block = labels[start * 700:end * 700]
            condition = int(block[0])
            if condition not in (1, 2) or not np.all(block == condition):
                excluded += 1; continue
            try:
                sensor_features = features(wrist, start, end)
            except ValueError:
                incomplete += 1; continue
            row = {'row_id': f'{subject}:{start}', 'participant': subject, 'start_seconds': start,
                   'end_seconds': end, 'outcome': int(condition == 2), **sensor_features}
            subject_rows.append(row)
        if not subject_rows or len(set(x['outcome'] for x in subject_rows)) != 2:
            raise ValueError('Missing either protocol condition')
        rows.extend(subject_rows)
        audits.append({'participant': subject, 'recording_seconds': duration,
                       'labeled_seconds': int(np.isin(labels, [1, 2]).sum()) / 700,
                       'windows': len(subject_rows), 'excluded_full_minutes': excluded,
                       'incomplete_or_nonfinite_wrist_minutes': incomplete,
                       'raw_wrist_channels': list(wrist)})
        print(json.dumps({'prepared': subject, 'windows': len(subject_rows)}), flush=True)
        del wrist, labels
    frame = pd.DataFrame(rows).sort_values(['participant', 'start_seconds']).reset_index(drop=True)
    assert sorted(frame.participant.unique()) == sorted(PEOPLE)
    assert not frame.row_id.duplicated().any()
    assert set(PROFILES['wrist_all']) == set(frame.columns) - {'row_id', 'participant', 'start_seconds', 'end_seconds', 'outcome'}
    path = root / PREPARED; path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    write(root / OUT / 'audit.json', {'subjects': audits, 'people': len(PEOPLE), 'windows': len(frame),
          'eligible_minutes': len(frame), 'label_source': 'Authors synchronized 700 Hz protocol labels; not questionnaire responses.',
          'feature_availability': frame[PROFILES['wrist_all']].notna().mean().to_dict(),
          'prepared_sha256': sha(path), 'protocol_sha256': sha(root / PROTOCOL), 'preparation_code_sha256': sha(Path(__file__)),
          'runner_code_sha256': sha(root / 'scripts/run_wesad_stress_022.py'),
          'source_manifest_sha256': sha(root / RAW / 'manifest.json'), 'split': protocol['split']})


def training_weights(frame):
    sizes = frame.groupby(['participant', 'outcome']).row_id.transform('size')
    weights = 1 / sizes.to_numpy(float)
    return weights / weights.mean()


def model(config):
    kind = config['kind']
    if kind == 'logit':
        estimator = LogisticRegression(C=config['C'], max_iter=4000, random_state=SEED)
    elif kind == 'svm':
        estimator = SVC(C=config['C'], gamma=config['gamma'], kernel='rbf', random_state=SEED)
    elif kind == 'extra':
        estimator = ExtraTreesClassifier(n_estimators=300, min_samples_leaf=config['leaf'], max_features=.7, random_state=SEED, n_jobs=1)
    elif kind == 'hist':
        estimator = HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=config['leaf_nodes'], min_samples_leaf=12, l2_regularization=2., learning_rate=.05, early_stopping=False, random_state=SEED)
    else:
        raise ValueError('Unknown model')
    return make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler(), estimator)


def fit(frame, config):
    columns = PROFILES[config['profile']]
    fitted = model(config)
    fitted.fit(frame[columns], frame.outcome, **{fitted.steps[-1][0] + '__sample_weight': training_weights(frame)})
    return {'model': fitted, 'columns': columns, 'config': config,
            'training_people': sorted(frame.participant.unique()), 'training_row_ids': frame.row_id.tolist(),
            'production_enabled': False, 'target': 'WESAD baseline vs experimental TSST condition',
            'license': 'Scientific non-commercial research only.', 'score_is_calibrated_confidence': False,
            'window_seconds': WINDOW, 'minimum_channels': list(RATE)}


def predict(artifact, frame):
    # Predictions use explicit sensor allowlist only; no outcome/participant/time.
    return artifact['model'].predict(frame[artifact['columns']]).astype(int)


def metrics(frame, column):
    y = frame.outcome.to_numpy(int); predicted = frame[column].to_numpy(int)
    if not np.isin(predicted, [0, 1]).all():
        raise ValueError('Non-binary predictions')
    tn = int(((y == 0) & (predicted == 0)).sum()); fp = int(((y == 0) & (predicted == 1)).sum())
    fn = int(((y == 1) & (predicted == 0)).sum()); tp = int(((y == 1) & (predicted == 1)).sum())
    recall0, recall1 = tn / (tn + fp), tp / (tp + fn)
    per_person = []
    for _, group in frame.groupby('participant'):
        if group.outcome.nunique() != 2:
            raise ValueError('Within-person metric requires both classes')
        per_person.append(float(np.mean([np.mean(group.loc[group.outcome == label, column] == label) for label in [0, 1]])))
    return {'accuracy': (tn + tp) / len(y), 'balanced_accuracy': (recall0 + recall1) / 2,
            'baseline_recall': recall0, 'stress_condition_recall': recall1,
            'mean_person_balanced_accuracy': float(np.mean(per_person)),
            'confusion_matrix': [[tn, fp], [fn, tp]], 'windows': len(y), 'people': int(frame.participant.nunique())}


def cluster_interval(frame, column):
    groups = list(frame.groupby('participant'))
    rng = np.random.default_rng(SEED + 2); values = []
    for _ in range(2000):
        sample = pd.concat([groups[i][1].assign(participant=f'resample{j}') for j, i in enumerate(rng.integers(0, len(groups), len(groups)))], ignore_index=True)
        values.append(metrics(sample, column)['mean_person_balanced_accuracy'])
    return np.quantile(values, [.025, .975]).tolist()


def run(root):
    out = root / OUT
    if (out / 'evaluation.json').exists():
        raise ValueError('Test already evaluated; use verify, never retune this holdout')
    protocol = json.loads((root / PROTOCOL).read_text()); data = pd.read_csv(root / PREPARED)
    audit = json.loads((out / 'audit.json').read_text())
    assert audit['prepared_sha256'] == sha(root / PREPARED)
    assert audit['protocol_sha256'] == sha(root / PROTOCOL)
    assert audit['preparation_code_sha256'] == sha(Path(__file__))
    assert audit['runner_code_sha256'] == sha(root / 'scripts/run_wesad_stress_022.py')
    assert audit['source_manifest_sha256'] == sha(root / RAW / 'manifest.json')
    assert not data.row_id.duplicated().any()
    training = data[data.participant.isin(protocol['split']['development'])].copy()
    assert not set(training.participant) & set(protocol['split']['test'])
    assert len(protocol['candidates']) <= 40
    preserved = {str(path.relative_to(root)): sha(path) for path in (root / 'experiments').glob('*') if path.name[:3].isdigit() and int(path.name[:3]) <= 18}
    run_start = {'protocol_sha256': sha(root / PROTOCOL), 'code_sha256': sha(Path(__file__)),
                 'source_manifest_sha256': sha(root / RAW / 'manifest.json'), 'audit_sha256': sha(out / 'audit.json'),
                 'prepared_sha256': sha(root / PREPARED), 'preserved_experiments_001_018': preserved}
    write(out / 'run-start.json', run_start)
    choices = []; all_oof = []
    with threadpool_limits(limits=1):
        for i, config in enumerate(protocol['candidates']):
            predictions = []
            for fold, validation_people in enumerate(protocol['inner_validation_people']):
                fitting = training[~training.participant.isin(validation_people)]
                validation = training[training.participant.isin(validation_people)].copy()
                assert not set(fitting.participant) & set(validation.participant)
                artifact = fit(fitting, config)
                validation['prediction'] = predict(artifact, validation); validation['fold'] = fold
                predictions.append(validation[['row_id', 'participant', 'outcome', 'prediction', 'fold']])
            oof = pd.concat(predictions, ignore_index=True)
            values = metrics(oof, 'prediction')
            choices.append({'index': i, 'config': config, 'metrics': values})
            oof['candidate'] = i; all_oof.append(oof)
            print(json.dumps({'candidate': i + 1, 'of': len(protocol['candidates']), 'mean_person_balanced_accuracy': round(values['mean_person_balanced_accuracy'], 4)}), flush=True)
    winner = max(choices, key=lambda x: x['metrics']['mean_person_balanced_accuracy'])
    selection = {'run': run_start, 'winner': winner, 'candidates': choices,
                 'selection_uses': 'Development participant-disjoint cross-validation only. Test predictions not yet computed.'}
    write(out / 'frozen-selection.json', selection)
    pd.concat(all_oof, ignore_index=True).to_csv(out / 'development-oof.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    # Only after writing the selected configuration is the held-out test predicted.
    test = data[data.participant.isin(protocol['split']['test'])].copy()
    test['majority'] = int(training.outcome.mean() > .5)
    artifacts = []
    with threadpool_limits(limits=1):
        for arm, config in [('fixed_logit', protocol['fixed_baseline']), ('selected', winner['config'])]:
            artifact = fit(training, config); test[arm] = predict(artifact, test)
            path = root / f'models/wesad-stress-022/{arm}.joblib'; path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(artifact, path)
            artifacts.append({'arm': arm, 'file': str(path.relative_to(root)), 'sha256': sha(path)})
    predictions_path = out / 'heldout-predictions.csv.gz'
    test.to_csv(predictions_path, index=False, compression={'method': 'gzip', 'mtime': 0})
    report = {'production_enabled': False, 'scope': protocol['target'], 'split': protocol['split'],
              'selection': winner, 'arms': {arm: {**metrics(test, arm), 'participant_bootstrap_95_mean_balanced': cluster_interval(test, arm)} for arm in ['majority', 'fixed_logit', 'selected']},
              'per_person': {person: metrics(group, 'selected') for person, group in test.groupby('participant')},
              'coverage': {'selected_eligible_windows': len(test), 'abstentions': 0,
                           'all_windows': len(data), 'timing_seconds': WINDOW},
              'limits': ['Three unseen participants only; windows are not independent subjects.',
                         'Protocol stress condition is not an individual self-report or validated mental-state label.',
                         'Lab tasks, speech/movement, posture and temperature drift may confound classification.',
                         'Requires E4 raw BVP/EDA/TEMP/ACC; no transfer claim to other devices.',
                         'No confidence calibration, clinical, workplace, or real-time validation.',
                         'Scientific non-commercial source license; no product integration.']}
    write(out / 'report.json', report)
    write(out / 'evaluation.json', {'artifacts': artifacts, 'predictions_sha256': sha(predictions_path),
                                   'selection_sha256': sha(out / 'frozen-selection.json'), 'report_sha256': sha(out / 'report.json')})
    render_report(root, report)
    print(json.dumps(report['arms']), flush=True)


def render_report(root, report):
    audit = json.loads((root / OUT / 'audit.json').read_text())
    lines = ['# Experiment 022: WESAD wrist protocol-condition benchmark', '',
             '**Offline scientific research only. Production disabled. This is not an employee stress detector.**', '',
             '## Data and target', '',
             'New external dataset: 15 WESAD participants, authors’ synchronized Empatica E4 BVP (64 Hz), EDA and skin temperature (4 Hz), and accelerometer (32 Hz). '
             'No chest, EEG, demographics, questionnaire answers, subject IDs, timestamps or condition codes enter the model. '
             'The label is baseline versus the experimentally induced TSST protocol condition; it is not the participant’s actual instantaneous stress.', '',
             f"There are {audit['windows']} eligible non-overlapping 60-second windows. Only windows entirely within one source condition are retained; transitions, amusement and meditation are excluded. "
             'The readme warns that raw wrist CSV times are not synchronized; this benchmark instead uses the authors’ synchronized arrays. HR/IBI vendor files are ignored as the source instructs. '
             'Pulse summaries are estimated within each completed BVP window and are not ECG-validated HRV.', '',
             '## Evaluation', '',
             f"Frozen before feature extraction: 12 development people {report['split']['development']}; 3 test people {report['split']['test']}. "
             'Four participant-disjoint inner folds select among 32 fixed configurations: logistic regression, RBF SVM, ExtraTrees and histogram gradient boosting; autonomic-only versus all wrist channels. '
             'The criterion is mean per-person balanced accuracy. Fitted preprocessing never sees validation/test people. No random window split and no test tuning.', '',
             '| Arm | Accuracy | Balanced accuracy | Baseline recall | TSST recall | Person-mean balanced |',
             '|---|---:|---:|---:|---:|---:|']
    for arm, values in report['arms'].items():
        lines.append('| ' + arm + ' | ' + ' | '.join(f'{values[k]:.2%}' for k in ['accuracy', 'balanced_accuracy', 'baseline_recall', 'stress_condition_recall', 'mean_person_balanced_accuracy']) + ' |')
    selected = report['arms']['selected']; low, high = selected['participant_bootstrap_95_mean_balanced']
    lines += ['', f"Selected configuration: `{json.dumps(report['selection']['config'])}`. Development participant-grouped mean balanced accuracy: {report['selection']['metrics']['mean_person_balanced_accuracy']:.2%}.", '',
              f"Selected model’s descriptive 95% participant-cluster bootstrap interval for person-mean balanced accuracy: {low:.2%}–{high:.2%}. "
              'Only three held-out clusters: this interval is unstable and cannot establish population reliability. It is not per-prediction confidence.', '',
              f"Coverage: {selected['windows']} / {selected['windows']} eligible held-out windows, no abstention; eligibility already excludes unlabeled/transition/non-target periods. "
              'A prediction uses a completed trailing minute and updates once per minute. No instantaneous/live validation was performed.', '',
              '## Limits', '', *['- ' + item for item in report['limits']], '',
              'Do not compare this number directly with self-report stress, fatigue, readiness or workload benchmarks: the target and difficulty are different. '
              'Condition recognition can partly exploit task/activity or temperature drift; it does not solve general employee monitoring.', '',
              '## Source, integrity and reproduction', '',
              f'[Authors’ dataset and scientific non-commercial terms]({SOURCE}); '
              '[UCI metadata](https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detetection); '
              '[Schmidt et al., ICMI 2018](https://doi.org/10.1145/3242969.3242985).', '',
              'Official ZIP members are fetched by byte range, with original ZIP CRC/size and SHA-256 recorded. '
              'A restricted NumPy-only unpickler rejects arbitrary globals and persistent references; only numeric wrist arrays and synchronized labels enter feature extraction. '
              'No downloaded executable code is run. Acquired recordings and models remain ignored by git.', '',
              'Run `scripts/run_wesad_stress_022.py freeze`, `download`, `prepare`, `run`, then `verify` with the engine Python environment. '
              'A completed held-out run refuses reruns; verification independently recomputes metrics and replays saved artifacts. '
              'Artifacts in `models/wesad-stress-022/`, evidence in `results/wesad-stress-022/`. Prior experiments 001–018 remain unchanged.']
    (root / 'experiments/022-wesad-stress-results.md').write_text('\n'.join(lines).replace(". '\n", '.\n') + '\n')


def verify(root):
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, recall_score
    out = root / OUT; protocol = json.loads((root / PROTOCOL).read_text())
    selection = json.loads((out / 'frozen-selection.json').read_text()); evaluation = json.loads((out / 'evaluation.json').read_text())
    report = json.loads((out / 'report.json').read_text()); data = pd.read_csv(root / PREPARED)
    saved = pd.read_csv(out / 'heldout-predictions.csv.gz')
    assert sha(root / PROTOCOL) == selection['run']['protocol_sha256']
    assert sha(Path(__file__)) == selection['run']['code_sha256']
    assert sha(root / PREPARED) == selection['run']['prepared_sha256']
    assert sha(root / RAW / 'manifest.json') == selection['run']['source_manifest_sha256']
    assert sha(out / 'audit.json') == selection['run']['audit_sha256']
    audit = json.loads((out / 'audit.json').read_text())
    assert sha(root / 'scripts/run_wesad_stress_022.py') == audit['runner_code_sha256']
    assert sha(out / 'frozen-selection.json') == evaluation['selection_sha256']
    assert sha(out / 'heldout-predictions.csv.gz') == evaluation['predictions_sha256']
    assert sha(out / 'report.json') == evaluation['report_sha256']
    for path, digest in selection['run']['preserved_experiments_001_018'].items():
        assert sha(root / path) == digest
    assert set(saved.participant) == set(protocol['split']['test'])
    assert not set(protocol['split']['development']) & set(protocol['split']['test'])
    assert sorted(p for fold in protocol['inner_validation_people'] for p in fold) == sorted(protocol['split']['development'])
    assert set(saved.row_id) == set(data[data.participant.isin(protocol['split']['test'])].row_id)
    assert not saved.row_id.duplicated().any()
    original_test = data[data.participant.isin(protocol['split']['test'])].sort_values('row_id').reset_index(drop=True)
    saved_test = saved.sort_values('row_id').reset_index(drop=True)
    pd.testing.assert_frame_equal(saved_test[list(data.columns)], original_test, check_exact=False, rtol=1e-12, atol=1e-12)
    assert selection['winner'] == max(selection['candidates'], key=lambda x: x['metrics']['mean_person_balanced_accuracy'])
    oof = pd.read_csv(out / 'development-oof.csv.gz')
    for choice in selection['candidates']:
        subset = oof[oof.candidate == choice['index']]
        assert not set(subset.participant) & set(protocol['split']['test'])
        assert set(subset.row_id) == set(data[data.participant.isin(protocol['split']['development'])].row_id)
        assert metrics(subset, 'prediction') == choice['metrics']
    for record in evaluation['artifacts']:
        path = root / record['file']; assert sha(path) == record['sha256']
        artifact = joblib.load(path)  # Our own locally created artifact, not external pickle.
        assert artifact['production_enabled'] is False
        assert artifact['columns'] == protocol['predictors'][artifact['config']['profile']]
        assert set(artifact['training_people']) == set(protocol['split']['development'])
        assert set(artifact['training_row_ids']) == set(data[data.participant.isin(protocol['split']['development'])].row_id)
        assert not set(artifact['training_row_ids']) & set(saved.row_id)
        tampered = saved.copy(); tampered['participant'] = 'irrelevant'; tampered['outcome'] = 1 - tampered.outcome
        tampered['start_seconds'] = -999; tampered['end_seconds'] = -999
        with threadpool_limits(limits=1):
            np.testing.assert_array_equal(predict(artifact, tampered), saved[record['arm']])
    checks = 0
    for arm in ['majority', 'fixed_logit', 'selected']:
        values = report['arms'][arm]
        for key, value in [('accuracy', accuracy_score(saved.outcome, saved[arm])),
                           ('balanced_accuracy', balanced_accuracy_score(saved.outcome, saved[arm])),
                           ('baseline_recall', recall_score(saved.outcome, saved[arm], pos_label=0)),
                           ('stress_condition_recall', recall_score(saved.outcome, saved[arm], pos_label=1))]:
            np.testing.assert_allclose(values[key], value, atol=1e-12, rtol=0); checks += 1
    result = {'status': 'passed', 'independent_metric_checks': checks, 'saved_artifact_replays': len(evaluation['artifacts']),
              'person_disjoint': True, 'old_experiments_001_018_preserved': True, 'production_enabled': False}
    write(out / 'verification.json', result); print(json.dumps(result), flush=True)
