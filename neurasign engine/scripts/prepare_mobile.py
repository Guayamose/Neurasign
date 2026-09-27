#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.external_labeled import prepare_mobile
if __name__=='__main__':prepare_mobile(ROOT)
