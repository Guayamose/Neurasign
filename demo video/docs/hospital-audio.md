# Hospital film: narration, score and final mix

The complete 76-second soundtrack is ready in `public/audio/hospital-mix-76s.wav`. Place it at film time **0**, at unity gain. It already contains narration, music and quiet editorial effects; do not simultaneously play the separate stems. The hospital story now leads into a wider-workplace montage and the final brand sign-off.

## Deliverables

| File under `public/audio/` | Contents |
| --- | --- |
| `hospital-mix-76s.wav` | Final 76.000 s mix, 48 kHz stereo PCM 24-bit. |
| `hospital-mix-76s.m4a` | Stereo AAC listening/edit reference. |
| `hospital-narration-76s.wav` | Isolated narration, with all eleven cues positioned on the 76 s timeline. |
| `hospital-score-76s.wav` | Isolated original instrumental score. |
| `hospital-effects-76s.wav` | Isolated quiet door, movement, connection, confirmation and transition effects. |
| `hospital-narration.vtt` | Eleven English caption cues at the supplied scene times. |
| `hospital-narration.json` | Exact captions, spoken text, start/end times, actual audio endings, tempo adjustments and source hashes. |
| `hospital-audio-validation.json` | Actual duration, loudness, peak, clipping and cue-alignment checks. |
| `hospital-narration-listening-review.json` | Separate automated transcription/quality review and word-sequence comparison. |
| `hospital-cue-01-source.wav` … `hospital-cue-11-source.wav` | Cached generated narration, with matching provider metadata JSON. |
| `hospital-cue-01.wav` … `hospital-cue-11.wav` | Trimmed and level-matched narration cues. |

The original 60-second masters remain in `public/audio/`. Before the extension, all original audio, source cues, metadata, scripts and this document were preserved in `review/hospital-original-audio/`; its `backup-manifest.json` records verified hashes. The stable JSON/VTT filenames now describe the 76-second version. Original cue 9 is preserved in that backup and reused as current cue 11.

## Voice provenance and timing

Narration uses **Google Gemini API, `gemini-3.8-flash-tts`, stock voice `Iapetus`**. It was generated through the project's existing authorized account credential. This is synthetic English narration, not ElevenLabs, a recorded human performer or a clone of a real person. No account purchase or new paid-plan subscription was made. Normal API usage may use the account's existing quota or billing.

The performance direction asks for warmth, clarity, an engaging vocal smile and purposeful momentum. The spoken spelling **“NeuroSign”** guides pronunciation; captions retain the brand spelling **“NeuraSign”**. All supplied narration words are retained. **All eleven cues run at natural speed**. The first eight edited cues, their timing and the first 56 seconds of narration PCM are identical to the original. Only cues 9 and 10 were newly generated; cue 11 reuses the original sign-off source at its natural speed in the longer final slot. Leading and trailing silence are trimmed with small margins to preserve consonants and breaths. There are no overlapping cues.

| Cue | Caption window | Subject |
| --- | --- | --- |
| 1 | 0.5–4.8 s | The right support in an emergency. |
| 2 | 5.2–10.8 s | Patient arrival and three qualified doctors. |
| 3 | 11.3–17.8 s | Wrist signals: heart rate, variability and movement. |
| 4 | 18.2–25.8 s | Proposed stress, fatigue, workload and readiness estimates. |
| 5 | 26.2–32.8 s | Omar, Emma and Maya in the fictional scenario. |
| 6 | 33.2–40.8 s | Comparing signals, availability and relevant skills. |
| 7 | 41.2–48.8 s | Maya's recommendation and its reasons. |
| 8 | 49.2–55.8 s | Coordinator confirmation and response. |
| 9 | 56.2–60.7 s | “This hospital is just one example.” |
| 10 | 61.0–70.8 s | Demanding workplaces with real risks: construction, industrial operations and control rooms. |
| 11 | 71.2–75.7 s | Original brand sign-off. |

This is narration for a fictional animated product concept. It does not establish deployed clinical functionality or validate physiological employee-state inference.

