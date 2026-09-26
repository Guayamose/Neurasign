"""Prepare a deployment offline; --apply explicitly deploys to the supplied account.

No command uses the terminal's default account or project. Never reads .env.
Prerequisite: a dedicated billed Firebase project, web app and email/password Auth.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--firebase-api-key', required=True, help='Public Firebase web app API key, not a service account key.')
    parser.add_argument('--region', default='europe-west1')
    parser.add_argument('--tag', default=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--output', type=Path, default=ROOT / 'var/deploy')
    parser.add_argument('--integrations-origin', help='Public HTTPS origin registered for wearable OAuth callbacks.')
    parser.add_argument('--integrations-key-secret', help='Existing Secret Manager secret containing a Fernet key.')
    parser.add_argument('--whoop-client-id')
    parser.add_argument('--whoop-client-secret', help='Existing Secret Manager secret name; never a secret value.')
    parser.add_argument('--google-health-client-id')
    parser.add_argument('--google-health-client-secret', help='Existing Secret Manager secret name; never a secret value.')
    parser.add_argument('--apply', action='store_true', help='Create/update billable resources and deploy. Without this flag everything is offline.')
    args = parser.parse_args(argv)
    checks = {'project': r'[a-z][a-z0-9-]{4,28}[a-z0-9]', 'account': r'[^\s@]+@[^\s@]+\.[^\s@]+', 'region': r'[a-z]+-[a-z]+[0-9]+', 'tag': r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', 'firebase_api_key': r'[A-Za-z0-9_-]{8,128}'}
    for key, pattern in checks.items():
        if not re.fullmatch(pattern, getattr(args, key)):
            parser.error(f'Invalid {key.replace("_", "-")}.')
    selected = bool(args.whoop_client_id or args.google_health_client_id)
    for provider in ('whoop', 'google_health'):
        if bool(getattr(args, provider+'_client_id')) != bool(getattr(args, provider+'_client_secret')):
            parser.error('Each wearable provider needs a client ID and a Secret Manager secret name.')
    if any((selected, args.integrations_origin, args.integrations_key_secret)) and not (selected and args.integrations_origin and args.integrations_key_secret):
        parser.error('Wearable OAuth requires a provider, HTTPS callback origin and encryption-key secret.')
    for name in ('integrations_key_secret', 'whoop_client_secret', 'google_health_client_secret'):
        if getattr(args, name) and not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', getattr(args, name)):
            parser.error('Use a Secret Manager secret name, never a secret value.')
    if args.integrations_origin:
        origin = urllib.parse.urlparse(args.integrations_origin)
        if origin.scheme != 'https' or not origin.netloc or origin.username or origin.path or origin.query or origin.fragment:
            parser.error('Wearable callback origin must be HTTPS without a path or credentials.')
    if args.project.startswith('demo-') and args.apply:
        parser.error('A demo emulator project cannot be deployed.')
    args.output = args.output.resolve()
    return args


def env(values):
    return [{'name': key, 'value': str(value)} for key, value in values.items()]


def manifests(args):
    registry = f'{args.region}-docker.pkg.dev/{args.project}/neurasign'
    runtime = f'neurasign-runtime@{args.project}.iam.gserviceaccount.com'
    build = f'projects/{args.project}/serviceAccounts/neurasign-build@{args.project}.iam.gserviceaccount.com'
    service = {
        'apiVersion': 'serving.knative.dev/v1', 'kind': 'Service',
        'metadata': {'name': 'neurasign', 'annotations': {'run.googleapis.com/ingress': 'all'}},
        'spec': {'template': {
            'metadata': {'annotations': {'autoscaling.knative.dev/minScale': '0', 'autoscaling.knative.dev/maxScale': '5', 'run.googleapis.com/container-dependencies': '{"web":["api"]}', 'run.googleapis.com/execution-environment': 'gen2'}},
            'spec': {'serviceAccountName': runtime, 'containerConcurrency': 20, 'timeoutSeconds': 60,
                     'containers': [
                         {'name': 'web', 'image': f'{registry}/web:{args.tag}', 'ports': [{'containerPort': 8080}],
                          'env': env({'NEURASIGN_ENV': 'production', 'API_INTERNAL_URL': 'http://127.0.0.1:8000'}),
                          'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
                          'startupProbe': {'tcpSocket': {'port': 8080}, 'periodSeconds': 2, 'failureThreshold': 60}},
                         {'name': 'api', 'image': f'{registry}/api:{args.tag}',
                          'env': env({'NEURASIGN_ENV': 'production', 'PORT': 8000, 'WORKSPACE_STORE': 'firestore', 'FIREBASE_PROJECT_ID': args.project, 'FIREBASE_WEB_API_KEY': args.firebase_api_key, 'FIREBASE_AUTH_DOMAIN': f'{args.project}.firebaseapp.com'}),
                          'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
                          'startupProbe': {'httpGet': {'path': '/api/health', 'port': 8000}, 'periodSeconds': 2, 'failureThreshold': 60},
                          'livenessProbe': {'httpGet': {'path': '/api/health', 'port': 8000}, 'periodSeconds': 30, 'failureThreshold': 3}},
                     ]}}, 'traffic': [{'latestRevision': True, 'percent': 100}]},
    }
    if args.integrations_origin:
        api_env = service['spec']['template']['spec']['containers'][1]['env']
        api_env.extend(env({'INTEGRATIONS_PUBLIC_ORIGIN': args.integrations_origin}))
        names = {'INTEGRATIONS_ENCRYPTION_KEY': args.integrations_key_secret}
        for provider in ('whoop', 'google_health'):
            client = getattr(args, provider+'_client_id')
            if client:
                api_env.extend(env({provider.upper()+'_CLIENT_ID': client}))
                names[provider.upper()+'_CLIENT_SECRET'] = getattr(args, provider+'_client_secret')
        api_env.extend({'name': name, 'valueFrom': {'secretKeyRef': {'name': secret, 'key': 'latest'}}} for name, secret in names.items())
    cloudbuild = {
        'steps': [{'name': 'gcr.io/cloud-builders/docker', 'args': ['build', '-f', file, '-t', f'{registry}/{name}:{args.tag}', '.']} for name, file in [('api', 'services/api/Dockerfile'), ('web', 'apps/web/Dockerfile')]],
        'images': [f'{registry}/{name}:{args.tag}' for name in ('api', 'web')],
        'serviceAccount': build, 'options': {'logging': 'CLOUD_LOGGING_ONLY'}, 'timeout': '1200s',
    }
    return service, cloudbuild


class Deployment:
    def __init__(self, args):
        self.args = args
        self.prefix = ['gcloud', f'--project={args.project}', f'--account={args.account}', '--quiet']

    def command(self, *parts, capture=False):
        command = [*self.prefix, *parts]
        print(shlex.join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE if capture else None)
        return result.stdout.strip() if capture else None

    def json(self, *parts):
        return json.loads(self.command(*parts, '--format=json', capture=True))

    def rest(self, method, url, data=None):
        # Captured in memory only; the access token is never printed or written.
        token = self.command('auth', 'print-access-token', capture=True)
        request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, method=method,
                                         headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'X-Goog-User-Project': self.args.project})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def apply(self):
        a = self.args
        p = a.project
        runtime = f'neurasign-runtime@{p}.iam.gserviceaccount.com'
        build = f'neurasign-build@{p}.iam.gserviceaccount.com'
        self.command('services', 'enable', 'run.googleapis.com', 'cloudbuild.googleapis.com', 'artifactregistry.googleapis.com', 'firestore.googleapis.com', 'identitytoolkit.googleapis.com', 'firebaserules.googleapis.com', 'iam.googleapis.com', 'logging.googleapis.com')
        config_url = f'https://identitytoolkit.googleapis.com/admin/v2/projects/{p}/config'
        auth = self.rest('GET', config_url)
        email = auth.get('signIn', {}).get('email', {})
        if not email.get('enabled') or not email.get('passwordRequired'):
            raise RuntimeError('Enable Firebase Email/Password authentication first. See docs/gcloud-deployment.md.')
        # Auth key project mismatch should fail before allocating storage/build resources.
        project_config = f'https://identitytoolkit.googleapis.com/v1/projects?key={urllib.parse.quote(a.firebase_api_key)}'
        with urllib.request.urlopen(project_config, timeout=30) as response:
            if json.load(response).get('projectId') != p:
                raise RuntimeError('The Firebase web API key belongs to a different project.')
        accounts = self.json('iam', 'service-accounts', 'list')
        for name, email in [('neurasign-runtime', runtime), ('neurasign-build', build)]:
            if not any(account['email'] == email for account in accounts):
                self.command('iam', 'service-accounts', 'create', name, f'--display-name={name}')
            self.command('iam', 'service-accounts', 'add-iam-policy-binding', email, f'--member=user:{a.account}', '--role=roles/iam.serviceAccountUser')
        for email, roles in [(runtime, ['roles/datastore.user', 'roles/firebaseauth.viewer']), (build, ['roles/logging.logWriter', 'roles/serviceusage.serviceUsageConsumer'])]:
            for role in roles:
                self.command('projects', 'add-iam-policy-binding', p, f'--member=serviceAccount:{email}', f'--role={role}', '--condition=None')
        if a.integrations_origin:
            self.command('services', 'enable', 'secretmanager.googleapis.com')
            for secret in (a.integrations_key_secret, a.whoop_client_secret, a.google_health_client_secret):
                if secret:
                    self.command('secrets', 'describe', secret)
                    self.command('secrets', 'add-iam-policy-binding', secret, f'--member=serviceAccount:{runtime}', '--role=roles/secretmanager.secretAccessor')
        repos = self.json('artifacts', 'repositories', 'list', f'--location={a.region}')
        if not any(repo['name'].endswith('/neurasign') for repo in repos):
            self.command('artifacts', 'repositories', 'create', 'neurasign', '--repository-format=docker', f'--location={a.region}')
        self.command('artifacts', 'repositories', 'add-iam-policy-binding', 'neurasign', f'--location={a.region}', f'--member=serviceAccount:{build}', '--role=roles/artifactregistry.writer')
        bucket = f'{p}-neurasign-build'
        buckets = self.json('storage', 'buckets', 'list')
        if not any(item.get('name') == bucket for item in buckets):
            self.command('storage', 'buckets', 'create', f'gs://{bucket}', f'--location={a.region}', '--uniform-bucket-level-access', '--public-access-prevention')
        self.command('storage', 'buckets', 'add-iam-policy-binding', f'gs://{bucket}', f'--member=serviceAccount:{build}', '--role=roles/storage.objectViewer')
        databases = self.json('firestore', 'databases', 'list')
        existing = next((db for db in databases if db['name'].endswith('/(default)')), None)
        if existing:
            if existing.get('type') != 'FIRESTORE_NATIVE' or existing.get('locationId') != a.region:
                raise RuntimeError('Existing Firestore location/type differs. Use the correct region and a dedicated project.')
            self.command('firestore', 'databases', 'update', '--database=(default)', '--delete-protection', '--enable-pitr')
        else:
            self.command('firestore', 'databases', 'create', '--database=(default)', f'--location={a.region}', '--type=firestore-native', '--delete-protection', '--enable-pitr')
        for group in ('readings', 'latest', 'observations', 'signal_state', 'audit', 'invitations', 'enrollments', 'vendor_connections', 'vendor_oauth_states'):
            self.command('firestore', 'fields', 'ttls', 'update', 'expires_at', f'--collection-group={group}', '--database=(default)', '--enable-ttl', '--async')
        indexes = self.json('firestore', 'indexes', 'composite', 'list', '--database=(default)')
        fields = [{'fieldPath': 'series_id', 'order': 'ASCENDING'}, {'fieldPath': 'timestamp', 'order': 'DESCENDING'}]
        if not any('/collectionGroups/observations/' in item.get('name', '') and item.get('queryScope') == 'COLLECTION'
                   and [field for field in item.get('fields', []) if field.get('fieldPath') != '__name__'] == fields for item in indexes):
            self.command('firestore', 'indexes', 'composite', 'create', '--database=(default)', '--collection-group=observations',
                         '--query-scope=COLLECTION', '--field-config=field-path=series_id,order=ascending',
                         '--field-config=field-path=timestamp,order=descending')
        schedules = self.json('firestore', 'backups', 'schedules', 'list', '--database=(default)')
        if not any('dailyRecurrence' in schedule for schedule in schedules):
            self.command('firestore', 'backups', 'schedules', 'create', '--database=(default)', '--retention=7d', '--recurrence=daily')
        # Server SDK uses IAM. Direct mobile/browser database access is denied.
        rules_url = f'https://firebaserules.googleapis.com/v1/projects/{p}'
        ruleset = self.rest('POST', rules_url + '/rulesets', {'source': {'files': [{'name': 'firestore.rules', 'content': (ROOT / 'infra/gcloud/firestore.rules').read_text()}]}})
        release = {'name': f'projects/{p}/releases/cloud.firestore', 'rulesetName': ruleset['name']}
        try:
            self.rest('GET', rules_url + '/releases/cloud.firestore')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            self.rest('POST', rules_url + '/releases', release)
        else:
            self.rest('PATCH', rules_url + '/releases/cloud.firestore', {'release': release})
        self.command('builds', 'submit', '.', f'--config={a.output / "cloudbuild.json"}', f'--gcs-source-staging-dir=gs://{bucket}/source')
        self.command('run', 'services', 'replace', str(a.output / 'service.json'), f'--region={a.region}')
        self.command('run', 'services', 'add-iam-policy-binding', 'neurasign', f'--region={a.region}', '--member=allUsers', '--role=roles/run.invoker')
        url = self.command('run', 'services', 'describe', 'neurasign', f'--region={a.region}', '--format=value(status.url)', capture=True)
        domain = urllib.parse.urlparse(url).hostname
        current = self.rest('GET', config_url)
        domains = current.get('authorizedDomains', [])
        if domain not in domains:
            self.rest('PATCH', config_url + '?updateMask=authorizedDomains', {'authorizedDomains': [*domains, domain]})
        subprocess.run(['python3', str(ROOT / 'scripts/check_deployment.py'), url], cwd=ROOT, check=True)
        print(f'Deployed {url}. Complete the two-account acceptance check in docs/gcloud-deployment.md before inviting a company.')


def main(argv=None):
    args = arguments(argv)
    service, cloudbuild = manifests(args)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('service.json', service), ('cloudbuild.json', cloudbuild)]:
        (args.output / name).write_text(json.dumps(value, indent=2) + '\n')
    print(f'Prepared {args.output}\nTarget account: {args.account}\nTarget project: {args.project}\nRegion: {args.region}')
    if args.apply:
        Deployment(args).apply()
    else:
        print('OFFLINE PLAN ONLY. No gcloud command or network request was executed.\nReview the generated files and docs/gcloud-deployment.md; add --apply when the new account is ready.')


if __name__ == '__main__':
    main()
