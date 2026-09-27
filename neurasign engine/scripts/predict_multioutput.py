#!/usr/bin/env python3
"""Run a locally trained offline bundle against a physiological feature object."""
import argparse
import json
from pathlib import Path
import sys

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True,type=Path)
    args=parser.parse_args()
    payload=json.loads(args.input.read_text())
    bundle=joblib.load(ROOT/"models/multioutput-v1.joblib")
    print(json.dumps(bundle.predict(payload["features"],payload["pipeline_id"]),indent=2,allow_nan=False))