Google's [TTS documentation](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation) describes stock voices and delivery direction through speech metadata. The provider returns 24 kHz mono speech; the editing pipeline resamples it to the requested 48 kHz stereo timeline. Resampling changes the delivery format, not the original voice bandwidth.

## Original musical arc

The original score develops at **96 BPM**, synthesized locally with seed `2026092801`; the new section uses a separate seed, `2026092877`. It uses damped piano-like keys, a syncopated ostinato, warm bass, light brushed percussion, open harmonic voicings and short stereo reflections. The first 56 seconds of music/effects synthesis retain the original arrangement and timing. Six newly composed bars broaden the harmony from 56 to 71 seconds, followed by a longer final resolve. No music loop is repeated to fill the extension.

A smooth 1.5-second overlap at 56–57.5 seconds lets the former hospital ending become the transition into the wider story. The new progression moves through Dadd9, Gmaj9, Bm9, Em9 and an A suspension before returning to D. Each bar changes inversion, accents and melodic responses. Final loudness normalization may slightly alter the opening music/mix gain; narration PCM and scene timing remain preserved.

| Time | Musical direction |
| --- | --- |
| 0–6 s | Sparse, calm establishment. |
| 6–14 s | Minor color, bass and a quiet sense of urgency. |
| 14–25 s | Inquisitive piano responses for the comparisons. |
| 25–33 s | Clearer rhythmic connection and forward movement. |
| 33–43 s | Increased focus and rhythmic density. |
| 43–50 s | Brighter resolved harmony for the recommendation. |
| 50–56 s | Confirmation and onward movement. |
| 56–61 s | A flowing harmonic bridge: the hospital is one example. |
| 61–71 s | Brighter, evolving rhythmic movement across other workplaces. |
| 71–76 s | Broader logo resolve; music fades smoothly from 74.97 to 75.97 s. |

Quiet effects suggest a sliding door, cart movement, signal handoff and coordinator confirmation. They are designed editorial cues, not recordings of medical equipment. There is no siren, heartbeat, alarm or medical-monitor sound. The music and effects contain no third-party samples, loops or stock recordings; no third-party music/sample license is required for those original synthesized stems.

Music drops to **42% of its normal gain** beneath narration, with short anticipatory entry and smooth release. The voice remains centered and forward. The mix is mastered with measured two-pass FFmpeg loudness normalization.

## Validation

The final WAV measures **−17.5 LUFS integrated**, **−3.97 dBTP**, with **3.9 LU** loudness range and **zero clipped samples**. It contains exactly **3,648,000 stereo frames at 48 kHz**, or **76.000 seconds**. All four stems/mix files are exactly 76 seconds. All eleven cues fit their assigned windows; the last 20 ms of the mix are digital silence. The final spoken word ends at approximately 75.118 seconds.

The independent `gemini-2.5-flash` transcription matched **all 124 spoken words** in the complete final mix, after normalizing punctuation, capitalization and the brand's phonetic spelling. The review reported clear voice, smooth music transitions and ending, and no audible defects. `hospital-narration-listening-review.json` records the reviewed mix hash and exact word-sequence comparison. This is an automated check, not a claim that a human engineer auditioned the audio. Review the final picture-and-sound render on speakers or headphones before release.

## Reproduce

From the repository root:

```sh
# Generate missing cues using the configured account; cached cues are reused.
'neurasign engine/.venv/bin/python' 'demo video/scripts/create-hospital-narration.py'

# Reassemble cached speech without making any API calls.
'neurasign engine/.venv/bin/python' 'demo video/scripts/create-hospital-narration.py' --assemble-only

# Rebuild the deterministic music/effects and master the complete mix locally.
'neurasign engine/.venv/bin/python' 'demo video/scripts/create-hospital-audio.py'
```

Dependencies are NumPy, SciPy and FFmpeg. The narration script reads `GEMINI_API_KEY`, `GOOGLE_API_KEY` or the existing `Google_AI_API_key` setting locally; credentials are never written to manifests or logs. Remote voice generation is not guaranteed to be deterministic. The saved source audio permits repeatable local assembly; music and effects are seeded. Preserve the cached source cues and their hashes instead of regenerating them unnecessarily.
