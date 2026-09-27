# NEURASIGN film audio — Quiet Connection

An original, restrained electronic instrumental bed for the 15-second sample. It uses soft detuned harmonic pads, sparse felt-like pulses, quiet brushed transition accents and a resolved final chord. There is no speech, heartbeat, alarm, drum hit or interface beep. The nominal pulse is 80 BPM; it becomes a little more present during the dashboard section.

## Ready-to-use files

| File under `public/audio/` | Use |
| --- | --- |
| `neurasign-film-bed-15s.wav` | Main film mix: 15.000 s, 48 kHz stereo, PCM 24-bit. Place at film time 0, unity gain. |
| `neurasign-film-bed-15s.m4a` | Compact AAC listening/reference copy; use the WAV for the final render. |
| `neurasign-cut-soft.wav` | Optional 0.520 s tactile accent, peak −23 dBFS. |
| `neurasign-transition-air.wav` | Optional 0.850 s soft air transition, peak −25 dBFS. |
| `audio-validation.json` | Actual measured levels, hashes, generator version and validation results. |

**The main bed already contains the cut accents.** The two standalone effects are provided for later edit changes; automatically layering them over the main bed would double the accents.

## Cue sheet

| Film time | Picture | Sound |
| --- | --- | --- |
| 0–3.5 s | Real desk footage | A gently opening warm D(add9) pad with sparse midrange pulses. |
| 3.5 s | Connection title | Quiet brushed cut accent and a soft harmonic change. |
| 5–11 s | Actual dashboard | Slightly more regular felt-like pulse; restrained energy supports reading the interface. |
| 11 s | Brand/logo | Single low resolved chord with a subtle air transition; the rhythmic sequence stops. |
| 13.14–14.94 s | Logo hold | Smooth final fade; the last 60 ms of the master are digital silence. |

The voicings move through D(add9), Gmaj9, A(sus) and D6/9. The sound comes from finite harmonic oscillators, seeded filtered noise, short stereo reflections and gentle saturation. No external samples, loops, recordings, pretrained audio, paid service or generated voice are used. There are no third-party music or sample licenses to obtain for these synthesized assets.

## Measured master

Measured on the final WAV using FFmpeg's EBU R128 loudness analysis:

- Duration: **15.000 s**, 720,000 stereo frames at 48,000 Hz.
- Integrated loudness: **−19.0 LUFS**.
- True peak: **−8.14 dBTP**, below the requested −1 dBTP ceiling.
- Loudness range: **2.6 LU**.
- Clipped samples: **0**.
- Final 250 ms RMS: **−99.32 dBFS**; final 50 ms: digital silence.
- Stereo correlation: **+0.770**, with a stable mono fold-down.

The mastering step targets −19 LUFS using measured two-pass normalization, with a −1.5 dBTP ceiling. The material does not need limiting to reach that loudness; its natural peak remains well below the ceiling. The integrated level should be checked again after any addition of footage sound, voice or other effects, and after the final video encode.

## Reproduce

From the repository root, using the existing engine environment:

```sh
'neurasign engine/.venv/bin/python' 'demo video/scripts/create-audio.py'
```

The script requires NumPy, SciPy and FFmpeg. It uses seed `20260927`, writes only its audio output directory, analyzes the final WAV, and checks exact frame count, stereo format, finite samples, clipping, loudness, peak ceiling, ending silence and tail energy. `--output /another/directory` can be used to compare a fresh deterministic render without replacing the working assets. Exact byte hashes are recorded in `audio-validation.json`; use the same numerical libraries and FFmpeg build for byte-for-byte reproduction.

A second independent render into a temporary directory produced identical SHA-256 hashes for the WAV, AAC preview and both optional effects.

If the edit's duration or cuts change, change the cue schedule in the generator and rerender instead of stretching the master. The WAV is ready for the 0–15 s timeline supplied for this sample; subjective balance should also be reviewed with the finished picture on speakers and headphones.
