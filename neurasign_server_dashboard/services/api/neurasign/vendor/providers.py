"""Translate documented vendor records, retaining time, source and aggregation.

WHOOP reference: developer.whoop.com/api (v2).
Google reference: health.googleapis.com/$discovery/rest?version=v4.
"""
from datetime import datetime, timezone
import hashlib
import json
import math


def stable(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def date(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Vendor timestamps must include an offset.')
    return result.astimezone(timezone.utc)


def iso(value):
    return value.isoformat().replace('+00:00', 'Z')


def numeric(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a measurement.')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Non-finite vendor measurement.')
    return value


def reading(group, name, manufacturer, metric, unit, value, end, record, start=None, samples=None, offsets=None):
    cap = dict(metric=metric, unit=unit, delivery_mode='sync', measurement_kind='summary' if start else 'sample',
               method=group, timestamp_basis='source_record')
    row = dict(metric=metric, unit=unit, value=numeric(value), measured_at=iso(end), source_record_id=stable(record))
    if start:
        period = (end-start).total_seconds()
        if period <= 0 or period > 7*86400 or period != int(period):
            # Keep fractional endpoints precise: rounded duration must cover the whole interval.
            if 0 < period <= 7*86400:
                period = math.ceil(period)
            else:
                raise ValueError('Invalid vendor summary period.')
        cap['interval_variable'] = True
        row['interval_seconds'] = int(period)
    if samples is not None:
        row.update(samples=samples, sample_offsets_ms=offsets)
    return dict(group=group, name=name, manufacturer=manufacturer, capability=cap, measurement=row)


def whoop_records(sleeps, recoveries, cycles, workouts):
    output = []
    sleep_by_id = {str(row['id']): row for row in sleeps}
    for recovery in recoveries:
        sleep = sleep_by_id.get(str(recovery.get('sleep_id')))
        if not sleep or recovery.get('score_state') != 'SCORED' or recovery.get('score', {}).get('user_calibrating'):
            continue
        start, end = date(sleep['start']), date(sleep['end'])
        for field, metric, unit in [('resting_heart_rate', 'heart_rate', 'bpm'), ('hrv_rmssd_milli', 'hrv_rmssd', 'ms'),
                                     ('spo2_percentage', 'oxygen_saturation', '%'), ('skin_temp_celsius', 'skin_temperature', '°C')]:
            value = recovery.get('score', {}).get(field)
            if value is not None:
                output.append(reading('whoop-recovery-v2', 'WHOOP · overnight summary', 'WHOOP', metric, unit, value, end,
                                      ['recovery', recovery['cycle_id'], field], start))
    for sleep in sleeps:
        value = (sleep.get('score') or {}).get('respiratory_rate')
        if sleep.get('score_state') == 'SCORED' and value is not None and sleep.get('end'):
            output.append(reading('whoop-sleep-v2', 'WHOOP · sleep summary', 'WHOOP', 'respiratory_rate', 'breaths/min', value,
                                  date(sleep['end']), ['sleep', sleep['id']], date(sleep['start'])))
    for kind, records in [('cycle', cycles), ('workout', workouts)]:
        for row in records:
            if row.get('score_state') == 'SCORED' and row.get('end') and (row.get('score') or {}).get('average_heart_rate') is not None:
                output.append(reading(f'whoop-{kind}-v2', f'WHOOP · {kind} summary', 'WHOOP', 'heart_rate', 'bpm',
                                      row['score']['average_heart_rate'], date(row['end']), [kind, row['id']], date(row['start'])))
    return output


GOOGLE_TYPES = {'heart-rate': ('heartRate', 'heart_rate', 'bpm', 'beatsPerMinute'),
                'oxygen-saturation': ('oxygenSaturation', 'oxygen_saturation', '%', 'percentage'),
                'core-body-temperature': ('coreBodyTemperature', 'core_body_temperature', '°C', 'temperatureCelsius')}


def google_records(kind, records):
    output = []
    for record in records:
        source = record.get('dataSource', {})
        device = source.get('device', {})
        # Health API can contain manual/third-party entries; do not call those wearable samples.
        if source.get('recordingMethod') == 'MANUAL' or device.get('formFactor') not in ('WATCH', 'FITNESS_BAND', 'RING', 'CHEST_STRAP'):
            continue
        fingerprint = stable(source)[:16]
        name = str(device.get('displayName') or device.get('manufacturer') or 'Google Health wearable')[:45]
        manufacturer = str(device.get('manufacturer') or 'Google Health')[:80]
        if kind in GOOGLE_TYPES:
            field, metric, unit, value = GOOGLE_TYPES[kind]
            data = record[field]
            time = date(data['sampleTime']['physicalTime'])
            output.append(reading(f'google-health-{fingerprint}-{kind}', f'{name} · synced', manufacturer, metric, unit,
                                  data[value], time, [source, kind, iso(time)]))
        elif kind == 'electrocardiogram':
            data = record['electrocardiogram']
            rate, scale, values = data.get('samplingFrequencyHertz'), data.get('millivoltsScalingFactor'), data.get('waveformSamples')
            if not rate or not scale or not values or rate <= 0 or scale <= 0:
                continue
            start = date(data['interval']['startTime'])
            # API start/end can be equal: cadence and waveform length determine actual block times.
            from datetime import timedelta
            width = max(1, min(512, int(rate*10)+1))
            for index in range(0, len(values), width):
                samples = [numeric(v)/scale for v in values[index:index+width]]
                end = start + timedelta(seconds=(index+len(samples)-1)/rate)
                output.append(reading(f'google-health-{fingerprint}-ecg', f'{name} · recorded ECG', manufacturer,
                    'electrocardiogram', 'mV', samples[-1], end, [record.get('name'), iso(start), index],
                    samples=samples, offsets=[(i-len(samples)+1)*1000/rate for i in range(len(samples))]))
    return output
