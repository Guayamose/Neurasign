.PHONY: setup dev test build smoke models-prepare phone-setup phone-test contract-check test-all mobile-setup mobile-check mobile-apk onboarding-smoke

setup dev test build smoke models-prepare:
	$(MAKE) -C neurasign_server_dashboard $@

phone-setup:
	cd neurasign_phone_app && npm ci

phone-test:
	cd neurasign_phone_app && npm test

contract-check:
	cd neurasign_server_dashboard && PYTHONPATH=services/api .venv/bin/python scripts/export_gateway_contract.py --check

test-all: test phone-test contract-check

mobile-setup:
	cd neurasign_phone_app/mobile && npm ci

mobile-check:
	cd neurasign_phone_app/mobile && npm run lint && npm run typecheck

mobile-apk:
	cd neurasign_phone_app/mobile && npm run android:apk

onboarding-smoke:
	cd neurasign_server_dashboard && .venv/bin/python scripts/onboarding_smoke.py
