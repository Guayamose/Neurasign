# Live-action footage ledger

Reviewed and downloaded on 2026-09-27. These are real stock clips, not generated people. The selected source is filmed independently of NEURASIGN and does not depict a real customer, product integration test, or a measured physiological state.

The selected item and both supporting candidates explicitly show the **Mixkit Stock Video Free License** in their own download panels. This was checked separately from the site's structured metadata: two other attractive smartwatch clips had restricted personal-use licenses and were excluded.

- [License](https://mixkit.co/license/#videoFree)
- [Complete Free License text](https://mixkit.co/license/modal/videoFree/)
- [User terms](https://mixkit.co/terms/)

The Free License permits incorporation into edited commercial films and marketing videos. Attribution is optional; suggested production credit: **Stock footage: Mixkit.** Keep original footage files outside public Git history; distribute the edited NEURASIGN film rather than a stock-media collection. The footage license does not imply brand or performer endorsement.

## Selected: one consistent human setting

**A person working on a laptop, close up** — Mixkit item 1827.

- Source page: https://mixkit.co/free-stock-video/a-person-working-on-a-laptop-close-up-1827/
- Provider credit: Mixkit. The current source page does not identify an individual contributor; no photographer name has been inferred.
- Exact download: https://assets.mixkit.co/videos/1827/1827-1080.mp4
- Local file: `public/footage/workspace-watch-1827.mp4`
- Format verified with ffprobe: 1920 × 1080, 24000/1001 fps, 10.552208 seconds, 35,663,282 bytes. No audio stream.
- SHA-256: `d843619d58a015228aa67095f225d5de0fbddce0e3a88963316c8ba41554159b`
- Re-fetch and verify: `python3 scripts/fetch-footage.py`

Visual inspection covered a one-second contact sheet plus full-size frames at 4.0, 8.5, 8.8 and 9.3 seconds. One anonymous person sits at a wooden desk, sets down coffee, types and checks a black smartwatch. Soft natural light and a consistent room support the realistic product-film direction.

Suggested source trims:

| Purpose | Source time | Framing notes |
| --- | --- | --- |
| Work opening | 2.6–6.1 s | Typing, wearable and coffee. `crop=1536:864:384:216` excludes the laptop logo on the left in the inspected sequence. |
| Wearable insert | 8.6–9.6 s | Person raises wrist. `crop=1536:864:384:0` preserves the upward motion. The lower keyboard is intentionally cropped. |

The watch moves substantially: its screen center is approximately (1490, 750) at 8.5 s, (1480, 435) at 8.8 s, and (1600, 40) at 9.3 s in the 1920 × 1080 source. A tight static bottom crop will lose it during the raise. Review the final crop through the whole selected range. Laptop branding must stay outside the composition. No rendered readings should be presented as originating from this stock actor or watch.

## Supporting candidates, not selected for the style sample

These were downloaded and visually inspected but are omitted from the selected edit to keep one person and setting. They remain local only.

### Hands of a girl working on a computer — 4938

- Source: https://mixkit.co/free-stock-video/hands-of-a-girl-working-on-a-computer-4938/
- Provider: Mixkit; individual contributor not identified on the current source page.
- Download: https://assets.mixkit.co/videos/4938/4938-1080.mp4
- File: `public/footage/hands-of-a-girl-working-on-a-computer-4938.mp4`
- 1920 × 1080, 24000/1001 fps, 10.218542 s, 30,246,749 bytes.
- SHA-256: `a9d86c17a21d8c77153f5b9cddb3b018c5caebb3eac7b230f8458fbd33a04743`
- Useful trim: 0.5–4.5 s. Natural warm wood, typing hands, notebook and phone. Bracelets are jewelry, not a demonstrated wearable sensor. No face or prominent laptop logo visible in inspected frames.

### Close-Up of Hands Typing and Using Mouse — 101553

- Source: https://mixkit.co/free-stock-video/close-up-of-hands-typing-and-using-mouse-101553/
- Provider: Mixkit; individual contributor not identified on the current source page.
- Download: https://assets.mixkit.co/uycpu8pjz50sr5x6rgeh28teml1k
- File: `public/footage/close-up-of-hands-typing-and-using-mouse-101553.mp4`
- 1920 × 1080, 24000/1001 fps, 9.217542 s, 35,522,673 bytes.
- SHA-256: `5b4aa42b66bb70b68ba16a3e49faa0c9e93c639f726b659ae9c09bcf0ffbb61b`
- Useful trim: 4.5–8.0 s. Warm keyboard-to-mouse move. The opening contains a monitor logo near the upper edge, so avoid it or crop below it. This setup is more colorful than the selected scene.

The Astra reference video is a creative reference only. No frames, audio or footage from it are included in the deliverable.
