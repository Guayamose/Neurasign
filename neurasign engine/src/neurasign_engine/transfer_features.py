"""Portable past-only feature profiles and source-preserving personal references."""
from __future__ import annotations
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, sosfilt, sosfilt_zi, welch

from .causal import Trace, statistics, window_samples, pulse_filter

STATS = ["mean", "std", "range", "slope_per_second", "last20_minus_first20"]
FEATURES = [f"{signal}_{stat}" for signal in ("eda", "temperature", "heart_rate", "motion") for stat in STATS] + [
    "pulse_rate_bpm", "pulse_interval_sdnn_ms", "pulse_interval_rmssd_ms", "pulse_interval_pnn50",
    "bvp_periodicity", "bvp_spectral_concentration", "motion_enmo_mean_g", "acc_clipped_fraction"]
PROFILES = {
    "ppg": ["pulse_rate_bpm", "pulse_interval_sdnn_ms", "pulse_interval_rmssd_ms", "pulse_interval_pnn50", "bvp_periodicity", "bvp_spectral_concentration"],
    "summary": ["heart_rate_mean", "pulse_interval_rmssd_ms", "pulse_interval_sdnn_ms"] + [f"eda_{s}" for s in STATS],
    "ppg_eda": ["pulse_rate_bpm", "pulse_interval_sdnn_ms", "pulse_interval_rmssd_ms", "pulse_interval_pnn50", "bvp_periodicity", "bvp_spectral_concentration"] + [f"eda_{s}" for s in STATS],
    "all": FEATURES,
}


def e4_csv(path, unit, scale=1.):
    lines = path.read_text().splitlines()
    origin = float(lines[0].split(",")[0]); rate = float(lines[1].split(",")[0])
    values = np.loadtxt(io.StringIO("\n".join(lines[2:])), delimiter=",", ndmin=2)
    times = origin + np.arange(len(values))/rate
    return [Trace(times, values[:, i]*scale, rate, unit) for i in range(values.shape[1])]


def e4_folder(folder):
    traces = {}
    for name, filename, unit in (("bvp", "BVP.csv", "au"), ("eda", "EDA.csv", "uS"),
                                 ("temperature", "TEMP.csv", "degC"), ("heart_rate", "HR.csv", "bpm")):
        path = folder / filename
        if path.exists():
            traces[name] = e4_csv(path, unit)[0]
    if (folder / "ACC.csv").exists():
        for name, trace in zip(("acc_x", "acc_y", "acc_z"), e4_csv(folder / "ACC.csv", "g", 1/64)):
            traces[name] = trace
    return traces


def pulse_features(trace, end, motion_bad):
    t, x, q = window_samples(trace, end-60, end)
    if q["coverage"] < .95 or q["max_gap_seconds"] > .5 or q["cadence_relative_error"] > .1 or len(x) < 100 or np.std(x) < 1e-8:
        return {}
    sos = pulse_filter(trace.rate)
    x, _ = sosfilt(sos, x, zi=sosfilt_zi(sos)*x[0]); x=x[int(2*trace.rate):];t=t[int(2*trace.rate):]
    freqs, power=welch(x, fs=trace.rate, nperseg=min(len(x),int(8*trace.rate)))
    band=(freqs>=.5)&(freqs<=4);peak=int(np.argmax(np.where(band,power,-1)))
    lag=int(round(trace.rate/max(freqs[peak],.5)));centered=x-x.mean()
    periodicity=float(np.dot(centered[lag:],centered[:-lag])/max(np.linalg.norm(centered[lag:])*np.linalg.norm(centered[:-lag]),1e-12))
    result={"bvp_periodicity":periodicity,"bvp_spectral_concentration":min(1.,float(power[abs(freqs-freqs[peak])<=.25].sum()/max(power[band].sum(),1e-12)))}
    peaks,_=find_peaks(x,distance=max(1,int(.3*trace.rate)),prominence=max(x.std()*.3,1e-9))
    rr=np.diff(t[peaks])*1000;valid=(rr>=300)&(rr<=2000)
    if valid.sum()<20 or valid.mean()<.8 or periodicity<.2 or motion_bad:
        return result
    v=rr[valid];diff=np.diff(rr)[valid[1:]&valid[:-1]]
    result.update(pulse_rate_bpm=float(60000/np.median(v)),pulse_interval_sdnn_ms=float(v.std(ddof=1)))
    if len(diff)>=10:
        result.update(pulse_interval_rmssd_ms=float(np.sqrt(np.mean(diff**2))),pulse_interval_pnn50=float(np.mean(abs(diff)>50)))
    return result


