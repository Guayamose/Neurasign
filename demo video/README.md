# NEURASIGN — Every second matters

A complete **76-second animated NEURASIGN concept film**, with original vector characters and environments, English narration, an original score, and cobalt branding. The hospital story follows three fictional doctors and a coordinator-confirmed recommendation. A new closing section broadens the idea to construction sites, industrial operations, and control rooms.

## Watch and download

Run `npm run preview` from this folder and open **http://localhost:3101**. The player includes native playback/fullscreen controls, English captions, chapter navigation, and a 1080p/4K selector that preserves the current position.

| File | Contents |
| --- | --- |
| `exports/neurasign-hospital-76s-1080p.mp4` | Full film, 1920 × 1080, 30 fps, H.264/AAC. |
| `exports/neurasign-hospital-76s-4k.mp4` | Full film, 3840 × 2160, 30 fps, H.264/AAC. |
| `exports/neurasign-hospital-editable-project.zip` | Editable scenes, official logo copies, captions, scripts, package lockfile, and audio masters. |
| `public/audio/hospital-narration.vtt` | English caption file for use outside the preview player. |

The editable archive includes the current 76-second WAV masters and all eleven narration source cues. Older 60-second masters and stale review reports are excluded. It excludes credentials, `.env` files, application API responses, research datasets, stock footage, and `node_modules`. Install dependencies after extracting it.

## Edit and render

Use **Node.js 20+**, npm, Python 3, and Google Chrome. The render commands use `/usr/bin/google-chrome` with `--chrome-mode=chrome-for-testing`; adjust that path if Chrome is installed elsewhere. Run commands from **`demo video/`** or the extracted project folder:

```sh
node --version
npm ci
npm run typecheck
npm run studio       # Editable timeline at http://localhost:3100
npm run storyboard   # Scene review images
npm run still        # Player poster
npm run render       # 1080p film
npm run render:4k    # 4K film
npm run preview     # Export player at http://localhost:3101
```

**Rendering with the supplied audio requires no API key or external model call.** The film reads `public/audio/hospital-mix-76s.wav` directly. FFmpeg plus Python/NumPy/SciPy are needed only to rebuild the separate audio production pipeline. See [audio production notes](docs/hospital-audio.md).

The Git checkout includes both final MP4s, the mastered WAV, all eleven original narration cues and the player poster. Generated stems, intermediate previews, older MP4s and editable ZIP archives stay local. To rebuild the downloadable editable archive without any API calls, install NumPy/SciPy and FFmpeg, then run from this folder:

```sh
python3 scripts/create-hospital-narration.py --assemble-only
python3 scripts/create-hospital-audio.py
python3 scripts/package-hospital-project.py
```

These commands recreate the separate stems and processed cues from the included narration sources. The current film and player can be used immediately without this archive-building step.

## What is editable

- `src/hospital/HospitalFilm.tsx`: the hospital story, workplace extension, pacing, titles, transitions and character placement.
- `src/hospital/Characters.tsx`, `Environment.tsx`, `Props.tsx`: original SVG artwork, refined hands and faces, and movement.
- `src/hospital/Workplaces.tsx`: construction, industrial and control-room environments for the wider-purpose ending.
- `src/hospital/Design.tsx`: palette, type, motion helpers and fictional scenario values.
- `src/Root.tsx`: 76-second compositions: 2,280 frames at 30 fps, and output sizes.
- `public/audio/`: full WAV mix, separate stems, captions and narration timing.

Narration was generated using **Google Gemini 3.8 Flash TTS**, stock voice **Iapetus**, through the existing authorized project credential. It is synthetic narration, not ElevenLabs or a cloned voice. Music and effects are original local synthesis. The film contains original vector art rather than stock or generated human footage. No footage or audio from the Astra reference is used.

## What the film demonstrates

This is a **fictional product concept**, not footage of a deployed clinical workflow or an evaluation of the trained models. The doctors, workplace scenes, readings and 0–100 estimates are scripted for the story; the scores are not accuracy percentages. The recommendation and coordinator confirmation are illustrated, not executed against the application. The current app, presentation and original logo files are unchanged.

See the [complete story and eleven narration cues](docs/hospital-story.md), [environment notes](docs/hospital-art.md) and [character notes](docs/character-art.md). The earlier 60-second MP4 exports remain preserved separately; the player and editable package use this 76-second revision.
