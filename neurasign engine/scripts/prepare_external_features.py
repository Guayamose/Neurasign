#!/usr/bin/env python3
"""Extract unlabeled external wrist features for representation-learning trials."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from neurasign_engine.transfer_features import e4_folder,extract,add_history,from_universe
from neurasign_engine.causal import Trace


def process_folder(item):
    dataset,folder,person,session=item;folder=Path(folder)
    rows=[]
    try:
        if dataset=="clacir":traces=e4_folder(folder)
        else:
            traces={}
            for file,name,unit,rate in [("empatica_bvp.csv","bvp","au",64),("empatica_eda.csv","eda","uS",4),("empatica_temp.csv","temperature","degC",4)]:
                path=folder/file
                if path.exists():
                    d=pd.read_csv(path);d=d.drop_duplicates("time").sort_values("time")
                    traces[name]=Trace(d.time.to_numpy(float),d.iloc[:,0].to_numpy(float),rate,unit)
        if "bvp" not in traces:return [],{"folder":str(folder),"reason":"no_bvp"}
        t=traces["bvp"].times;start=t[0];stop=t[-1]+1/traces["bvp"].rate
        for end in np.arange(start+60,stop+.001,60):
            f=extract(traces,float(end))
            if np.isfinite(f["heart_rate_mean"]) or np.isfinite(f["eda_mean"]):
                rows.append({**f,"participant":dataset+":"+person,"session":session,"unit_id":dataset+":"+person+":"+session,
                             "window_end":end-start,"source_end":end,"dataset":dataset})
        return rows,None
    except (ValueError,IndexError,KeyError) as e:return [],{"folder":str(folder),"reason":type(e).__name__+": "+str(e)[:100]}


def main(dataset):
    dest=ROOT/"data/prepared/transfer-v1";dest.mkdir(parents=True,exist_ok=True)
    if dataset=="universe":
        frame=from_universe(ROOT);frame.to_csv(dest/"universe.csv.gz",index=False);print('universe',frame.shape);return
    source=ROOT/"data/external"/dataset
    manifest=json.loads((source/"manifest.json").read_text())
    if dataset=="clacir":
        folders=list((source/"extracted").rglob("BVP.csv"))
        items=[(dataset,str(p.parent),p.parent.parent.name+":"+p.parent.name,"recording") for p in folders]
        for f in manifest["files"]:
            if Path(f["member"]).name in ("BVP.csv","EDA.csv","TEMP.csv","HR.csv","ACC.csv"):
                assert hashlib.sha256((source/"extracted"/f["member"]).read_bytes()).hexdigest()==f["sha256"]
    else:
        items=[]
        for p in source.rglob("empatica_bvp.csv"):
            rel=p.relative_to(source).parts
            # Pilot and survey participant numbers are distinct ID namespaces.
            items.append((dataset,str(p.parent),rel[0]+":"+rel[1],"/".join(rel[2:-2]) or "pilot"))
        for f in manifest["files"]:
            assert hashlib.sha256((ROOT/"data/external"/f["path"]).read_bytes()).hexdigest()==f["sha256"]
        published={line.split(maxsplit=1)[1].strip():line.split()[0]
                   for line in (source/"SHA256SUMS.txt").read_text().splitlines() if line.strip()}
        for p in source.rglob("*.csv"):
            relative=p.relative_to(source).as_posix()
            assert hashlib.sha256(p.read_bytes()).hexdigest()==published[relative],relative
    rows,errors=[],[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for i,(r,e) in enumerate(pool.map(process_folder,items)):
            rows.extend(r)
            if e:errors.append(e)
            if (i+1)%20==0:print(json.dumps({"dataset":dataset,"recordings":i+1,"windows":len(rows)}),flush=True)
    frame=add_history(pd.DataFrame(rows));frame.to_csv(dest/f"{dataset}.csv.gz",index=False)
    audit={"dataset":dataset,"recordings":len(items),"windows":len(frame),"people":frame.participant.nunique(),
           "nonoverlapping_hours":len(frame)/60,"errors":errors,"source_manifest_sha256":hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest(),
           "feature_code_sha256":hashlib.sha256((ROOT/"src/neurasign_engine/transfer_features.py").read_bytes()).hexdigest(),
           "output_sha256":hashlib.sha256((dest/f"{dataset}.csv.gz").read_bytes()).hexdigest()}
    (dest/f"{dataset}-audit.json").write_text(json.dumps(audit,indent=2));print(json.dumps(audit),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("dataset",choices=["universe","clacir","cogwear"])
    main(parser.parse_args().dataset)
