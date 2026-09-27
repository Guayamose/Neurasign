#!/usr/bin/env python3
"""Join manufacturer IBI by verified waveform alignment, without inferred labels."""
from concurrent.futures import ProcessPoolExecutor
import io
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from neurasign_engine.causal_data import source_manifest,RawSignalUnpickler
from neurasign_engine.data import verified_bytes
from neurasign_engine.external_labeled import native_intervals
from neurasign_engine.transfer_training import sha,write_json


def process(item):
    person,session,records=item;source,manifest=source_manifest(ROOT)
    raw=[];errors=[]
    for path in (source/'UNIVERSE'/person/session/'Raw').rglob('BVP.csv'):
        try:
            lines=verified_bytes(path,source,manifest).decode().splitlines()
            origin=float(lines[0].split(',')[0]);rate=float(lines[1].split(',')[0]);assert rate==64
            values=np.loadtxt(io.StringIO('\n'.join(lines[2:])),delimiter=',').reshape(-1)
            ibipath=path.with_name('IBI.csv');lines=verified_bytes(ibipath,source,manifest).decode().splitlines()
            ibiorigin=float(lines[0].split(',')[0])
            ibi=np.loadtxt(io.StringIO('\n'.join(lines[1:])),delimiter=',',ndmin=2)
            if ibi.shape[1]!=2 or not np.isfinite(ibi).all() or np.any(np.diff(ibi[:,0])<=0):raise ValueError('Invalid beat event order')
            raw.append((path,origin,values,ibiorigin+ibi[:,0],ibi[:,1]))
        except (ValueError,AssertionError,FileNotFoundError) as e:
            errors.append({'member':str(path.relative_to(source)),'reason':type(e).__name__})
    result=[];alignment=[]
    windows=pd.read_csv(ROOT/'data/prepared/transfer-v1/universe.csv.gz')
    windows=windows[(windows.participant==person)&(windows.session==session)]
    for record in records:
        group=windows[windows.unit_id==record['unit_id']]
        if not len(group):continue
        path=source/record['segment']/'e4_BVP.pickle'
        seq=np.asarray(RawSignalUnpickler(io.BytesIO(verified_bytes(path,source,manifest))).load(),float)
        matches=[]
        # Require three distant four-second waveform blocks, including the end.
        for rawpath,origin,values,times,intervals in raw:
            for start in np.flatnonzero(np.isclose(values,seq[0],atol=1e-7,rtol=0)):
                if start+len(seq)>len(values):continue
                locations=[0,max(0,len(seq)//2-128),max(0,len(seq)-256)]
                if all(np.allclose(values[start+k:start+k+256],seq[k:k+256],rtol=0,atol=1e-7) for k in locations):
                    matches.append((rawpath,origin+start/64-record['origin'],times,intervals))
        if len(matches)!=1:
            alignment.append({'unit_id':record['unit_id'],'status':'ambiguous_or_no_waveform_match','matches':len(matches)})
            continue
        rawpath,offset,times,intervals=matches[0]
        alignment.append({'unit_id':record['unit_id'],'status':'verified_three_waveform_blocks',
                          'source_bvp':str(rawpath.relative_to(source)),'clock_offset_seconds':offset})
        for index,row in group.iterrows():
            result.append({'index':int(index),**native_intervals(times,intervals,float(row.source_end+offset))})
    return result,alignment,errors


def main():
    data=pd.read_csv(ROOT/'data/prepared/transfer-v1/universe.csv.gz')
    provenance=json.loads((ROOT/'data/prepared/causal-v3/provenance.json').read_text())
    groups={}
    for row in provenance:groups.setdefault((row['participant'],row['session']),[]).append(row)
    rows=[];alignment=[];errors=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,(r,a,e) in enumerate(pool.map(process,[(p,s,g) for (p,s),g in groups.items()])):
            rows.extend(r);alignment.extend(a);errors.extend(e)
            if i%10==0:print(json.dumps({'sessions':i+1,'aligned_windows':len(rows)}),flush=True)
    cols=['native_rmssd_ms','native_sdnn_ms','native_pnn50','native_coverage']
    output=pd.DataFrame(np.nan,index=np.arange(len(data)),columns=cols)
    native=pd.DataFrame(rows).set_index('index');output.loc[native.index,cols]=native[cols]
    path=ROOT/'data/prepared/transfer-v1/universe-native.csv.gz';output.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
    report={'windows':len(data),'waveform_aligned_windows':len(native),'usable_native_variability_windows':int(output.native_rmssd_ms.notna().sum()),
            'alignment':alignment,'source_exclusions':errors,'output_sha256':sha(path),'code_sha256':sha(__file__),
            'base_table_sha256':sha(ROOT/'data/prepared/transfer-v1/universe.csv.gz'),
            'limitations':['Manufacturer PPG intervals are not independent ECG truth.','Missing and gapped beat data stay absent.','No held-out UNIVERSE participant loaded.']}
    write_json(path.with_name('universe-native-audit.json'),report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['alignment','source_exclusions']}),flush=True)


if __name__=='__main__':main()
