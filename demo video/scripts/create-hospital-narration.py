#!/usr/bin/env python3
"""Generate/cache eleven authorized Gemini narration cues; assemble a 76 s stem.

Credentials are read locally and are never printed or stored in audio metadata.
Cached source WAVs avoid repeat API spending. --assemble-only makes no API calls.
"""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public/audio"
RATE = 48_000
SECONDS = 76
MODEL = "gemini-3.8-flash-tts"
VOICE = "Iapetus"
STYLE = "Warm, engaging, confident English narration with a vocal smile. Energetic conversational delivery, crisp articulation, purposeful forward momentum, brisk but not rushed. Short natural pauses at punctuation. No dramatic whisper, no shouting, no music."
CUES = [
    (.5, 4.8, "In an emergency, the right support can change everything."),
    (5.2, 10.8, "A patient arrives. Three qualified doctors. One decision: who should respond?"),
    (11.3, 17.8, "Behind each wristband is a different story. Heart rate. Variability. Movement."),
    (18.2, 25.8, "NeuraSign turns those signals into estimates of stress, fatigue, workload and readiness."),
    (26.2, 32.8, "Omar is already busy. Emma shows elevated fatigue. Maya is available and ready."),
    (33.2, 40.8, "The incident reaches NeuraSign. It compares the team’s signals, availability and relevant skills."),
    (41.2, 48.8, "Maya is the recommended match. You see who, and the reasons behind the recommendation."),
    (49.2, 55.8, "The coordinator confirms. Maya gets the alert, and moves straight to the patient."),
    (56.2, 60.7, "This hospital is just one example."),
    (61.0, 70.8, "NeuraSign is designed for demanding workplaces with real risks. Construction sites. Industrial operations. Control rooms."),
    (71.2, 75.7, "NeuraSign. Understand your team. Respond with confidence."),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get_key():
    names = ["GEMINI_API_KEY", "GOOGLE_API_KEY", "Google_AI_API_key"]
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    path = ROOT.parent / "neurasign_server_dashboard/.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
            if match and match[1] in names:
                value = match[2].strip().strip("\"'")
                if value:
                    return value
    raise RuntimeError("No configured Gemini API credential found")


def run_ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *map(str, args)], check=True, capture_output=True)