def extract(traces, end):
    """Absent channels stay NaN; available channels require valid past coverage."""
    result={f:np.nan for f in FEATURES}; accepted={}
    for name, trace in traces.items():
        if name not in ("eda","temperature","heart_rate","acc_x","acc_y","acc_z"):
            continue
        t,x,q=window_samples(trace,end-60,end)
        if q["coverage"]<.95 or q["max_gap_seconds"]>max(.5,2.5/trace.rate) or q["cadence_relative_error"]>.1:
            continue
        accepted[name]=(t,x)
        if name in ("eda","temperature","heart_rate"):
            if (name=="eda" and ((x<0)|(x>100)).any()) or (name=="temperature" and ((x<10)|(x>45)).any()):
                continue
            stats=statistics(t,x,end-60,end)
            result.update({name+"_"+k:stats[k] for k in STATS})
    motion_bad=False
    if all(k in accepted for k in ("acc_x","acc_y","acc_z")):
        t=accepted["acc_x"][0]
        if all(np.array_equal(t,accepted[k][0]) for k in ("acc_y","acc_z")):
            xyz=np.column_stack([accepted[k][1] for k in ("acc_x","acc_y","acc_z")]);mag=np.linalg.norm(xyz,axis=1)
            stats=statistics(t,mag,end-60,end);result.update({"motion_"+k:stats[k] for k in STATS})
            result["motion_enmo_mean_g"]=float(np.maximum(mag-1,0).mean())
            result["acc_clipped_fraction"]=float((abs(xyz)>=1.98).any(axis=1).mean())
            motion_bad=result["motion_std"]>.2 or result["acc_clipped_fraction"]>.05
    if "bvp" in traces:
        result.update(pulse_features(traces["bvp"],end,motion_bad))
    # Explicit derived HR fallback for a shared summary profile, not a fake measured channel.
    if not np.isfinite(result["heart_rate_mean"]):
        result["heart_rate_mean"]=result["pulse_rate_bpm"]
    return result


def add_history(frame):
    """Reference = median of up to 15 earliest nonfuture windows in this session.

    Reference windows must finish before the current evidence window starts;
    each feature needs >=3 observed references. No labels or future rows enter it.
    This is an initial physiological reference, not a claimed resting baseline.
    """
    result=frame.copy()
    delta=np.full((len(frame),len(FEATURES)),np.nan)
    mapping={index:i for i,index in enumerate(frame.index)}
    for _, group in frame.groupby(["participant","session"],sort=False):
        group=group.sort_values("source_end")
        values=group[FEATURES].to_numpy(float);ends=group.source_end.to_numpy(float)
        for j,(index,row) in enumerate(group.iterrows()):
            past=values[:min(15,int(np.searchsorted(ends,row.source_end-60,side="right")))]
            if not len(past):continue
            reference=np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).sum()>=3 else np.nan for col in past.T])
            delta[mapping[index]]=values[j]-reference
    for i,f in enumerate(FEATURES):result[f+"__delta"]=delta[:,i]
    return result


def from_universe(root):
    source=pd.read_csv(root/"data/prepared/causal-v3/windows.csv.gz")
    return add_history(source[[*FEATURES,"participant","session","unit_id","window_end","source_end",
                               "mental_effort","mental_demand","physical_demand","temporal_demand","effort","perceived_performance"]])
