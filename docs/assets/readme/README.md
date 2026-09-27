# README presentation assets

These assets make the repository front page readable in GitHub Markdown. They are derived from NEURASIGN's existing brand, actual local application and original film/deck. No original presentation, logo or video was changed.

| Asset | Source and purpose |
| --- | --- |
| `hero.svg` | Editable SVG composition using the supplied principal logo's original path geometry, official cobalt and a decorative wristband illustration. No external fonts, linked images or scripts. |
| `film-preview.gif` | Five seconds from the final 76-second 1080p concept film, beginning at 00:06. 960 px wide, 10 fps; a clickable teaser for the complete film. |
| `pitch-cover.png` | Unmodified first page of the updated 18-slide PDF, rendered at 1200 px. |
| `team-overview.png` | Native browser screenshot of the actual sample company's roster at 2× scale. Contains 36 fictional profiles; no real employee data. |

The README's film preview uses a `picture` source to show the existing static film poster when reduced motion is requested. The full MP4s, captions, PDF and editable PPTX are linked within the repository, preserving its access settings. The film remains a scripted concept; the product screenshots show operational human-reported context.

## Regenerate the derivatives

Run from the repository root with FFmpeg and Poppler installed:

```sh
ffmpeg -hide_banner -loglevel error \
  -ss 6 -t 5 -i "demo video/exports/neurasign-hospital-76s-1080p.mp4" \
  -filter_complex '[0:v]fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3' \
  -loop 0 -y docs/assets/readme/film-preview.gif

pdftoppm -f 1 -l 1 -scale-to 1200 -singlefile -png \
  presentation/NeuraSign_Pitch.pdf docs/assets/readme/pitch-cover
```

For the roster, open the local sample company in Chrome at a 1440 px viewport with device scale factor 2. Take a native element screenshot of `.ops-roster`; leave its data, labels, scrolling region and pagination unchanged. Do not substitute real employee screenshots.

## Review performed

The root README was rendered through GitHub's Markdown API and reviewed in a local browser using GitHub-style Markdown presentation. Checks covered light/dark desktop presentation, a 390 px mobile viewport, image loading, reduced-motion selection, expanded disclosures and local link targets. These are rendering checks, not an end-user usability study.

Original sources: [brand](../../../NeuraSign_Cobalto_logos/LEEME.md), [film](../../../demo%20video/README.md), [pitch PDF](../../../presentation/NeuraSign_Pitch.pdf). Markdown media reference: [GitHub documentation](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files).
