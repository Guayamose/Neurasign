#!/usr/bin/env python3
"""Original 76-second score, quiet editorial effects and narration-forward mix.

Uses no stock music or samples. NumPy/SciPy synthesis is deterministic; narration
is supplied by create-hospital-narration.py. All outputs use the hospital- prefix.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/audio"
RATE = 48000
SECONDS = 76
ORIGINAL_SECONDS = 60
SEED = 2026092801
BEAT = 60 / 96


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ffmpeg(*args):
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *map(str, args)], check=True, capture_output=True, text=True)
    return result.stderr


def analyze(path):
    log = ffmpeg("-i", path, "-af", "loudnorm=I=-17.5:TP=-1.8:LRA=7:print_format=json", "-f", "null", "-")
    return json.loads(re.findall(r'\{\s*"input_i".*?\}', log, re.S)[-1])


def master(raw, output, level):
    measurement = analyze(raw)
    filters = (f"loudnorm=I={level}:TP=-1.8:LRA=7:measured_I={measurement['input_i']}:"
               f"measured_TP={measurement['input_tp']}:measured_LRA={measurement['input_lra']}:"
               f"measured_thresh={measurement['input_thresh']}:offset={measurement['target_offset']}:linear=true")
    ffmpeg("-y", "-i", raw, "-af", filters, "-ar", RATE, "-ac", 2, "-c:a", "pcm_s24le", "-t", SECONDS, output)


def read(path):
    rate, pcm = wavfile.read(path)
    assert rate == RATE and pcm.shape == (RATE * SECONDS, 2)
    return pcm.astype(float) / 2 ** 31


def midi(number):
    return 440 * 2 ** ((number - 69) / 12)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def env(length, attack, release):
    t = np.arange(length) / RATE
    return smooth(t / attack) * smooth((length / RATE - t) / release)


def pan(x, position=0):
    angle = (position + 1) * np.pi / 4
    return x[:, None] * np.array([np.cos(angle), np.sin(angle)])


def add(bus, sound, start, gain=1):
    first = round(start * RATE)
    count = min(len(sound), len(bus) - first)
    if first >= 0 and count > 0:
        bus[first:first + count] += sound[:count] * gain


def noise(rng, seconds, lo, hi):
    x = rng.normal(size=round(seconds * RATE))
    x = sosfilt(butter(2, [lo, hi], btype="bandpass", fs=RATE, output="sos"), x)
    return x / max(np.std(x), 1e-12)


def piano(number, duration=2.2, soft=False):
    t = np.arange(round(duration * RATE)) / RATE
    f = midi(number)
    x = np.zeros(len(t))
    for h, a in [(1, 1), (2, .42), (3, .17), (4, .085), (5, .025)]:
        # Slight inharmonicity plus independent damping produces a felt-key body.
        x += a * np.sin(2 * np.pi * f * h * (1 + .00016 * h * h) * t) * np.exp(-t * (1.5 + h * .58))
    return x * env(len(t), .018 if soft else .009, .18)


def bass(number):
    t = np.arange(round(.56 * RATE)) / RATE
    f = midi(number)
    x = np.sin(2 * np.pi * f * t) + .18 * np.sin(4 * np.pi * f * t)
    return x * np.exp(-t * 3.2) * env(len(t), .018, .1)


def pad(number, duration, phase):
    t = np.arange(round(duration * RATE)) / RATE
    f = midi(number)
    x = (np.sin(2 * np.pi * f * .999 * t + phase) + np.sin(2 * np.pi * f * 1.0013 * t - phase)) / 2
    x += .09 * np.sin(6 * np.pi * f * t + phase)
    return x * env(len(t), .65, 1.0)


def percussion(rng, kind):
    seconds = .18 if kind == "tap" else .1
    t = np.arange(round(seconds * RATE)) / RATE
    if kind == "tap":
        x = .11 * noise(rng, seconds, 700, 4200) * np.exp(-t * 36)
        x += .26 * np.sin(2 * np.pi * 360 * t) * np.exp(-t * 65)
    else:
        x = .09 * noise(rng, seconds, 3500, 8500) * np.exp(-t * 55)
    return x * env(len(t), .003, .02)


def synthesize_original():
    rng = np.random.default_rng(SEED)
    score = np.zeros((RATE * ORIGINAL_SECONDS, 2))
    effects = np.zeros_like(score)
    # Twenty-four independently voiced bars. The composition develops through
    # an opening, minor-color arrival, enquiry, connection, focus and resolution.
    chords = [
        (50, [62,66,69,76]), (50, [62,64,69,73]),
        (47, [59,62,66,73]), (47, [59,62,66,69]), (43, [59,62,66,69]), (45, [57,62,64,69]),
        (43, [59,62,66,69]), (42, [57,62,66,69]), (40, [59,62,64,67]), (45, [57,61,64,71]),
        (50, [62,66,69,76]), (47, [59,62,66,73]), (43, [59,62,66,69]),
        (47, [59,62,66,73]), (43, [59,62,66,69]), (45, [57,62,64,69]), (45, [57,61,64,71]),
        (50, [62,66,69,76]), (42, [57,62,66,69]), (43, [59,62,66,69]),
        (50, [62,64,66,69]), (45, [57,61,64,69]), (50, [62,66,69,74]), (50, [62,64,66,69]),
    ]
    patterns = [
        [(0,0),(1.5,2),(3,1)],
        [(0,0),(.75,2),(1.5,1),(2.5,3),(3.5,2)],
        [(0,0),(1,2),(1.75,1),(2.5,3),(3.25,2)],
        [(0,0),(.5,1),(1.5,2),(2,1),(2.75,3),(3.5,2)],
    ]
    for bar, (root, voicing) in enumerate(chords):
        start = bar * 4 * BEAT
        intensity = .48 if start < 6 else .67 if start < 14 else .57 if start < 25 else .76 if start < 33 else .87 if start < 43 else .71
        if start >= 55:
            intensity = .48
        for j, number in enumerate(voicing[:-1]):
            add(score, pan(pad(number - 12, 3.35, rng.uniform(0, 6.28)), -.45 + .45 * j), start, .021 * intensity)
        pattern = patterns[0 if start < 5 else 1 if start < 14 else 2 if start < 25 else 3]
        if start >= 55:
            pattern = [(0,0),(1.5,2)]
        for k, (beat, degree) in enumerate(pattern):
            position = (-.3, .25, -.1, .35)[k % 4]
            # Alternating accents and human-scale timing offsets give momentum.
            offset = 0 if k == 0 else rng.uniform(-.009, .009)
            gain = .077 * intensity * (1 if k % 3 == 0 else .76)
            add(score, pan(piano(voicing[degree], 2.1), position), start + beat * BEAT + offset, gain)
        if 5 <= start < 55:
            for beat, pitch, strength in [(0,root,.092),(2.5,root + (7 if bar % 3 == 0 else 0),.063)]:
                add(score, pan(bass(pitch - 12)), start + beat * BEAT, strength * intensity)
        if 6 <= start < 55:
            for beat in [1, 3]:
                add(score, pan(percussion(rng, "tap"), -.08), start + beat * BEAT, .20 * intensity)
            for beat in [.5, 1.5, 2.5, 3.5]:
                add(score, pan(percussion(rng, "brush"), .24 if beat % 2 else -.24), start + beat * BEAT, .13 * intensity)
    # Fresh melodic responses at narrative changes, avoiding repeated 15 s loops.
    for start, notes in [(14,[69,66,64]), (25,[66,69,73,76]), (33,[66,69,71]), (43,[74,73,69,66]), (50,[66,69,74])]:
        for j, number in enumerate(notes):
            add(score, pan(piano(number, 2.8, soft=True), -.25 + .16 * j), start + j * .31, .027)
    for j, number in enumerate([50,57,62,66,69,76]):
        add(score, pan(piano(number, 4, soft=True), -.3 + j * .12), 56 + j * .025, .042 if j < 3 else .025)
    # Quiet designed Foley: sliding hospital door, cart texture, device handoff,
    # coordinator confirmation. No alarm, heartbeat, siren or medical monitor tone.
    for start, duration, gain in [(5.45,1.05,.012),(6.4,1.6,.005),(25.1,.55,.006),(33.0,.55,.006)]:
        n = round(duration * RATE)
        x = noise(rng, duration, 180, 1900) * np.sin(np.linspace(0,np.pi,n)) ** 2
        add(effects, pan(x, -.25 if start < 10 else .25), start, gain)
    for start in [26.0, 28.0, 30.0, 43.0, 50.2]:
        add(effects, pan(percussion(rng, "tap"), .14), start, .085)
    # A low, musical two-note confirmation rather than a high electronic beep.
    add(effects, pan(piano(62, 1), -.1), 50.15, .021)
    add(effects, pan(piano(69, 1), .1), 50.31, .015)
    reflected = score.copy()
    for delay, gain in [(.093,.13),(.177,.075),(.291,.04)]:
        shift = round(delay * RATE)
        reflected[shift:] += score[:-shift,::-1] * gain
    score = sosfilt(butter(2, 35, btype="highpass", fs=RATE, output="sos"), reflected, axis=0)
    score = np.tanh(score * 1.16) / 1.16
    timeline = np.arange(len(score)) / RATE
    fade = smooth(timeline / .25) * smooth((59.97 - timeline) / 1.0) ** 1.35
    score *= fade[:,None]
    effects *= fade[:,None]
    score[-round(.03 * RATE):] = 0
    effects[-round(.03 * RATE):] = 0
    return score, effects


def synthesize():
    """Preserve the opening; compose a new bridge and wider-workplace development.

    The old logo chord becomes the hospital-to-montage transition. Its natural
    tail overlaps fresh harmony, rather than splicing or repeating a music loop.
    A separate random stream leaves the original arrangement and Foley intact.
    """
    original_score, original_effects = synthesize_original()
    score = np.zeros((RATE * SECONDS, 2))
    effects = np.zeros_like(score)
    extension = np.zeros_like(score)
    rng = np.random.default_rng(SEED + 76)
    # Dadd9 -> Gmaj9 -> Bm9 -> Em9 -> Gmaj9 -> Asus/A -> Dadd9.
    # Six new bars broaden the palette, with changing inversions and accents.
    bars = [
        (56., 50, [62,66,69,76], .58),
        (58.5, 43, [59,62,66,69], .69),
        (61., 47, [62,66,69,73], .78),
        (63.5, 40, [59,62,66,67], .79),
        (66., 43, [62,66,69,71], .77),
        (68.5, 45, [61,64,69,74], .66),
    ]
    patterns = [
        [(0,0),(1.5,2),(2.75,1)],
        [(0,0),(.75,2),(1.5,1),(2.5,3),(3.5,2)],
        [(0,0),(.5,2),(1.5,1),(2.25,3),(3.25,2)],
        [(0,0),(1,2),(1.75,3),(2.5,1),(3.5,2)],
        [(0,0),(.75,1),(1.5,3),(2.5,2),(3.25,1)],
        [(0,0),(1.5,2),(2.5,1)],
    ]
    for bar, (start, root, voicing, intensity) in enumerate(bars):
        for j, number in enumerate(voicing[:3]):
            add(extension, pan(pad(number - 12, 3.5, rng.uniform(0, 6.28)), -.45 + .45*j), start, .021*intensity)
        for k, (beat, degree) in enumerate(patterns[bar]):
            offset = 0 if k == 0 else rng.uniform(-.008, .008)
            add(extension, pan(piano(voicing[degree], 2.4, soft=True), (-.3,.3,-.12,.2)[k%4]),
                start + beat*BEAT + offset, .077*intensity*(1 if k%3 == 0 else .78))
        for beat, strength in [(0,.092),(2.5,.063)]:
            add(extension, pan(bass(root - 12)), start + beat*BEAT, strength*intensity)
        for beat in [1,3]:
            add(extension, pan(percussion(rng,"tap"), -.08), start + beat*BEAT, .19*intensity)
        for beat in [.5,1.5,2.5,3.5]:
            add(extension, pan(percussion(rng,"brush"), .2), start + beat*BEAT, .12*intensity)
    # Sparse answering phrases let each workplace receive its own musical turn.
    for start, notes in [(60.85,[69,73,76]),(64.8,[74,71,69]),(67.85,[71,74,76])]:
        for j, number in enumerate(notes):
            add(extension, pan(piano(number,2.6,soft=True), -.25+.2*j), start+j*.31, .023)
    # A broader, longer final resolve; percussion has ended before the brand.
    for j, number in enumerate([38,50,57,62,66,69,76]):
        add(extension, pan(piano(number,4.8,soft=True), -.3+j*.1), 71+j*.025, .044 if j<4 else .025)
    for j, number in enumerate([50,57,62,66]):
        add(extension, pan(pad(number,4.8,rng.uniform(0,6.28)), -.45+j*.3), 71, .008)
    reflected = extension.copy()
    for delay, gain in [(.093,.13),(.177,.075),(.291,.04)]:
        shift = round(delay*RATE)
        reflected[shift:] += extension[:-shift,::-1]*gain
    extension = sosfilt(butter(2,35,btype="highpass",fs=RATE,output="sos"), reflected, axis=0)
    extension = np.tanh(extension*1.16)/1.16
    timeline = np.arange(len(score))/RATE
    bridge = smooth((timeline-56)/1.5)
    score[:len(original_score)] = original_score
    score *= (1-bridge)[:,None]
    score += extension*bridge[:,None]
    effects[:len(original_effects)] = original_effects
    # Quiet scene-opening air; no extra notification implying a clinical event.
    for start, duration, gain in [(56.1,.65,.003),(60.8,.6,.0035)]:
        n = round(duration*RATE)
        sound = noise(rng,duration,250,1600)*np.sin(np.linspace(0,np.pi,n))**2
        add(effects,pan(sound,.15),start,gain)
    fade = smooth((SECONDS-.03-timeline)/1.0)**1.35
    score *= fade[:,None]
    effects *= fade[:,None]
    score[-round(.03*RATE):] = 0
    effects[-round(.03*RATE):] = 0
    assert np.array_equal(score[:56*RATE], original_score[:56*RATE])
    assert np.array_equal(effects[:56*RATE], original_effects[:56*RATE])
    return score,effects


def validate(path):
    measurement = analyze(path)
    x = read(path)
    peak = np.max(np.abs(x))
    assert np.isfinite(x).all() and peak < 1
    return {"duration_seconds":len(x)/RATE,"sample_rate_hz":RATE,"channels":2,
            "integrated_lufs":float(measurement["input_i"]),"true_peak_dbtp":float(measurement["input_tp"]),
            "loudness_range_lu":float(measurement["input_lra"]),"sample_peak_dbfs":float(20*np.log10(peak)),
            "clipped_samples":int(np.sum(np.abs(x)>=1)),
            "last_20ms_silent":bool(np.max(np.abs(x[-round(.02*RATE):]))==0),
            "sha256":sha(path)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    narration_path = OUT / f"hospital-narration-{SECONDS}s.wav"
    manifest = json.loads((OUT / "hospital-narration.json").read_text())
    narration = read(narration_path)
    score, effects = synthesize()
    with tempfile.TemporaryDirectory(prefix="hospital-mix-") as directory:
        temporary = Path(directory)
        raw = temporary / "raw.wav"
        wavfile.write(raw, RATE, score.astype(np.float32))
        score_path = OUT / f"hospital-score-{SECONDS}s.wav"
        master(raw, score_path, -23)
        score = read(score_path)
        effects_path = OUT / f"hospital-effects-{SECONDS}s.wav"
        wavfile.write(raw, RATE, effects.astype(np.float32))
        ffmpeg("-y", "-i", raw, "-ar", RATE, "-ac", 2, "-c:a", "pcm_s24le", effects_path)
        # Envelope follows exact edited narration boundaries, with fast entry and
        # smooth release. In gaps the score comes forward without pumping.
        timeline = np.arange(len(score)) / RATE
        duck = np.ones(len(score))
        for cue in manifest["cues"]:
            enter = smooth((timeline - (cue["start"] - .11)) / .1)
            leave = smooth(((cue["audio_end"] + .32) - timeline) / .32)
            duck = np.minimum(duck, 1 - .58 * enter * leave)
        mix = narration + score * duck[:,None] + effects
        mix[-round(.02*RATE):] = 0
        wavfile.write(raw, RATE, mix.astype(np.float32))
        mix_path = OUT / f"hospital-mix-{SECONDS}s.wav"
        master(raw, mix_path, -17.5)
    ffmpeg("-y", "-i", mix_path, "-ar", RATE, "-c:a", "aac", "-b:a", "256k", OUT / f"hospital-mix-{SECONDS}s.m4a")
    reports = {p.name:validate(p) for p in [mix_path,narration_path,score_path,effects_path]}
    final = reports[mix_path.name]
    assert -18 <= final["integrated_lufs"] <= -17
    assert final["true_peak_dbtp"] <= -1.5 and final["last_20ms_silent"]
    cues = manifest["cues"]
    assert all(c["start"] <= c["audio_end"] <= c["end"] for c in cues)
    assert all(a["end"] < b["start"] for a,b in zip(cues,cues[1:]))
    report = {"duration_seconds":SECONDS,"score_seed":SEED,"extension_seed":SEED+76,"tempo_bpm":96,
              "voice_provider":manifest["provider"],"voice_model":manifest["model"],"voice":manifest["voice"],
              "original_score_and_effects":True,"third_party_music_or_samples":False,
              "cue_count":len(cues),"cue_overlaps":False,"all_cues_fit_assigned_slots":True,
              "music_duck_gain_under_voice":.42,"narration_manifest_sha256":sha(OUT/"hospital-narration.json"),
              "original_first_56_seconds_synthesis_unchanged":True,
              "narration_extension_preservation":manifest["extension_preservation"],
              "music_bridge_seconds":[56,57.5],"final_music_fade_seconds":[74.97,75.97],
              "script_sha256":sha(Path(__file__)),"outputs":reports,
              "aac_sha256":sha(OUT/f"hospital-mix-{SECONDS}s.m4a"),
              "timeline":[[0,6,"calm establish"],[6,14,"quiet urgency"],[14,25,"inquisitive comparisons"],
              [25,33,"rhythmic connection"],[33,43,"rising focus"],[43,50,"resolved recommendation"],
              [50,56,"confirmation and movement"],[56,61,"hospital is one example"],
              [61,71,"broader demanding workplaces"],[71,76,"logo resolve"]]}
    (OUT / "hospital-audio-validation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
