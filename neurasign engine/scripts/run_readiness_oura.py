#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine import readiness_oura
from neurasign_engine.reference_benchmark import run,verify
p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','verify']);args=p.parse_args()
if args.action=='prepare':print(readiness_oura.prepare(ROOT))
elif args.action=='run':run(ROOT,'readiness-oura-v1','data/prepared/readiness-oura-v1/days.csv.gz','experiments/016-readiness-oura-protocol.json')
else:print(json.dumps(verify(ROOT,'readiness-oura-v1')))
