# Real interface captures

Captured from the working application at `http://localhost:3000/demo` on 27 September 2026.

These are browser screenshots of the shipped interface. No interface labels, values, participants, or graphs were recreated or retouched. The API returned two UNIVERSE Empatica recordings under fictional profile names Alex and Sam, paused at recording time 30:00. Each profile had 90 recorded history windows. The existing heuristic estimates remain unvalidated; the manager page labels them experimental.

The capture script performs one read of `/api/state`, saves that response unchanged to `public/capture/recorded-snapshot.json`, and supplies it to browser HTTP and WebSocket reads for a consistent photographic moment. It blocks application writes and never calls a model provider. `manifest.json` records the snapshot hash, frame dimensions, crop bounds, zero writes, and zero browser errors.

## Best assets for compositing

| File under `public/capture/` | Dimensions | Suggested use |
| --- | --- | --- |
| `manager-overview-panel@2x.png` | 2400 × 1462 | Readable manager view on the room's screen; includes experimental interpretation context. |
| `alex-heart-rate-panel@2x.png` | 2400 × 1444 | Strong cobalt physiological graph with the real 93 bpm reading. |
| `sam-hrv-panel@2x.png` | 2400 × 1444 | Alternative physiological graph and real 48.1 ms reading. |
| `team-rows@2x.png` | 2400 × 442 | Compact glimpse of the two profiles and their measured channels. |
| `source-context@2x.png` | 2400 × 160 | Original recorded-data disclosure to accompany close-up panel crops. |
| `manager-overview-2560.png` | 2560 × 1440 | Complete browser frame, with logo, navigation and recorded-data disclosure. |
| `team-signals-2560.png` | 2560 × 1440 | Complete team signals frame. |
| `sam-hrv-2560.png` | 2560 × 1440 | Complete team signals frame with Sam's HRV selected. |
| `manager-detail-2560.png` | 2560 × 1440 | Complete optional experimental detail view. |

A full 2560 px frame has the application centered in a 1200 CSS-pixel content column. For cinematic product close-ups, the retina component crops preserve much better legibility than scaling the whole desktop down. The retina captures render at device pixel ratio 2; they are not enlarged images.

For a tight graph composition, mask the lower disclosure controls below approximately **y=1065** in a retina signal panel. Retain the person's name, channel name, units, recording-time axis and gap note. Do not mask the manager page's experimental-interpretation line. A persistent **“Recorded demo · UNIVERSE”** film caption should accompany any component crop that excludes the app's original source bar. Film narration should not imply the staged person supplied these recorded readings.

The frames show navigation to the manager preview, opening Alex's details, switching to Team signals, choosing Sam, and choosing Heart rate variability. These interactions were exercised in the browser; the film may cut between those real states.

## Reproduce

From the repository root with the web and API services running:

```sh
neurasign_server_dashboard/.venv/bin/python 'demo video/scripts/capture-dashboard.py'
```

The script deliberately stops if the server is in manual, live or synthetic mode. It does not change application mode or restart playback. It creates normal and retina PNG assets and validates that no writes or browser errors occurred.
