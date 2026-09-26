"""Export the authoritative API schemas for native gateway implementers.

Run with PYTHONPATH=services/api .venv/bin/python scripts/export_gateway_contract.py.
Use --check to verify that checked-in schemas match server validation.
"""
import argparse
import json
from pathlib import Path

from neurasign.telemetry import ObservationBatch, SourceInput, catalog

DESTINATION = Path(__file__).resolve().parents[2] / 'neurasign_phone_app/contracts'


def documents():
    return {'source.schema.json': SourceInput.model_json_schema(),
            'observations.schema.json': ObservationBatch.model_json_schema(),
            'metrics.json': {'schema_version': 2, 'metrics': catalog()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, document in documents().items():
        content = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
        path = DESTINATION / name
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f'Gateway contract is stale: {name}. Run the exporter.')
        else:
            path.write_text(content)
    print('Gateway contract matches server validation.' if args.check else 'Exported gateway schemas and metric catalog.')


if __name__ == '__main__':
    main()
