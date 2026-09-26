"""Phone-authorized vendor OAuth and sync. Company tokens never go to vendors.

The phone drives sync; there is no autonomous collection after phone pause.
Credentials are encrypted at rest and never returned to the dashboard or phone.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
import httpx
from pydantic import ValidationError

from .workspace import Store, device_access, digest
from .identity import production
from .company_access import capture_allowed
from .telemetry import SourceInput, Observation, ObservationBatch, register_source, ingest_observations
from .vendor.providers import GOOGLE_TYPES, date, iso, stable, whoop_records, google_records

router = APIRouter(prefix='/api/v1', tags=['Wearable accounts'])
PROVIDERS = {
    'whoop': dict(name='WHOOP', prefix='WHOOP', authorize='https://api.prod.whoop.com/oauth/oauth2/auth',
                  token='https://api.prod.whoop.com/oauth/oauth2/token',
                  scopes='offline read:recovery read:sleep read:cycles read:workout'),
    'fitbit': dict(name='Fitbit / Google Health', prefix='GOOGLE_HEALTH', authorize='https://accounts.google.com/o/oauth2/v2/auth',
                   token='https://oauth2.googleapis.com/token',
                   scopes='https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly https://www.googleapis.com/auth/googlehealth.ecg.readonly'),
}


def cipher():
    try:
        return Fernet(os.environ['INTEGRATIONS_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError):
        raise HTTPException(503, 'Wearable account encryption is not configured.') from None


def seal(value):
    return cipher().encrypt(json.dumps(value, separators=(',', ':')).encode()).decode()


def unseal(value):
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise HTTPException(503, 'Wearable account credentials cannot be decrypted.') from None


def config(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404, 'Unknown wearable account provider.')
    settings = PROVIDERS[provider]
    prefix = settings['prefix']
    client, secret = os.getenv(prefix+'_CLIENT_ID'), os.getenv(prefix+'_CLIENT_SECRET')
    origin = os.getenv('INTEGRATIONS_PUBLIC_ORIGIN', '').rstrip('/')
    parsed = urlparse(origin)
    local = parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1') and not production()
    if not client or not secret or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or (parsed.scheme != 'https' and not local):
        raise HTTPException(503, f'{settings["name"]} account connection needs server OAuth configuration.')
    cipher()
    return {**settings, 'client_id': client, 'client_secret': secret, 'redirect_uri': origin+f'/api/v1/integrations/{provider}/callback'}


def path_for(device, provider):
    return 'vendor_connections/'+digest(device+':'+provider)


def access(store, authorization, sharing=False):
    return store.atomic(lambda tx: device_access(tx, authorization, require_sharing=sharing))


class ProviderPermissionError(HTTPException):
    def __init__(self):
        super().__init__(424, 'Provider permission was not granted for this data type.')


def vendor_request(method, url, **kwargs):
    # Fixed official endpoints only, no redirects, bounded body before decoding.
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            with client.stream(method, url, **kwargs) as response:
                if response.status_code == 429:
                    raise HTTPException(429, 'Wearable provider is limiting requests. Retry later.')
                if response.status_code == 403:
                    raise ProviderPermissionError()
                if response.status_code == 401:
                    raise HTTPException(424, 'Wearable authorization expired. Reconnect the account.')
                if not response.is_success:
                    raise HTTPException(502, 'Wearable provider request failed.')
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body)+len(chunk) > 8_000_000:
                        raise HTTPException(502, 'Wearable provider response exceeds the import limit.')
                    body.extend(chunk)
                result = json.loads(body) if body else {}
                if not isinstance(result, dict):
                    raise ValueError('Expected an object')
                return result
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Wearable provider is temporarily unavailable.') from None


@router.get('/gateway/integrations')
def integration_status(store: Store, authorization: str | None = Header(None)):
    device, _, _, _ = access(store, authorization)
    result = []
    for provider, definition in PROVIDERS.items():
        try:
            config(provider); configured = True
        except HTTPException:
            configured = False
        connection = store.get(path_for(device, provider)) or {}
        result.append(dict(id=provider, name=definition['name'], configured=configured,
                           connected=bool(connection.get('tokens')), delivery='sync',
                           last_sync=connection.get('last_sync'), error=connection.get('error'),
                           warnings=connection.get('warnings', [])))
    return {'integrations': result}


@router.post('/gateway/integrations/{provider}/connect')
def connect_account(provider: str, store: Store, authorization: str | None = Header(None)):
    settings = config(provider)
    device, org, person, _ = access(store, authorization)
    state, generation, verifier = secrets.token_urlsafe(32), secrets.token_hex(16), secrets.token_urlsafe(48)
    now = time.time(); path = path_for(device, provider)
    def begin(tx):
        device_access(tx, authorization, require_sharing=False)
        current = tx.get(path) or {}
        if current.get('started_at', 0) > now-5:
            raise HTTPException(429, 'Wait a moment before reconnecting.')
        tx.put(path, dict(id=path.split('/')[-1], device=device, org=org, person=person['id'], provider=provider,
                          generation=generation, started_at=now, expires_at=now+30*86400))
        tx.put('vendor_oauth_states/'+digest(state), dict(provider=provider, path=path, generation=generation,
            expires_at=now+600, secret=seal(dict(authorization=authorization, verifier=verifier))))
    store.atomic(begin)
    params = dict(client_id=settings['client_id'], redirect_uri=settings['redirect_uri'], response_type='code',
                  scope=settings['scopes'], state=state)
    if provider == 'fitbit':
        params.update(access_type='offline', prompt='consent', code_challenge_method='S256',
                      code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
    return {'authorization_url': settings['authorize']+'?'+urlencode(params)}


@router.get('/integrations/{provider}/callback', response_class=HTMLResponse)
def oauth_callback(provider: str, store: Store, state: str = Query(min_length=32, max_length=128),
                   code: str | None = Query(None, max_length=4096), error: str | None = Query(None, max_length=200)):
    settings = config(provider)
    def consume(tx):
        path = 'vendor_oauth_states/'+digest(state); record = tx.get(path)
        if not record or record['provider'] != provider or record['expires_at'] < time.time():
            raise HTTPException(400, 'This account connection expired or was already used.')
        current = tx.get(record['path'])
        if not current or current['generation'] != record['generation']:
            raise HTTPException(410, 'This account connection was cancelled.')
        secret = unseal(record['secret'])
        device_access(tx, secret['authorization'], require_sharing=False)
        tx.delete(path)
        return record, secret
    record, secret = store.atomic(consume)
    if error or not code:
        raise HTTPException(400, 'Account authorization was not completed. Return to NEURASIGN to retry.')
    body = dict(grant_type='authorization_code', code=code, client_id=settings['client_id'],
                client_secret=settings['client_secret'], redirect_uri=settings['redirect_uri'])
    if provider == 'fitbit':
        body['code_verifier'] = secret['verifier']
    token = vendor_request('POST', settings['token'], data=body)
    if not isinstance(token.get('access_token'), str) or not token.get('refresh_token'):
        raise HTTPException(502, 'Provider did not grant renewable access. Reconnect and grant the requested permissions.')
    token['expires_at'] = time.time()+min(float(token.get('expires_in', 3600)), 86400)
    def save(tx):
        device_access(tx, secret['authorization'], require_sharing=False)
        current = tx.get(record['path'])
        if not current or current['generation'] != record['generation']:
            raise HTTPException(410, 'This connection was cancelled.')
        tx.put(record['path'], {**current, 'tokens': seal(token), 'error': None})
    store.atomic(save)
    return HTMLResponse('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>NEURASIGN</title><body><h1>Wearable account connected</h1><p>Return to NEURASIGN Link and select Sync. Your company sharing controls still apply.</p></body></html>',
                        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"})


@router.delete('/gateway/integrations/{provider}')
def disconnect_account(provider: str, store: Store, authorization: str | None = Header(None)):
    if provider not in PROVIDERS:
        raise HTTPException(404, 'Unknown provider.')
    device, _, _, _ = access(store, authorization)
    def remove(tx):
        device_access(tx, authorization, require_sharing=False)
        path = path_for(device, provider); record = tx.get(path); tx.delete(path)
        return record
    record = store.atomic(remove)
    revoked = False
    if record and record.get('tokens'):
        try:
            token = unseal(record['tokens'])
            if provider == 'whoop':
                vendor_request('DELETE', 'https://api.prod.whoop.com/developer/v2/user/access', headers={'Authorization': 'Bearer '+token['access_token']})
            else:
                vendor_request('POST', 'https://oauth2.googleapis.com/revoke', data={'token': token.get('refresh_token', token['access_token'])})
            revoked = True
        except HTTPException:
            pass  # Local deletion is authoritative even while provider is offline.
    return {'disconnected': True, 'provider_revoked': revoked}


def fetch_records(provider, token, now, cursors=None):
    headers = {'Authorization': 'Bearer '+token['access_token']}
    output = []; warnings = []; next_cursors = {}; started = time.monotonic()
    def pages(url, params, rows_key, next_key, token_key):
        rows, seen = [], set()
        for _ in range(20):
            if time.monotonic()-started > 35:
                raise HTTPException(504, 'Provider sync exceeded the request time budget. Retry later.')
            response = vendor_request('GET', url, headers=headers, params=params)
            page = response.get(rows_key, [])
            if not isinstance(page, list):
                raise HTTPException(502, 'Unexpected provider record format.')
            rows.extend(page)
            cursor = response.get(next_key)
            if not cursor:
                return rows
            if not isinstance(cursor, str) or len(cursor)>4096 or cursor in seen:
                raise HTTPException(502, 'Invalid provider pagination.')
            seen.add(cursor); params = {**params, token_key: cursor}
        raise HTTPException(502, 'Provider response exceeds one sync window. Retry a narrower window.')
    end = datetime.fromtimestamp(now, timezone.utc)
    if provider == 'whoop':
        resources = ['activity/sleep', 'recovery', 'cycle', 'activity/workout']
        def fetch(resource):
            return pages('https://api.prod.whoop.com/developer/v2/'+resource,
                {'start': iso(end-timedelta(days=6)), 'end': iso(end), 'limit': 25}, 'records', 'next_token', 'nextToken')
        with ThreadPoolExecutor(max_workers=4) as pool:
            data = dict(zip(resources, pool.map(fetch, resources)))
        output = whoop_records(data['activity/sleep'], data['recovery'], data['cycle'], data['activity/workout'])
    else:
        kinds = [*GOOGLE_TYPES, 'electrocardiogram']
        def google_page(kind):
            field = kind.replace('-', '_')
            field += '.interval.start_time' if kind == 'electrocardiogram' else '.sample_time.physical_time'
            cursor = (cursors or {}).get(kind, {})
            start = cursor.get('start') or iso(end-timedelta(days=6))
            params = {'filter': f'{field} >= "{start}"', 'pageSize': 2 if kind == 'electrocardiogram' else 500}
            if cursor.get('page'):
                params['pageToken'] = cursor['page']
            try:
                response = vendor_request('GET', 'https://health.googleapis.com/v4/users/me/dataTypes/'+kind+'/dataPoints', headers=headers, params=params)
            except ProviderPermissionError:
                return kind, cursor, start, None
            return kind, cursor, start, response
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(google_page, kinds))
        for kind, cursor, start, response in responses:
            if response is None:
                warnings.append(f'{kind}: permission unavailable. Other permitted channels are imported.'); continue
            rows = response.get('dataPoints', [])
            if not isinstance(rows, list):
                raise HTTPException(502, 'Unexpected provider record format.')
            page = response.get('nextPageToken')
            if page:
                if not isinstance(page, str) or len(page)>4096 or page == cursor.get('page'):
                    raise HTTPException(502, 'Invalid provider pagination.')
                next_cursors[kind] = {'start': start, 'page': page}
            output.extend(google_records(kind, rows))
        warnings.append('Google HRV and daily summaries are not imported without an explicit measurement interval. Source timing is never invented.')
    return output, warnings, next_cursors


@router.post('/gateway/integrations/{provider}/sync')
def sync_account(provider: str, store: Store, authorization: str | None = Header(None)):
    settings = config(provider)
    device, _, person, _ = access(store, authorization, True)
    path = path_for(device, provider); now = time.time(); lease = secrets.token_hex(16)
    def reserve(tx):
        device_access(tx, authorization)
        current = tx.get(path)
        if not current or not current.get('tokens'):
            raise HTTPException(409, 'Connect your wearable account first.')
        if current.get('lease_until', 0) > now or current.get('attempt_at', 0) > now-30:
            raise HTTPException(429, 'Sync is already running or was requested recently.')
        current = {**current, 'lease': lease, 'lease_until': now+120, 'attempt_at': now}
        tx.put(path, current); return current
    connection = store.atomic(reserve)
    def update(**changes):
        def write(tx):
            device_access(tx, authorization, require_sharing=False)
            current = tx.get(path)
            if not current or current.get('generation') != connection['generation'] or current.get('lease') != lease:
                raise HTTPException(410, 'Wearable account changed during sync.')
            tx.put(path, {**current, 'expires_at': time.time()+30*86400, **changes})
        store.atomic(write)
    try:
        token = unseal(connection['tokens'])
        if token.get('expires_at', 0) < now+60:
            refreshed = vendor_request('POST', settings['token'], data=dict(grant_type='refresh_token',
                refresh_token=token['refresh_token'], client_id=settings['client_id'], client_secret=settings['client_secret']))
            if not refreshed.get('access_token'):
                raise HTTPException(502, 'Provider returned an invalid token refresh.')
            token = {**token, **refreshed, 'expires_at': time.time()+float(refreshed.get('expires_in', 3600))}
            update(tokens=seal(token))
        records, warnings, next_cursors = fetch_records(provider, token, now, connection.get('cursors'))
        groups = {}; skipped = 0
        for record in records:
            row = record['measurement']
            try:
                stamp = date(row['measured_at']).timestamp()
                if stamp > now+5 or stamp < now-7*86400:
                    skipped += 1; continue
                duration = -(row.get('sample_offsets_ms') or [0])[0]/1000 or row.get('interval_seconds') or 0
                capture_allowed(person, stamp, duration)
                if any(stamp-duration < assignment['from'] <= stamp for assignment in person.get('assignments', [])):
                    skipped += 1; continue
                Observation(**row, id='validation', source_id='0'*64)
            except (HTTPException, ValueError, ValidationError):
                skipped += 1; continue
            group = groups.setdefault(record['group'], {'record': record, 'caps': {}, 'rows': []})
            group['caps'][record['capability']['metric']] = record['capability']; group['rows'].append(row)
        accepted = duplicates = 0
        for group_id, group in groups.items():
            # Register WHOOP's complete documented field set so optional absent values do not mutate a source.
            if group_id == 'whoop-recovery-v2':
                cap = next(iter(group['caps'].values()))
                group['caps'] = {metric: {**cap, 'metric': metric, 'unit': unit} for metric, unit in
                                  [('heart_rate', 'bpm'), ('hrv_rmssd', 'ms'), ('oxygen_saturation', '%'), ('skin_temperature', '°C')]}
            record = group['record']
            descriptor = SourceInput(client_source_id=stable([connection['generation'], group_id]), name=record['name'][:80],
                manufacturer=record['manufacturer'], adapter={'id': provider+'-cloud', 'version': '1.0.0'},
                transport='cloud_api', capabilities=list(group['caps'].values()))
            update()  # Detect disconnect before registering or writing.
            source = register_source(descriptor, store, authorization)['source']['id']
            rows = [Observation(**row, source_id=source, id=stable([source, row])) for row in group['rows']]
            for i in range(0, len(rows), 60):
                update()
                def guard(tx):
                    current = tx.get(path)
                    if not current or current.get('generation') != connection['generation'] or current.get('lease') != lease:
                        raise HTTPException(410, 'Wearable account changed during sync.')
                result = ingest_observations(ObservationBatch(schema_version=2, observations=rows[i:i+60]), store, authorization, guard)
                accepted += result['accepted']; duplicates += result['duplicates']
        update(last_sync=now, lease_until=0, error=None, warnings=warnings, cursors=next_cursors)
        return {'accepted': accepted, 'duplicates': duplicates, 'skipped': skipped, 'warnings': warnings, 'delivery': 'sync'}
    except (HTTPException, ValueError, KeyError, TypeError) as error:
        public = error if isinstance(error, HTTPException) else HTTPException(502, 'Unexpected vendor data. Nothing is synthesized.')
        try:
            update(lease_until=0, error=public.detail)
        except HTTPException:
            pass
        raise public from None
