"""Firebase identity verification and environment boundaries for company data."""
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from threading import Lock

from fastapi import Header, HTTPException

from .store import FirestoreStore, SQLiteStore


def production():
    return os.getenv('NEURASIGN_ENV') == 'production' or bool(os.getenv('K_SERVICE'))


def local_test_account():
    if (not production() and os.getenv('FIREBASE_PROJECT_ID') == 'demo-neurasign'
            and os.getenv('FIREBASE_AUTH_EMULATOR_HOST') and os.getenv('FIRESTORE_EMULATOR_HOST')
            and os.getenv('WORKSPACE_STORE') == 'firestore'):
        return {'email': 'demo@neurasign.test', 'password': 'Neurasign2026!'}
    return None


def workspace_config():
    project = os.getenv('FIREBASE_PROJECT_ID', '')
    api_key = os.getenv('FIREBASE_WEB_API_KEY', '')
    emulator = os.getenv('FIREBASE_AUTH_EMULATOR_HOST', '')
    return {
        'enabled': bool(project and api_key),
        'firebase': {'projectId': project, 'apiKey': api_key, 'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN', f'{project}.firebaseapp.com')},
        'emulator_url': os.getenv('FIREBASE_AUTH_EMULATOR_URL', 'http://localhost:9099') if emulator and not production() else None,
        'demo_available': not production(),
        'test_account': local_test_account(),
    }


def validate_environment():
    if production():
        if os.getenv('FIREBASE_AUTH_EMULATOR_HOST') or os.getenv('FIRESTORE_EMULATOR_HOST'):
            raise RuntimeError('Emulators are forbidden in production.')
        if not workspace_config()['enabled']:
            raise RuntimeError('Production requires Firebase project and web authentication configuration.')
        if os.getenv('WORKSPACE_STORE') != 'firestore':
            raise RuntimeError('Production requires persistent Firestore storage.')


@lru_cache(maxsize=1)
def get_store():
    validate_environment()
    if os.getenv('WORKSPACE_STORE') == 'firestore':
        return FirestoreStore(os.environ['FIREBASE_PROJECT_ID'], os.getenv('FIRESTORE_DATABASE', '(default)'))
    root = Path(__file__).resolve().parents[3]
    return SQLiteStore(os.getenv('WORKSPACE_DB', str(root / 'var/workspace.sqlite3')))


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str
    name: str


_app_lock = Lock()


def firebase_app():
    import firebase_admin
    with _app_lock:
        try:
            return firebase_admin.get_app('neurasign-workspace')
        except ValueError:
            return firebase_admin.initialize_app(options={'projectId': os.environ['FIREBASE_PROJECT_ID']}, name='neurasign-workspace')


def bearer(authorization):
    if not authorization or not authorization.startswith('Bearer ') or len(authorization) > 8192:
        raise HTTPException(401, 'Sign in to continue.', headers={'WWW-Authenticate': 'Bearer'})
    return authorization[7:]


def identity(authorization: str | None = Header(None)):
    if not workspace_config()['enabled']:
        raise HTTPException(503, 'Company sign-in has not been configured.')
    validate_environment()
    token = bearer(authorization)
    if token.startswith('nsd_'):
        raise HTTPException(401, 'A device credential cannot access a user account.')
    from firebase_admin import auth
    try:
        claims = auth.verify_id_token(token, app=firebase_app(), check_revoked=True)
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, auth.UserNotFoundError, ValueError):
        raise HTTPException(401, 'Your session expired. Please sign in again.') from None
    except Exception:
        raise HTTPException(503, 'Sign-in verification is temporarily unavailable.') from None
    if not claims.get('email_verified') or not claims.get('email'):
        raise HTTPException(403, 'Verify your email before accessing a company workspace.')
    return Identity(claims['uid'], claims['email'].strip().lower(), str(claims.get('name') or claims['email'].split('@')[0])[:80])
