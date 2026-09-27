#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['cache','prepare'])
    args=parser.parse_args()
    from neurasign_engine import dailysense_data
    (dailysense_data.cache_available if args.stage=='cache' else dailysense_data.prepare)(ROOT)
