#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine import fatigueset
from neurasign_engine.reference_benchmark import run,verify
p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('--target',choices=['physical','mental']);args=p.parse_args()
if args.action=='prepare':print(json.dumps(fatigueset.prepare(ROOT)))
else:
 if not args.target:p.error('--target required')
 name=f'fatigueset-{args.target}-v1'
 if args.action=='run':run(ROOT,name,f'data/prepared/{name}/references.csv.gz',f'experiments/015-fatigueset-{args.target}-protocol.json')
 else:print(json.dumps(verify(ROOT,name)))
