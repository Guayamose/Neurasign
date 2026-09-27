# NEURASIGN demo film

A finished **15-second style sample** for the planned one-minute film: real live-action footage, actual NEURASIGN captures, cobalt branding, restrained typography and an original instrumental soundtrack.

## Watch

Open `exports/neurasign-style-sample-15s.mp4` in a video player, or run `npm run preview` here and visit <http://localhost:3101>. The preview includes playback controls, sound, fullscreen and a download link. The export is 1920 × 1080, 30 fps, H.264 with stereo AAC audio.

This is the first finished visual sample, not the complete 60-second demo. The sample establishes the human setting, product treatment, motion and sound. It does not yet explain the full product workflow.

## Edit and render

Requirements: Node.js 20+, npm, Python 3, FFmpeg and Google Chrome. Activate Node.js 20 or later before running the npm commands; the project's `engines` field requires it. The checked-in render command uses `/usr/bin/google-chrome` with `--chrome-mode=chrome-for-testing`; change the executable path for another installation.

Run these commands from **`demo video/`**, not the repository root:

```sh
node --version # Confirm v20 or later before continuing.
npm ci
python3 scripts/fetch-footage.py
python3 scripts/prepare-footage.py
# Create the original soundtrack using the neighboring engine environment:
'../neurasign engine/.venv/bin/python' scripts/create-audio.py
npm run typecheck
npm run studio
```

The Python audio generator requires NumPy and SciPy. The example above uses this repository's existing engine environment; a separate Python environment with those packages also works. Studio opens on port **3100**; the exported-film preview uses **3101**. To export the film from the same folder:

```sh
npm run render
npm run still
```

`src/Sample.tsx` contains the scene layouts and motion. `src/Root.tsx` defines resolution, frame rate and duration. All film text is English. Original source files in the application, logo folder and presentation remain unchanged.

| Time | Picture |
| --- | --- |
| 0–3.5 s | Real desk scene. “Every team has a pulse.” |
| 3.5–5 s | Wearable close-up. “Make it visible.” |
| 5–8 s | Actual manager overview, two recorded sample profiles. |
| 8–11 s | Actual recorded heart-rate chart, units and source context. |
| 11–15 s | NEURASIGN logo and closing line. |

## Assets and provenance

- Live action: licensed Mixkit footage, selected and checked at item level. [Source and license ledger](docs/footage-sources.md). The actor and watch illustrate the setting; the dashboard values were not collected from this person.
- Product: unchanged screenshots of the working local demo, using one frozen UNIVERSE snapshot. [Capture notes](docs/capture-notes.md). No invented scores, alert flags or model-accuracy claims.
- Branding: copies of the project's supplied cobalt SVG logos.
- Sound: original seeded synthesis; no third-party music, samples, stock loops, paid generation service or voice. The 15-second stereo WAV is mastered to −19.0 LUFS and already includes the cut accents. [Audio notes and reproduction](docs/audio-notes.md).
- Editing: [Remotion](https://www.remotion.dev/) and FFmpeg. Consult [Remotion's licensing](https://www.remotion.dev/docs/licensing) for its organizational terms.

Raw licensed footage, raw API snapshots, generated WAV masters, node dependencies and rendered exports stay out of Git. `fetch-footage.py` downloads the selected clip and verifies its SHA-256 hash. The exported film and all local assets remain in this folder.

The Astra reference informed the use of real environments and readable product framing. None of its footage or audio appears in this film.
