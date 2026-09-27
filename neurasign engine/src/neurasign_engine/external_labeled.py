"""Mobile CogLoad import and gap-safe beat-interval summaries.

Only task questionnaire labels are imported. Their repeated window values are
weak supervision, not measured instantaneous mental state.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .causal import Trace
from .transfer_features import extract, add_history, FEATURES
from .transfer_training import sha,write_json


def native_intervals(times, intervals, end):
    times=np.asarray(times,float);intervals=np.asarray(intervals,float)
    inside=(times>=end-60)&(times<end);t=times[inside];rr=intervals[inside]
    result={'native_rmssd_ms':np.nan,'native_sdnn_ms':np.nan,'native_pnn50':np.nan,'native_coverage':0.}
    if len(t)<2:return result
    valid=np.isfinite(rr)&(rr>=.3)&(rr<=2)
    coverage=min(1.,float(rr[valid].sum()/60));result['native_coverage']=coverage
    adjacent=valid[1:]&valid[:-1]&(np.abs(np.diff(t)-rr[1:])<=np.maximum(.08,.15*rr[1:]))
    # Never join separated runs before differencing; no interpolation across gaps.
    if valid.sum()<20 or coverage<.8 or valid.mean()<.8 or np.diff(np.r_[end-60,t,end]).max()>5:return result
    differences=np.diff(rr)[adjacent]*1000
    if len(differences)<10:return result
    result.update(native_rmssd_ms=float(np.sqrt(np.mean(differences**2))),
                  native_sdnn_ms=float(np.std(rr[valid]*1000,ddof=1)),
                  native_pnn50=float((abs(differences)>50).mean()))
    return result


def resistance_to_conductance(values):
    """Microsoft Band SDK reports kOhm; 1000/kOhm = microSiemens."""
    x=np.asarray(values,float)
    return np.divide(1000.,x,out=np.full_like(x,np.nan),where=np.isfinite(x)&(x>0))


def read_mobile(path):
    header=path.read_text(encoding='utf-8-sig').splitlines()[0]
    return pd.read_csv(path,sep=';' if ';' in header else ',',encoding='utf-8-sig')


def prepare_mobile(root):
    source=root/'data/external/mobile_cogload';base=next((source/'extracted').iterdir())/'data'
    split=json.loads((root/'experiments/008-mobile-split.json').read_text())
    manifest=json.loads((source/'manifest.json').read_text())
    for f in manifest['files']:
        if sha(source/'extracted'/f['member'])!=f['sha256']:raise ValueError('Changed source '+f['member'])
    frames={'development':[],'test':[]};audit=[]
    for group in frames:
        for person in split[group]:
            if not (base/(person+'_vprasalnik.csv')).exists():
                audit.append({'group':group,'source_id':person,'windows_retained':0,'reason':'No questionnaire file in published archive'})
                continue
            table=read_mobile(base/(person+'_meritve.csv'));label=read_mobile(base/(person+'_vprasalnik.csv'))
            assert set(table.kodaUporabnika.astype(str))=={person}
            table['time']=pd.to_datetime(table.lokalniCas,utc=True,format='mixed').astype('int64')/1e9
            table=table.sort_values('time').drop_duplicates('time')
            rrpath=base/(person+'_rrInterval.csv');rr=read_mobile(rrpath) if rrpath.exists() else pd.DataFrame()
            if len(rr):
                rr['time']=pd.to_datetime(rr.lokalniCas,utc=True,format='mixed').astype('int64')/1e9
                rr=rr.sort_values('time').drop_duplicates('time')
            keys=['idEksperimenta','fazaEksperimenta','zaporedniDelEksperimenta']
            assert not label.duplicated(keys).any()
            labels={tuple(k):g.iloc[0] for k,g in label.groupby(keys)}
            rows=[];considered=0
            for key,block in table.groupby(keys,sort=True):
                if tuple(key) not in labels:continue
                t=block.time.to_numpy(float);rating=labels[tuple(key)]
                hr=block.srcniUtrip.to_numpy(float)
                hr[(block.srcniUtripKvaliteta!='LOCKED').to_numpy()|(hr<30)|(hr>220)]=np.nan
                traces={'heart_rate':Trace(t,hr,1,'bpm'),
                        'eda':Trace(t,resistance_to_conductance(block.prevodnostKoze),1,'uS'),
                        'temperature':Trace(t,block.temperaturaKoze.to_numpy(float),1,'degC')}
                beats=rr
                for column,value in zip(keys,key):
                    if len(beats):beats=beats[beats[column]==value]
                for end in np.arange(t[0]+60,t[-1]+1,10):
                    considered+=1;f=extract(traces,float(end))
                    if len(beats):
                        native=native_intervals(beats.time,beats.rrInterval,end)
                        f['pulse_interval_rmssd_ms']=native['native_rmssd_ms']
                        f['pulse_interval_sdnn_ms']=native['native_sdnn_ms']
                        f['pulse_interval_pnn50']=native['native_pnn50']
                    if not any(np.isfinite(f[n]) for n in ['heart_rate_mean','eda_mean','temperature_mean']):continue
                    targets={}
                    for target,col in [('mental_demand','mental_demand'),('physical_demand','physical_demand'),
                                       ('temporal_demand','temporal_demand'),('effort','effort'),('perceived_performance','performance')]:
                        value=float(rating[col])
                        if not 0<=value<=20:raise ValueError('Rating outside documented slider encoding')
                        targets[target]=value*5
                    rows.append({**f,**targets,'mental_effort':np.nan,'participant':'mobile:'+person,
                      'session':str(key[0]),'unit_id':'mobile:'+person+':'+':'.join(map(str,key)),
                      'source_end':float(end),'window_end':float(end-t[0]),'dataset':'mobile'})
            frames[group].extend(rows)
            audit.append({'group':group,'source_id':person,'sessions':int(table.idEksperimenta.nunique()),
                          'windows_considered':considered,'windows_retained':len(rows),'native_event_file':rrpath.exists()})
    output=root/'data/prepared/transfer-v1'
    for group,rows in frames.items():
        d=add_history(pd.DataFrame(rows));d.to_csv(output/('mobile_'+group+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
    report={'pooling_permitted':True,'pooled_targets':['mental_demand','physical_demand','temporal_demand','effort'],
      'questionnaire_mapping':'Four NASA-TLX dimensions: exported slider 0..20 mapped linearly to 0..100. Thesis Fig 4.4a shows 21 positions; development endpoints are 0 and 20. Cross-study measurement equivalence is still an assumption, tested rather than asserted.',
      'performance':'Kept source-specific. Direction equivalence with UNIVERSE not verified.',
      'identity':'Exporter supplies 36 user codes. Thesis p12 describes a unique user-entered ID. Publication describes 23 people; export-to-publication count difference unresolved. Report held-out codes and do not assert independently verified identities.',
      'eda_units':'Band SDK: resistance kOhm; conductance uS = 1000/resistance. The original column is misleadingly named skin conductivity.',
      'temperature':'Stored once/second; thesis states sensor updates once/10 seconds. Repeated values retained, not interpreted as independent temperature observations.',
      'rr':'Native event CSV only. The repeated last-value column in the 1-Hz table is never used for HRV.',
      'sources':['https://gitlab.fri.uni-lj.si/lrk/mobile-cogload-dataset','https://repozitorij.uni-lj.si/IzpisGradiva.php?id=110571',
                 'https://www.scribd.com/document/353279939/Microsoft-Band-Sdk'],
      'excluded':['game difficulty','taps','game score','personality','frustration','composite TLX'],
      'recordings':audit,'manifest_sha256':sha(source/'manifest.json'),'split_sha256':sha(root/'experiments/008-mobile-split.json'),
      'outputs':{g:sha(output/('mobile_'+g+'.csv.gz')) for g in frames},'code_sha256':sha(__file__)}
    write_json(output/'mobile-audit.json',report)
    print(json.dumps({'mobile_prepared':{g:len(rows) for g,rows in frames.items()},'heldout_targets_not_summarized':True}),flush=True)
