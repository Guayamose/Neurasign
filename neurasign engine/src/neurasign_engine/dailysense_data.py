"""DailySense wrist-only summaries aligned to the scheduled Tokyo fatigue survey.

Reads each complete nested recording once, including from growing ZIP prefixes.
No survey outcome, identity or other psychological answer becomes a predictor.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile
import zlib
import numpy as np
import pandas as pd

SIGNALS = ['hr_mean','hr_std','eda_mean','eda_std','temperature_mean','temperature_std',
           'bvp_std','bvp_range','motion_mean','motion_std','motion_enmo',
           'ibi_mean_ms','ibi_sdnn_ms','ibi_rmssd_ms']
STATS = ['mean','std','p10','p50','p90']
BASE_FEATURES = [period+'__'+channel+'__'+stat for period in ['day','last60'] for channel in SIGNALS for stat in STATS]
PROFILES = {
    'cardiac_day':[f for f in BASE_FEATURES if f.startswith('day__') and f.split('__')[1].startswith(('hr_','ibi_','bvp_'))],
    'autonomic_day':[f for f in BASE_FEATURES if f.startswith('day__') and not f.split('__')[1].startswith('motion_')],
    'all_day':[f for f in BASE_FEATURES if f.startswith('day__')],
    'day_last_hour':list(BASE_FEATURES),
    'with_history':list(BASE_FEATURES)+[f+'__past7_delta' for f in BASE_FEATURES],
}


def sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as handle:
        for block in iter(lambda:handle.read(8*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')


def member_bytes(path,member,allow_crc_mismatch=False):
    """Read a complete stored/deflated member and verify local name, size and CRC.

    Equivalent checks to scripts/download_universe.extract_member, without that
    script's unavailable requests dependency. None means the prefix is incomplete.
    """
    with open(path,'rb') as handle:
        handle.seek(member['header_offset']);header=handle.read(30)
        if len(header)<30:
            return None
        signature,version,flags,method,mtime,mdate,crc,compressed,size,names,extra=struct.unpack('<4s5H3I2H',header)
        if signature!=b'PK\x03\x04' or flags&1:
            raise ValueError('Invalid/encrypted local ZIP header')
        name=handle.read(names)
        if len(name)<names:
            return None
        if name.decode('utf-8' if flags&0x800 else 'cp437')!=member['member']:
            raise ValueError('ZIP filename differs from source index')
        handle.seek(extra,1);payload=handle.read(member['compressed_bytes'])
    if len(payload)!=member['compressed_bytes']:
        return None
    if method==0:
        result=payload
    elif method==8:
        decoder=zlib.decompressobj(-15);result=decoder.decompress(payload,member['bytes']+1)
        if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError('Invalid compressed member')
    else:
        raise ValueError('Unsupported ZIP compression')
    if len(result)!=member['bytes'] or (not allow_crc_mismatch and f'{zlib.crc32(result):08x}'!=member['crc32']):
        raise ValueError('Nested archive failed source CRC/size verification')
    return result


def minute_statistics(values,start,rate):
    """Native samples grouped into UTC minutes, requiring at least 30s coverage."""
    values=np.asarray(values,float);buckets=np.floor((start%60+np.arange(len(values))/rate)/60).astype(int)
    finite=np.isfinite(values);size=int(buckets[-1])+1 if len(buckets) else 0
    count=np.bincount(buckets[finite],minlength=size)
    total=np.bincount(buckets[finite],weights=values[finite],minlength=size)
    square=np.bincount(buckets[finite],weights=values[finite]**2,minlength=size)
    mean=np.divide(total,count,out=np.full(size,np.nan),where=count>0)
    variance=np.divide(square,count,out=np.full(size,np.nan),where=count>0)-mean**2
    low=np.full(size,np.inf);high=np.full(size,-np.inf)
    np.minimum.at(low,buckets[finite],values[finite]);np.maximum.at(high,buckets[finite],values[finite])
    invalid=count<30*rate
    mean[invalid]=np.nan;variance[invalid]=np.nan;span=high-low;span[invalid]=np.nan
    return pd.DataFrame({'minute':np.arange(size)+int(np.floor(start/60)),
                         'mean':mean,'std':np.sqrt(np.maximum(variance,0)),'range':span})


def regular_signal(payload,axes=False):
    stream=io.BytesIO(payload)
    first=stream.readline().decode();second=stream.readline().decode()
    start=float(first.split(',')[0]);rate=float(second.split(',')[0])
    if not np.isfinite(start) or not 0<rate<=1000:
        raise ValueError('Invalid E4 signal header')
    remaining=stream.read()
    if axes:
        values=np.loadtxt(io.BytesIO(remaining),delimiter=',',ndmin=2)/64.
        if values.shape[1]!=3:
            raise ValueError('E4 accelerometer must have three axes')
    else:
        values=np.fromstring(remaining.decode(),sep='\n')
    return start,rate,values


def summarize_recording(raw,return_audit=False):
    """Return one sensor-only feature row per UTC minute from a nested E4 ZIP."""
    parts=[];channel_audit=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names={Path(name).name:name for name in archive.namelist() if not name.endswith('/')}
        def checked_read(filename):
            try:
                payload=archive.read(names[filename])
            except (zipfile.BadZipFile,zlib.error,EOFError,RuntimeError) as error:
                channel_audit.append({'channel':filename,'accepted':False,'reason':str(error)})
                return None
            channel_audit.append({'channel':filename,'accepted':True,'crc32_verified':True,'bytes':len(payload)})
            return payload
        for filename,channel in [('HR.csv','hr'),('EDA.csv','eda'),('TEMP.csv','temperature'),('BVP.csv','bvp'),('ACC.csv','motion')]:
            if filename not in names:
                continue
            payload=checked_read(filename)
            if payload is None or not payload.strip():
                continue
            start,rate,values=regular_signal(payload,filename=='ACC.csv')
            if filename=='ACC.csv':
                values=np.linalg.norm(values,axis=1)
            if filename=='HR.csv':
                values[(values<30)|(values>220)]=np.nan
            elif filename=='EDA.csv':
                values[(values<0)|(values>100)]=np.nan
            elif filename=='TEMP.csv':
                values[(values<10)|(values>45)]=np.nan
            summary=minute_statistics(values,start,rate)
            keep={'minute':'minute','mean':channel+'_mean','std':channel+'_std'}
            if channel=='bvp':
                keep={'minute':'minute','std':'bvp_std','range':'bvp_range'}
            current=summary[list(keep)].rename(columns=keep)
            if channel=='motion':
                current['motion_enmo']=minute_statistics(np.maximum(values-1,0),start,rate)['mean']
            parts.append(current.set_index('minute'))
        if 'IBI.csv' in names:
            payload=checked_read('IBI.csv')
            stream=io.BytesIO(payload if payload is not None else b'');header=stream.readline().decode()
            body=stream.read().strip()
            if header.strip() and body:
                start=float(header.split(',')[0])
                values=np.loadtxt(io.BytesIO(body),delimiter=',',ndmin=2)
                if values.shape[1]!=2:
                    raise ValueError('Invalid native IBI columns')
                times=start+values[:,0];interval=values[:,1]*1000
                valid=np.isfinite(interval)&(interval>=300)&(interval<=2000)
                differences=np.r_[np.nan,np.diff(interval)]
                adjacent=valid&np.r_[False,valid[:-1]]&np.r_[False,(np.diff(times)>0)&(np.diff(times)<=2.2)]
                records=[];buckets=np.floor(times/60).astype(int)
                order=np.argsort(buckets,kind='stable')
                groups=np.split(order,np.flatnonzero(np.diff(buckets[order]))+1)
                for selected in groups:
                    minute=buckets[selected[0]];good=selected[valid[selected]];paired=selected[adjacent[selected]]
                    records.append({'minute':int(minute),
                        'ibi_mean_ms':float(interval[good].mean()) if len(good)>=20 else np.nan,
                        'ibi_sdnn_ms':float(interval[good].std(ddof=1)) if len(good)>=20 else np.nan,
                        'ibi_rmssd_ms':float(np.sqrt(np.mean(differences[paired]**2))) if len(paired)>=10 else np.nan})
                parts.append(pd.DataFrame(records).set_index('minute'))
    if not parts:
        result=pd.DataFrame(columns=['minute',*SIGNALS])
        return (result,channel_audit) if return_audit else result
    frame=pd.concat(parts,axis=1).reindex(columns=SIGNALS)
    frame.index.name='minute'
    # Native wrist IBI variability is uninterpretable under high movement.
    high_motion=frame.motion_std>=.2
    frame.loc[high_motion,['ibi_mean_ms','ibi_sdnn_ms','ibi_rmssd_ms']]=np.nan
    result=frame.reset_index()
    return (result,channel_audit) if return_audit else result


def inventory(root):
    source=root/'data/external/dailysense';result=[]
    for index in sorted(source.glob('term*_data.zip.index.json')):
        archive_name=index.name.removesuffix('.index.json')
        completed=source/archive_name;partial=source/(archive_name+'.part')
        archive=completed if completed.exists() else partial
        for member in json.loads(index.read_text()):
            if '/rawdata/physio/' not in member['member'] or not member['member'].endswith('.zip'):
                continue
            item={**member,'archive':str(archive),'archive_name':archive_name,
                  'participant':'S'+member['member'].split('/rawdata/physio/')[1].split('/')[0]}
            item['cache_key']=hashlib.sha256((archive_name+'::'+member['member']).encode()).hexdigest()[:24]
            result.append(item)
    if not result:
        raise ValueError('DailySense source index has no physiological recordings')
    return result


def cache_available(root):
    directory=root/'data/prepared/dailysense-v1/recording_minutes';directory.mkdir(parents=True,exist_ok=True)
    items=inventory(root);completed=0;created=0;rejected=[];code=sha(Path(__file__))
    for item in items:
        path=directory/(item['cache_key']+'.csv.gz');meta=directory/(item['cache_key']+'.json')
        quarantine=directory/(item['cache_key']+'.rejected.json')
        if quarantine.exists():
            rejected.append(json.loads(quarantine.read_text()));continue
        if path.exists() and meta.exists():
            prior=json.loads(meta.read_text())
            if prior['code_sha256']!=code or prior['member_crc32']!=item['crc32'] or sha(path)!=prior['prepared_sha256']:
                raise ValueError('Cached sensor preparation provenance changed')
            completed+=1;continue
        archive=Path(item['archive'])
        if not archive.exists() or archive.stat().st_size<item['header_offset']+30+item['compressed_bytes']:
            continue
        try:
            # A published outer archive contains many damaged inner streams. The
            # nested envelope CRC may fail; every accepted CSV must independently
            # pass its own decompression/CRC. Final preparation checks outer MD5.
            raw=member_bytes(archive,item,allow_crc_mismatch=True)
            frame,channels=summarize_recording(raw,return_audit=True) if raw is not None else (None,[])
        except (ValueError,zipfile.BadZipFile,zlib.error) as error:
            record={'member':item['member'],'participant':item['participant'],'reason':str(error),
                    'source_member_crc32':item['crc32'],'status':'quarantined_no_features_used',
                    'code_sha256':code}
            save(quarantine,record);rejected.append(record)
            print(json.dumps({'dailysense_quarantined':item['member'],'reason':str(error)}),flush=True)
            continue
        if raw is None:
            continue
        frame.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        save(meta,{'participant':item['participant'],'member':item['member'],'member_crc32':item['crc32'],
                   'raw_nested_sha256':hashlib.sha256(raw).hexdigest(),'code_sha256':code,'prepared_sha256':sha(path),'minutes':len(frame),
                   'actual_nested_crc32':f'{zlib.crc32(raw):08x}','outer_member_crc_matches':f'{zlib.crc32(raw):08x}'==item['crc32'],
                   'channels':channels})
        completed+=1;created+=1
        if created%10==0:
            print(json.dumps({'dailysense_cached':completed,'total_recordings':len(items)}),flush=True)
    result={'cached_recordings':completed,'total_recordings':len(items),'created':created,
            'quarantined_recordings':len(rejected),'quarantine':rejected,'complete':completed+len(rejected)==len(items)}
    save(root/'data/prepared/dailysense-v1/cache-status.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='quarantine'}),flush=True);return result


def verify_archives(root):
    """Final preparation requires the complete, publisher-verified source bytes."""
    source=root/'data/external/dailysense';metadata=json.loads((source/'metadata.json').read_text());verified=[]
    for item in metadata['files']:
        if not item['key'].endswith('.zip'):
            continue
        path=source/item['key']
        if not path.exists() or path.stat().st_size!=item['size']:
            raise ValueError('Complete DailySense source archives are required before final preparation')
        algorithm,expected=item['checksum'].split(':',1);digest=hashlib.new(algorithm)
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(8*1024*1024),b''):
                digest.update(block)
        if digest.hexdigest()!=expected:
            raise ValueError('DailySense full archive publisher checksum mismatch')
        verified.append({'archive':item['key'],'publisher_checksum':item['checksum'],'bytes':item['size']})
        index=json.loads((source/(item['key']+'.index.json')).read_text())
        for member in index:
            if member['member'].endswith('/rawdata/questionnaire/project_DRM.csv') or '/user_table_term' in member['member']:
                raw=member_bytes(path,member)
                if raw!=(source/'inspection'/member['member']).read_bytes():
                    raise ValueError('Inspected fatigue labels/person mapping differ from verified source archive')
    return verified


def labels(root):
    source=root/'data/external/dailysense/inspection';parts=[];audit=[]
    for table in sorted(source.glob('term*_data/user_table_term*.csv')):
        users=pd.read_csv(table,usecols=['user_id','exkuma_roaming_id'])
        if users.user_id.duplicated().any() or users.exkuma_roaming_id.duplicated().any():
            raise ValueError('Ambiguous source person mapping')
        answers=pd.read_csv(table.parent/'rawdata/questionnaire/project_DRM.csv',usecols=['SignalDate','RoamingID','ID','drm_vas1'])
        answers=answers.merge(users,left_on='RoamingID',right_on='exkuma_roaming_id',how='left',validate='many_to_one')
        if answers.user_id.isna().any():
            raise ValueError('Questionnaire person has no source mapping')
        timestamp=pd.to_datetime(answers.SignalDate,format='mixed',errors='raise').dt.tz_localize('Asia/Tokyo')
        if not ((timestamp.dt.hour==21)&(timestamp.dt.minute==30)).all():
            raise ValueError('Daily survey timestamp differs from scheduled 21:30')
        answers['participant']='S'+answers.user_id.astype(int).astype(str)
        answers['date']=timestamp.dt.strftime('%Y-%m-%d');answers['cutoff_seconds']=timestamp.astype('int64')/1e9
        answers['day_start_seconds']=(timestamp.dt.normalize().astype('int64')/1e9)
        answers['rating']=pd.to_numeric(answers.drm_vas1,errors='coerce')
        answers['unit_id']=answers.participant+'_'+answers.date
        valid=answers.rating.between(0,100)
        audit.append({'term':table.parent.name,'source_answers':len(answers),'missing_or_invalid_rating':int((~valid).sum())})
        answers=answers[valid].copy()
        if answers.unit_id.duplicated().any():
            raise ValueError('Multiple daily fatigue answers for a person/date require explicit resolution')
        parts.append(answers[['participant','date','unit_id','rating','day_start_seconds','cutoff_seconds']])
    return pd.concat(parts,ignore_index=True),audit


def summarize_day(minutes,start,end):
    """Only fully preceding UTC minutes; survey cutoff never enters predictors."""
    evidence=minutes[(minutes.minute*60>=start)&((minutes.minute+1)*60<=end)].copy()
    observed=pd.DataFrame({'hr':evidence.hr_mean.notna(),'eda':evidence.eda_mean.notna(),
        'temperature':evidence.temperature_mean.notna(),'bvp':evidence.bvp_std.notna()&(evidence.bvp_std>1e-9),
        'motion':evidence.motion_std.notna(),'ibi':evidence.ibi_mean_ms.notna()})
    good=(observed.sum(axis=1)>=3)&(observed.hr|observed.bvp)&(observed.eda|observed.temperature)
    available=int(good.sum());features={}
    for period,left in [('day',start),('last60',end-3600)]:
        block=evidence[evidence.minute*60>=left]
        for channel in SIGNALS:
            values=block[channel].dropna().to_numpy(float)
            stats=[float(values.mean()),float(values.std()),*np.quantile(values,[.1,.5,.9]).tolist()] if len(values)>=5 else [np.nan]*5
            features.update({period+'__'+channel+'__'+stat:value for stat,value in zip(STATS,stats)})
    return features,available,len(evidence)


def add_history(frame):
    frame=frame.sort_values(['participant','date']).copy()
    extra=pd.DataFrame(np.nan,index=frame.index,columns=[name+'__past7_delta' for name in BASE_FEATURES])
    frame=pd.concat([frame,extra],axis=1)
    for _,person in frame.groupby('participant'):
        indexed=person.set_index(pd.to_datetime(person.date))
        baseline=indexed[BASE_FEATURES].rolling('7D',closed='left',min_periods=2).median()
        frame.loc[person.index,[f+'__past7_delta' for f in BASE_FEATURES]]=(indexed[BASE_FEATURES]-baseline).to_numpy()
    return frame


def prepare(root):
    status=cache_available(root)
    if not status['complete']:
        raise ValueError('DailySense source members are incomplete; final study cohort must wait for all recordings')
    verified=verify_archives(root)
    outcomes,label_audit=labels(root);directory=root/'data/prepared/dailysense-v1/recording_minutes'
    items=inventory(root);rows=[];audit=[];overlap=0
    for person,answers in outcomes.groupby('participant'):
        parts=[pd.read_csv(directory/(item['cache_key']+'.csv.gz')) for item in items
               if item['participant']==person and (directory/(item['cache_key']+'.csv.gz')).exists()]
        if not parts:
            audit.append({'participant':person,'status':'no_recordings','answers':len(answers)});continue
        minutes=pd.concat(parts,ignore_index=True)
        minutes['_coverage']=minutes[SIGNALS].notna().sum(axis=1)
        overlap+=int(minutes.minute.duplicated().sum())
        minutes=minutes.sort_values('_coverage',kind='stable').drop_duplicates('minute',keep='last').sort_values('minute')
        # Build every recorded calendar day, including days without a questionnaire, for causal sensor baselines.
        dates=pd.to_datetime(minutes.minute*60,unit='s',utc=True).dt.tz_convert('Asia/Tokyo').dt.strftime('%Y-%m-%d').unique()
        day_rows=[]
        for date in sorted(dates):
            start=pd.Timestamp(date,tz='Asia/Tokyo').timestamp();end=start+21.5*3600
            features,valid,total=summarize_day(minutes,start,end)
            audit.append({'participant':person,'date':date,'valid_minutes':valid,'recorded_minutes':total,'accepted':valid>=60})
            if valid>=60:
                day_rows.append({'participant':person,'date':date,**features})
        if day_rows:
            daily=add_history(pd.DataFrame(day_rows))
            joined=answers.merge(daily,on=['participant','date'],how='inner',validate='one_to_one')
            if len(joined)>=5:
                rows.append(joined)
            else:
                audit.append({'participant':person,'status':'fewer_than_five_paired_answers','paired_answers':len(joined)})
    if not rows:
        raise ValueError('No eligible DailySense answers')
    frame=pd.concat(rows,ignore_index=True).sort_values(['participant','date']).reset_index(drop=True)
    frame['row_id']=np.arange(len(frame));frame=frame.drop(columns=['day_start_seconds','cutoff_seconds'])
    out=root/'data/prepared/dailysense-v1';path=out/'answers.csv.gz'
    frame.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
    save(out/'profiles.json',PROFILES)
    report={'people':int(frame.participant.nunique()),'answers':len(frame),'label_audit':label_audit,'source_day_inventory':audit,
        'overlapping_minutes_resolved_by_channel_availability':overlap,'recording_cache':status,'prepared_sha256':sha(path),
        'publisher_verified_archives':verified,
        'feature_profiles':PROFILES,'feature_availability':frame[PROFILES['with_history']].notna().mean().to_dict(),
        'feature_extraction_code_sha256':sha(Path(__file__)),
        'target':'Original drm_vas1 daily fatigue VAS 0–100; scheduled SignalDate in Asia/Tokyo, no outcome reassignment to delayed answer day',
        'cutoff':'Features only from fully preceding minutes on SignalDate before 21:30 Tokyo; previous-seven-day history excludes current day',
        'source_reference':'https://zenodo.org/records/10816004','license':'CC BY 4.0',
        'quality':'At least 60 minutes with three observed channels including HR or BVP and EDA or temperature; at least five paired answers per person. Native-channel minutes require >=30 seconds samples; IBI requires >=20 valid beats.',
        'integrity_policy':'Complete outer archives must match publisher MD5. Each accepted CSV must pass its own CRC and decompression; damaged channels are missing, never reconstructed. Outer nested envelope CRC mismatches are recorded because published archives contain damaged inner streams.',
        'ibi_quality':'IBI variability excluded when observed motion standard deviation >=0.2g; with missing acceleration, native IBI is retained without a motion-quality claim.',
        'excluded':'All other questionnaires, demographics, phase/task/time/identity predictors; no target history',
        'source_index_sha256':{p.name:sha(p) for p in (root/'data/external/dailysense').glob('*.index.json')}}
    save(out/'audit.json',report)
    print(json.dumps({'prepared':str(path.relative_to(root)),'people':report['people'],'answers':report['answers']}),flush=True)
    return frame,report
