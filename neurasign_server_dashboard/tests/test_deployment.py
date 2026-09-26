"""Deployment boundaries are tested offline: never use the active cloud account."""
import json
import subprocess
import urllib.request

import pytest

from scripts.deploy_gcloud import Deployment, arguments, main, manifests


def options(tmp_path):
    return ['--project', 'neurasign-test-project', '--account', 'future@example.com', '--firebase-api-key', 'public-test-key', '--output', str(tmp_path), '--tag', 'test']


def test_default_plan_has_no_network_or_gcloud_calls(tmp_path, monkeypatch):
    def prohibited(*args, **kwargs):
        pytest.fail('Offline preparation must not access gcloud or the network.')
    monkeypatch.setattr(subprocess, 'run', prohibited)
    monkeypatch.setattr(urllib.request, 'urlopen', prohibited)
    main(options(tmp_path))
    service = json.loads((tmp_path / 'service.json').read_text())
    containers = service['spec']['template']['spec']['containers']
    web, api = containers
    assert web['ports'] == [{'containerPort': 8080}] and 'ports' not in api
    api_env = {item['name']: item['value'] for item in api['env']}
    assert api_env['NEURASIGN_ENV'] == 'production' and api_env['WORKSPACE_STORE'] == 'firestore'
    assert not any('EMULATOR' in name or 'JEV' in name or 'GEMINI' in name for name in api_env)
    assert 'localhost:9099' not in json.dumps(service)
    assert 'neurasign-runtime@neurasign-test-project' in service['spec']['template']['spec']['serviceAccountName']


def test_cloud_commands_always_target_explicit_account_and_project(tmp_path, monkeypatch):
    calls = []
    def capture(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='[]')
    monkeypatch.setattr(subprocess, 'run', capture)
    deploy = Deployment(arguments(options(tmp_path)))
    deploy.json('firestore', 'databases', 'list')
    assert '--account=future@example.com' in calls[0] and '--project=neurasign-test-project' in calls[0]
    assert 'config' not in calls[0]


def test_rejects_emulator_production_target(tmp_path):
    args = options(tmp_path)
    args[1] = 'demo-neurasign'
    with pytest.raises(SystemExit):
        arguments([*args, '--apply'])
