#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.transfer_training import development
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['universe','pooled','latent','native'])
    args=parser.parse_args();development(ROOT,args.mode)
