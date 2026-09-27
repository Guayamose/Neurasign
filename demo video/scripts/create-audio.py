#!/usr/bin/env python3
"""Synthesize the original NEURASIGN film bed; no samples or external services.

Requires Python with numpy/scipy and an ffmpeg executable. From the repository:
  'neurasign engine/.venv/bin/python' 'demo video/scripts/create-audio.py'

All synthesis is seeded. ffmpeg applies measured two-pass loudness normalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

RATE = 48_000
DURATION = 15.0
SEED = 20_260_927
ROOT = Path(__file__).resolve().parents[1]
NAME = "neurasign-film-bed-15s"


def note(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return smoothstep(t / attack) * smoothstep((n / RATE - t) / release)


def pan(mono: np.ndarray, position: float) -> np.ndarray:
    angle = (position + 1.0) * np.pi / 4.0
    return mono[:, None] * np.array([np.cos(angle), np.sin(angle)])[None, :]


def place(bus: np.ndarray, sound: np.ndarray, start: float, gain: float = 1.0) -> None:
    first = round(start * RATE)
    length = min(len(sound), len(bus) - first)
    if first < 0 or length < 1:
        raise ValueError("Sound must begin within the destination timeline")
    bus[first:first + length] += gain * sound[:length]


def filtered_noise(rng: np.random.Generator, seconds: float, low: float, high: float) -> np.ndarray:
    noise = rng.standard_normal(round(seconds * RATE))
    noise = sosfilt(butter(2, [low, high], btype="bandpass", fs=RATE, output="sos"), noise)
    return noise / max(float(np.std(noise)), 1e-12)


def pad_voice(midi: float, seconds: float, rng: np.random.Generator) -> np.ndarray:
    """Soft detuned harmonics, with slow tape-like drift and no sharp onset."""
    t = np.arange(round(seconds * RATE)) / RATE
    frequency = note(midi)
    result = np.zeros(len(t))
    for detune in [-0.0021, 0.0017]:
        phase = 2 * np.pi * frequency * ((1 + detune) * t + 0.00012 * np.sin(2 * np.pi * 0.23 * t))
        phase += rng.uniform(0, 2 * np.pi)
        # A mellow, finite harmonic series avoids sawtooth aliasing and buzzy highs.
        for harmonic, amplitude in [(1, 1.0), (2, .15), (3, .105), (4, .025), (5, .018)]:
            result += amplitude * np.sin(harmonic * phase) / 2
    result *= (.95 + .05 * np.sin(2 * np.pi * .19 * t + rng.uniform(0, 2 * np.pi)))
    return result * envelope(len(t), .85, 1.5)


def felt_pluck(midi: float, seconds: float, rng: np.random.Generator) -> np.ndarray:
    """Damped felt-like harmonic pulse, not a sine-wave interface beep."""
    t = np.arange(round(seconds * RATE)) / RATE
    frequency = note(midi)
    result = np.zeros(len(t))
    for harmonic, amplitude in [(1, 1.0), (2, .32), (3, .16), (4, .055), (5, .022)]:
        phase = rng.uniform(-.12, .12)
        result += amplitude * np.sin(2 * np.pi * frequency * harmonic * t + phase) * np.exp(-t * (2.0 + .75 * harmonic))
    felt = filtered_noise(rng, seconds, 170, 2200) * np.exp(-t * 35) * .035
    return (result + felt) * envelope(len(t), .026, .2)


def tactile_cut(rng: np.random.Generator) -> np.ndarray:
    seconds = .52
    t = np.arange(round(seconds * RATE)) / RATE
    brush = filtered_noise(rng, seconds, 230, 2700)
    body = np.sin(2 * np.pi * 235 * t) * np.exp(-t * 42)
    sound = (.26 * brush * np.exp(-t * 25) + .17 * body) * envelope(len(t), .012, .2)
    return pan(sound, -.05)


def air_transition(rng: np.random.Generator) -> np.ndarray:
    seconds = .85
    t = np.arange(round(seconds * RATE)) / RATE
    shape = np.sin(np.pi * t / seconds) ** 2
    left = filtered_noise(rng, seconds, 450, 2600)
    right = .75 * left + .25 * filtered_noise(rng, seconds, 450, 2600)
    return np.column_stack([left, right]) * shape[:, None] * .13


def synthesize() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEED)
    frames = round(RATE * DURATION)
    dry = np.zeros((frames, 2), dtype=np.float64)
    # Open voicings leave space for footage. D(add9) -> Gmaj9 -> A(sus) -> D6/9.
    chords = [
        (0.0, 5.0, [50, 57, 64, 66], .070),
        (3.2, 5.6, [43, 57, 62, 66], .061),
        (7.4, 5.0, [45, 57, 62, 64], .057),
        (10.7, 4.3, [50, 57, 59, 64, 66], .068),
    ]
    for start, seconds, notes, gain in chords:
        positions = np.linspace(-.58, .58, len(notes))
        for midi, position in zip(notes, positions):
            place(dry, pan(pad_voice(midi, seconds, rng), float(position)), start, gain)

    # Sparse 80 BPM pulse; restrained during desk footage, gently more present
    # during the dashboard. No kick drum, paired heartbeat or warning rhythm.
    pulses = [
        (.75, 62, .045), (1.875, 57, .030), (3.0, 64, .035),
        (4.125, 62, .038), (5.25, 62, .061), (6.0, 57, .044),
        (6.75, 66, .047), (7.5, 64, .037), (8.25, 62, .055),
        (9.0, 57, .043), (9.75, 64, .049), (10.5, 69, .034),
    ]
    for index, (start, midi, gain) in enumerate(pulses):
        place(dry, pan(felt_pluck(midi, 1.7, rng), -.24 if index % 2 == 0 else .26), start, gain)
    # A low, resolved logo chord blooms once; no jingle or high-pitched ping.
    for offset, midi, position in [(0, 50, -.12), (.035, 57, -.28), (.070, 66, .22), (.105, 64, .36)]:
        place(dry, pan(felt_pluck(midi, 3.0, rng), position), 11.0 + offset, .038)

    # Short, quiet stereo early reflections give the otherwise dry synthesis air.
    mix = dry.copy()
    for seconds, gain in [(.087, .12), (.161, .09), (.263, .052), (.389, .030)]:
        shift = round(seconds * RATE)
        mix[shift:] += dry[:-shift, ::-1] * gain

    cut = tactile_cut(rng)
    whoosh = air_transition(rng)
    for start, gain in [(3.5, .075), (5.0, .11), (11.0, .065)]:
        place(mix, cut, start, gain)
    for cut_time, gain in [(3.5, .028), (5.0, .035), (11.0, .035)]:
        place(mix, whoosh, cut_time - .55, gain)

    # Remove subsonic energy; gentle tape-like saturation stays comfortably below
    # distortion levels. Stereo stays narrow enough to fold down cleanly to mono.
    mix = sosfilt(butter(2, 38, btype="highpass", fs=RATE, output="sos"), mix, axis=0)
    mix = np.tanh(mix * 1.12) / 1.12
    time = np.arange(frames) / RATE
    opening = smoothstep(time / .22)
    ending = smoothstep((14.94 - time) / 1.8) ** 1.5
    mix *= (opening * ending)[:, None]
    mix[-round(.06 * RATE):] = 0
    # Standalone accents are deliberately quiet; the full bed already includes
    # them, so editors should not automatically add them a second time.
    cut *= 10 ** (-23 / 20) / max(float(np.max(np.abs(cut))), 1e-12)
    whoosh *= 10 ** (-25 / 20) / max(float(np.max(np.abs(whoosh))), 1e-12)
    return mix, cut, whoosh


def ffmpeg(*args: str) -> str:
    process = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return process.stderr


def loudness(path: Path) -> dict:
    log = ffmpeg("-i", str(path), "-af", "loudnorm=I=-19:TP=-1.5:LRA=7:print_format=json", "-f", "null", "-")
    blocks = re.findall(r"\{\s*\"input_i\".*?\}", log, re.S)
    if len(blocks) != 1:
        raise RuntimeError("Could not read ffmpeg loudness analysis")
    return json.loads(blocks[0])


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "audio")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mix, cut, whoosh = synthesize()
    output = args.output / f"{NAME}.wav"
    with tempfile.TemporaryDirectory(prefix="neurasign-audio-") as temporary:
        temporary = Path(temporary)
        raw = temporary / "unmastered.wav"
        wavfile.write(raw, RATE, mix.astype(np.float32))
        analysis = loudness(raw)
        settings = (
            "loudnorm=I=-19:TP=-1.5:LRA=7:"
            f"measured_I={analysis['input_i']}:measured_TP={analysis['input_tp']}:"
            f"measured_LRA={analysis['input_lra']}:measured_thresh={analysis['input_thresh']}:"
            f"offset={analysis['target_offset']}:linear=true:print_format=json"
        )
        ffmpeg("-y", "-i", str(raw), "-af", settings, "-ar", str(RATE), "-ac", "2", "-c:a", "pcm_s24le", "-t", str(DURATION), str(output))
        for filename, samples in [("neurasign-cut-soft.wav", cut), ("neurasign-transition-air.wav", whoosh)]:
            path = temporary / filename
            wavfile.write(path, RATE, samples.astype(np.float32))
            ffmpeg("-y", "-i", str(path), "-ar", str(RATE), "-ac", "2", "-c:a", "pcm_s24le", str(args.output / filename))

    # Compact listening/reference copy. Use the WAV for the actual film mix.
    preview = args.output / f"{NAME}.m4a"
    ffmpeg("-y", "-i", str(output), "-c:a", "aac", "-b:a", "256k", "-ar", str(RATE), str(preview))
    measured = loudness(output)
    rate, pcm = wavfile.read(output)
    samples = pcm.astype(np.float64) / 2 ** 31  # scipy left-aligns PCM24 in int32.
    peak = float(np.max(np.abs(samples)))
    tail = samples[-round(.25 * rate):]
    tail_rms = float(np.sqrt(np.mean(tail ** 2)))
    correlation = float(np.corrcoef(samples.T)[0, 1])
    assert rate == RATE and samples.shape == (round(DURATION * RATE), 2)
    assert np.isfinite(samples).all() and peak < 1
    assert -20 <= float(measured["input_i"]) <= -18, measured
    assert float(measured["input_tp"]) <= -1, measured
    assert np.max(np.abs(samples[-round(.05 * RATE):])) == 0
    assert tail_rms < 10 ** (-50 / 20)
    assert correlation > 0
    report = {
        "title": "NEURASIGN / Quiet Connection", "original_synthesis": True,
        "external_samples": False, "external_services": False, "voice": False,
        "seed": SEED, "sample_rate_hz": rate, "channels": 2,
        "duration_seconds": len(samples) / rate, "frames": len(samples), "encoding": "PCM signed 24-bit",
        "integrated_lufs": float(measured["input_i"]), "true_peak_dbtp": float(measured["input_tp"]),
        "loudness_range_lu": float(measured["input_lra"]),
        "sample_peak_dbfs": float(20 * np.log10(peak)), "clipped_samples": int(np.sum(np.abs(samples) >= 1)),
        "final_250ms_rms_dbfs": float(20 * np.log10(max(tail_rms, 1e-15))),
        "final_50ms_digital_silence": True, "stereo_correlation": correlation,
        "files": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in [output, preview, args.output / "neurasign-cut-soft.wav", args.output / "neurasign-transition-air.wav"]},
        "script_sha256": digest(Path(__file__)), "numpy_version": np.__version__,
        "ffmpeg_version": subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True).stdout.splitlines()[0],
        "normalization": "Measured two-pass ffmpeg loudnorm; -19 LUFS target; -1.5 dBTP ceiling; LRA7.",
    }
    (args.output / "audio-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
