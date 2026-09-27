"""Raw MEFAR wrist-only acquisition, audited CFS labels and causal features.

No author-normalized/oversampled table, EEG, demographics or time-of-day inputs.
The questionnaire is measured once per recording, not independently per window.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt, welch

DATASET = 'https://data.mendeley.com/datasets/z3g26tphnv/5'
PAPER = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10762351/'
ARCHIVE_SHA = '2de6973d2c9e4595c670dd01f66d592efda1daaea7342eeba518a1913ab8afbc'
DOWNLOAD = 'https://data.mendeley.com/public-files/datasets/z3g26tphnv/files/05c41cc5-03d0-47c0-b68b-32a418636e16/file_downloaded'
STATS = ['mean', 'std', 'p10', 'p90', 'slope', 'change', 'diff_rms']
FEATURES = [f'{c}_{s}' for c in ['hr', 'bvp', 'eda', 'temperature', 'motion'] for s in STATS] + [
    'bvp_dominant_hz', 'bvp_cardiac_power_fraction', 'bvp_peak_rate', 'bvp_prv_rmssd_ms',
    'bvp_prv_sdnn_ms', 'eda_positive_change_per_second', 'motion_enmo', 'motion_jerk_rms']
PROFILES = {
    'cardiac': [c for c in FEATURES if c.startswith(('hr_', 'bvp_'))],
    'autonomic': [c for c in FEATURES if not c.startswith('motion_')],
    'all_wrist': list(FEATURES),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire(root):
    local = root/'data/external/mefar';local.mkdir(parents=True, exist_ok=True)
    archive = local/'MEFAR_raw_data.zip'
    if not archive.exists():
        subprocess.run(['curl', '-fL', '--retry', '2', DOWNLOAD, '-o', str(archive)], check=True)
    if sha(archive) != ARCHIVE_SHA:
        raise ValueError('MEFAR raw archive differs from publisher SHA256')
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            target = (local/'raw'/name).resolve()
            if not target.is_relative_to((local/'raw').resolve()):
                raise ValueError('Unsafe archive path')
        zipped.extractall(local/'raw')
    provenance = {'dataset_url':DATASET, 'paper_url':PAPER, 'license':'CC BY 4.0',
                  'archive_sha256':ARCHIVE_SHA, 'archive_bytes':archive.stat().st_size,
                  'download_url':DOWNLOAD, 'processed_data_used':False,
                  'reason':'Author processed table includes whole-table scaling and minority oversampling.'}
    (local/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return local/'raw/MEFAR'


def read_labels(directory):
    """Independently sum all 11 marked questionnaire items and verify summary."""
    workbook = pd.ExcelFile(directory/'general_info.xlsx')
    summary = pd.read_excel(workbook, sheet_name='Subject List')
    result = []
    for _, person in summary.iterrows():
        sheet = pd.read_excel(workbook, sheet_name=person.subjects)
        for session, offset in [('morning', 1), ('evening', 7)]:
            cells = sheet.iloc[[*range(1, 11), 12], offset:offset+4]
            marked = cells.map(lambda cell: str(cell).strip().lower() == 'x').to_numpy()
            if not (marked.sum(axis=1) == 1).all():
                raise ValueError('Missing/ambiguous CFS response')
            score = int((marked*np.arange(4)).sum())
            if score != int(person[f'{session}-mental fatigue state']):
                raise ValueError('CFS item sum disagrees with summary')
            participant = str(person.subjects)
            result.append({'participant':participant, 'session':session,
                           'unit_id':participant+'_'+session, 'cfs':score, 'outcome':int(score >= 12)})
    labels = pd.DataFrame(result)
    if labels.duplicated(['participant', 'session']).any() or len(labels) != 46:
        raise ValueError('Unexpected source label inventory')
    return labels


def read_channel(path):
    array = np.loadtxt(path, delimiter=',', ndmin=2)
    start, rate = float(array[0, 0]), float(array[1, 0])
    if rate <= 0 or not np.isfinite(start):
        raise ValueError('Invalid E4 header')
    return {'start':start, 'rate':rate, 'values':array[2:]}


def statistics(values, rate):
    values = np.asarray(values, float)
    if len(values) < 3 or not np.isfinite(values).all():
        return {name:np.nan for name in STATS}
    times = np.arange(len(values))/rate;times -= times.mean()
    third = max(1, len(values)//3)
    return dict(zip(STATS, [float(values.mean()), float(values.std()),
        float(np.quantile(values, .1)), float(np.quantile(values, .9)),
        float(np.dot(times, values-values.mean())/np.dot(times, times)),
        float(values[-third:].mean()-values[:third].mean()), float(np.sqrt(np.mean(np.diff(values)**2)))]))


def features(channels, end, width):
    """Every signal slice is confined to [end-width, end); no future statistics."""
    result = dict.fromkeys(FEATURES, np.nan)
    for name, channel in channels.items():
        rate = channel['rate'];data = channel['values']
        left = max(0, int(np.ceil((end-width-channel['start'])*rate-1e-7)))
        right = min(len(data), int(np.ceil((end-channel['start'])*rate-1e-7)))
        values = data[left:right].copy()
        if len(values) < .95*width*rate or not np.isfinite(values).all():
            continue
        if name == 'motion':
            axes = values/64.;values = np.linalg.norm(axes, axis=1)
            result['motion_enmo'] = float(np.maximum(values-1, 0).mean())
            result['motion_jerk_rms'] = float(np.sqrt(np.mean(np.diff(values)**2))*rate)
        else:
            values = values[:, 0]
        if name == 'hr' and ((values < 30) | (values > 220)).any():
            continue
        if name == 'eda' and ((values < 0) | (values > 100)).any():
            continue
        if name == 'temperature' and ((values < 10) | (values > 45)).any():
            continue
        result.update({name+'_'+key:value for key, value in statistics(values, rate).items()})
        if name == 'eda':
            result['eda_positive_change_per_second'] = float(np.maximum(np.diff(values), 0).mean()*rate)
        if name == 'bvp' and values.std() > 1e-6:
            frequencies, power = welch(values, fs=rate, nperseg=min(len(values), int(rate*16)))
            band = (frequencies >= .5) & (frequencies <= 4)
            result['bvp_dominant_hz'] = float(frequencies[band][np.argmax(power[band])])
            result['bvp_cardiac_power_fraction'] = float(power[band].sum()/max(power.sum(), 1e-12))
            filtered = sosfiltfilt(butter(3, [.5, 4], fs=rate, btype='bandpass', output='sos'), values)
            peaks, _ = find_peaks(filtered, distance=int(rate*.3), prominence=filtered.std()*.3)
            intervals = np.diff(peaks)/rate
            accepted = intervals[(intervals >= .3) & (intervals <= 2.)]
            if len(accepted) >= 20 and len(accepted) >= .8*len(intervals):
                result['bvp_peak_rate'] = float(60/np.median(accepted))
                result['bvp_prv_sdnn_ms'] = float(accepted.std()*1000)
                # Differences only between consecutive accepted intervals, never bridge rejected beats.
                adjacent = (intervals[:-1] >= .3) & (intervals[:-1] <= 2.) & (intervals[1:] >= .3) & (intervals[1:] <= 2.)
                if adjacent.sum() >= 10:
                    result['bvp_prv_rmssd_ms'] = float(np.sqrt(np.mean(np.diff(intervals)[adjacent]**2))*1000)
    return result


def prepare(root):
    directory = acquire(root);labels = read_labels(directory)
    rows = [];inventory = [];hashes = {}
    for row in labels.to_dict('records'):
        folder = directory/('subject_'+row['participant'][1:])/('1.morning' if row['session']=='morning' else '2.evening')
        channels = {}
        for name, file in [('hr','HR'),('bvp','BVP'),('eda','EDA'),('temperature','TEMP'),('motion','ACC')]:
            path = folder/(file+'.csv');channels[name] = read_channel(path)
            hashes[str(path.relative_to(root))] = sha(path)
        start = max(c['start'] for c in channels.values())
        end = min(c['start']+len(c['values'])/c['rate'] for c in channels.values())
        inventory.append({**row, 'overlap_seconds':end-start})
        # Same endpoints for both evidence widths; ten seconds of vendor-HR warmup is already excluded.
        for offset in np.arange(180., end-start+1e-7, 60.):
            point = {**row, 'window_end':start+float(offset), 'row_id':len(rows)}
            for width in (60, 180):
                point.update({f'w{width}__'+key:value for key,value in features(channels,start+offset,width).items()})
            rows.append(point)
    # Reject exact raw duplicates spanning participants, which would invalidate grouped independence.
    by_digest = {}
    for path,digest in hashes.items():
        if path.endswith('/BVP.csv'):
            if digest in by_digest:
                raise ValueError('Duplicated raw BVP recording: '+path+' / '+by_digest[digest])
            by_digest[digest] = path
    frame = pd.DataFrame(rows)
    if frame.groupby('unit_id').outcome.nunique().max() != 1:
        raise ValueError('Each source recording must have one observed outcome')
    out = root/'data/prepared/mefar-v1';out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out/'windows.csv.gz', index=False, compression={'method':'gzip','mtime':0})
    audit = {'people':int(frame.participant.nunique()), 'sessions':int(frame.unit_id.nunique()),
             'windows':len(frame), 'source_archive_sha256':ARCHIVE_SHA, 'inventory':inventory,
             'source_hashes':hashes, 'labels_sha256':sha(directory/'general_info.xlsx'),
             'prepared_sha256':sha(out/'windows.csv.gz'), 'features_per_width':len(FEATURES),
             'feature_availability':frame.filter(regex='^w').notna().mean().to_dict(),
             'questionnaire_item_sums_verified':46, 'processed_data_used':False, 'eeg_used':False}
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return frame,audit