def generate(index, key):
    start, end, text = CUES[index]
    path = OUTPUT / f"hospital-cue-{index + 1:02d}-source.wav"
    metadata = path.with_suffix(".json")
    spoken = text.replace("NeuraSign", "NeuroSign")
    pace = " Lively concise brand sign-off; keep all eight words within about three and a half seconds." if index == len(CUES) - 1 else ""
    request_data = {
        "contents": [{"role": "user", "parts": [{"text": spoken, "speech_metadata": {"style": STYLE + pace}}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"voice": VOICE}}},
    }
    fingerprint = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
    if path.exists() and metadata.exists():
        saved = json.loads(metadata.read_text())
        if saved["request_sha256"] == fingerprint and saved["source_sha256"] == sha(path):
            print(json.dumps({"cue": index + 1, "status": "using cached source"}), flush=True)
            return
        raise RuntimeError(f"Cached cue {index + 1} differs; preserve or explicitly remove it before regeneration")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    request = urllib.request.Request(url, data=json.dumps(request_data).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"}, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
            break
        except urllib.error.HTTPError as error:
            # Never echo response bodies, request headers, or credential-bearing URLs.
            if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                print(json.dumps({"cue": index + 1, "status": "retry", "http_status": error.code}), flush=True)
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini cue {index + 1} request failed with HTTP {error.code}") from None
    parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    inline = next((p["inlineData"] for p in parts if "inlineData" in p), None)
    if not inline:
        raise RuntimeError(f"Gemini cue {index + 1} returned no audio")
    data = base64.b64decode(inline["data"], validate=True)
    if data[:4] == b"RIFF":
        rate, audio = wavfile.read(io.BytesIO(data))
        if audio.ndim != 1 or rate != 24000:
            raise RuntimeError("Unexpected provider audio format")
        path.write_bytes(data)
    else:
        rate = 24000
        audio = np.frombuffer(data, dtype="<i2")
        wavfile.write(path, rate, audio)
    metadata.write_text(json.dumps({"provider": "Google Gemini API", "model": MODEL, "voice": VOICE,
        "request_sha256": fingerprint, "source_sha256": sha(path), "caption_text": text,
        "spoken_text": spoken, "style": STYLE + pace, "source_rate_hz": rate,
        "source_duration_seconds": len(audio) / rate, "usage": result.get("usageMetadata", {})}, indent=2) + "\n")
    print(json.dumps({"cue": index + 1, "status": "generated", "source_seconds": round(len(audio) / rate, 3)}), flush=True)


def trim_silence(path):
    rate, pcm = wavfile.read(path)
    x = pcm.astype(float) / 32768
    # Keep 55 ms before/100 ms after detected speech, retaining consonants/breaths.
    block = max(1, round(rate * .01))
    energy = np.array([np.sqrt(np.mean(x[i:i + block] ** 2)) for i in range(0, len(x), block)])
    active = np.flatnonzero(energy > max(.0015, float(energy.max()) * .014))
    if not len(active):
        raise ValueError("Generated cue is silent")
    first = max(0, active[0] * block - round(.055 * rate))
    last = min(len(x), (active[-1] + 1) * block + round(.1 * rate))
    return rate, x[first:last], first / rate, (len(x) - last) / rate


def clock(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}"


def assemble():
    stem = np.zeros(round(SECONDS * RATE), dtype=float)
    records = []
    with tempfile.TemporaryDirectory(prefix="hospital-narration-") as temporary:
        temporary = Path(temporary)
        for index, (start, end, text) in enumerate(CUES):
            source = OUTPUT / f"hospital-cue-{index + 1:02d}-source.wav"
            rate, audio, leading, trailing = trim_silence(source)
            available = end - start - .035
            speed = max(1., len(audio) / rate / available)
            if speed > 1.45:
                raise RuntimeError(f"Cue {index + 1} needs excessive acceleration ({speed:.3f}); revise delivery")
            raw = temporary / "trim.wav"
            wavfile.write(raw, rate, audio.astype(np.float32))
            cue = OUTPUT / f"hospital-cue-{index + 1:02d}.wav"
            chain = f"atempo={speed:.9f},highpass=f=75,equalizer=f=2800:t=q:w=0.8:g=1.0,acompressor=threshold=0.12:ratio=2.0:attack=8:release=90:makeup=1.3,loudnorm=I=-17.5:TP=-2.0:LRA=7"
            run_ffmpeg("-y", "-i", raw, "-af", chain, "-ar", RATE, "-ac", 1, "-c:a", "pcm_s24le", cue)
            actual_rate, pcm = wavfile.read(cue)
            x = pcm.astype(float) / 2 ** 31
            assert actual_rate == RATE and len(x) / RATE <= end - start
            fade = min(round(.008 * RATE), len(x) // 2)
            x[:fade] *= np.linspace(0, 1, fade)
            x[-fade:] *= np.linspace(1, 0, fade)
            first = round(start * RATE)
            stem[first:first + len(x)] = x
            records.append({"cue": index + 1, "start": start, "end": end,
                "audio_end": start + len(x) / RATE, "text": text, "spoken_text": text.replace("NeuraSign", "NeuroSign"),
                "trim_leading_seconds": leading, "trim_trailing_seconds": trailing,
                "tempo_multiplier": speed, "audio_file": cue.name, "audio_sha256": sha(cue), "source_sha256": sha(source)})
        raw = temporary / "assembled.wav"
        wavfile.write(raw, RATE, np.column_stack([stem, stem]).astype(np.float32))
        output = OUTPUT / f"hospital-narration-{SECONDS}s.wav"
        run_ffmpeg("-y", "-i", raw, "-ar", RATE, "-ac", 2, "-c:a", "pcm_s24le", output)
    assert all(a["audio_end"] <= b["start"] for a, b in zip(records, records[1:]))
    assert len(stem) == SECONDS * RATE and np.max(np.abs(stem)) < 1
    preserved = ROOT / "review/hospital-original-audio"
    preservation = {}
    if (preserved / "hospital-narration.json").exists():
        original = json.loads((preserved / "hospital-narration.json").read_text())
        assert records[:8] == original["cues"][:8], "Original eight edited cues changed"
        assert records[-1]["source_sha256"] == original["cues"][-1]["source_sha256"], "Original sign-off source changed"
        old_rate, old_pcm = wavfile.read(preserved / "hospital-narration-60s.wav")
        new_rate, new_pcm = wavfile.read(output)
        assert old_rate == new_rate == RATE
        assert np.array_equal(old_pcm[:56 * RATE], new_pcm[:56 * RATE]), "Original first 56 seconds of narration changed"
        preservation = {"backup": "review/hospital-original-audio", "first_eight_cues_unchanged": True,
            "first_56_seconds_pcm_identical": True, "signoff_source_reused_from_original_cue": 9,
            "new_generation_cues": [9, 10], "original_manifest_sha256": sha(preserved / "hospital-narration.json")}
    manifest = {"provider": "Google Gemini API", "model": MODEL, "voice": VOICE,
        "duration_seconds": float(SECONDS), "sample_rate_hz": RATE, "channels": 2,
        "brand_pronunciation": "NeuroSign; on-screen spelling remains NeuraSign", "cues": records,
        "script_sha256": sha(Path(__file__)), "narration_sha256": sha(output),
        "generation_is_deterministic": False, "cached_sources_allow_reproducible_assembly": True,
        "extension_preservation": preservation,
        "scope": "Fictional animated hospital product-concept narration; not evidence of deployed clinical functionality."}
    (OUTPUT / "hospital-narration.json").write_text(json.dumps(manifest, indent=2) + "\n")
    captions = "WEBVTT\n\n" + "\n\n".join(f"{r['cue']}\n{clock(r['start'])} --> {clock(r['end'])}\n{r['text']}" for r in records) + "\n"
    (OUTPUT / "hospital-narration.vtt").write_text(captions)
    print(json.dumps({"assembled": str(output), "cues": len(records), "duration_seconds": SECONDS, "tempo_multipliers": [round(r['tempo_multiplier'], 3) for r in records]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assemble-only", action="store_true")
    parser.add_argument("--only-cue", type=int, choices=range(1, len(CUES) + 1))
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not args.assemble_only:
        key = get_key()
        indices = [args.only_cue - 1] if args.only_cue else range(len(CUES))
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda index: generate(index, key), indices))
    if not args.only_cue:
        assemble()


if __name__ == "__main__":
    main()
