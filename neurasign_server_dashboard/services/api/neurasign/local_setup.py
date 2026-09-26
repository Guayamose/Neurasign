"""Public test login for the local Firebase emulators only."""
from firebase_admin import auth

from .identity import Identity, firebase_app, get_store, local_test_account
from .workspace import CompanyInput, create_company, digest


def ensure_local_test_account():
    credentials = local_test_account()
    if not credentials:
        return
    app = firebase_app()
    try:
        user = auth.get_user_by_email(credentials['email'], app=app)
    except auth.UserNotFoundError:
        user = auth.create_user(uid='neurasign-local-test-user', display_name='Taylor',
                                email_verified=True, app=app, **credentials)
    if not user.email_verified:
        user = auth.update_user(user.uid, email_verified=True, app=app)
    store = get_store()
    account = store.get(f'accounts/{digest(user.uid)}')
    if not account or not account.get('organizations'):
        create_company(CompanyInput(name='NEURASIGN Test Workspace'),
                       Identity(user.uid, user.email, user.display_name or 'Taylor'), store)
