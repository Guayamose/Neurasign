.PHONY: setup dev test build smoke models-prepare

setup:
	python3 scripts/setup.py

dev:
	docker compose up -d --wait emulator
	python3 scripts/dev.py

test:
	.venv/bin/python -m pytest -q

build:
	cd apps/web && npm run build

smoke:
	.venv/bin/python scripts/smoke.py

models-prepare:
	python3 scripts/prepare_model_engine.py
