#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine import readiness_refinement as source
from neurasign_engine import readiness_refinement_training as training
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run','verify'])
    args=parser.parse_args()
    result=source.prepare(ROOT) if args.action=='prepare' else getattr(training,args.action)(ROOT)
    print(json.dumps(result),flush=True)
