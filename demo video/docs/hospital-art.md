# Hospital film: original vector environment

The 76-second revision also adds `src/hospital/Workplaces.tsx`: three original 600 × 440 vector sets for construction sites, industrial operations and control rooms. They appear in the wider-purpose section at 56–71 seconds, after the hospital example. The crane, industrial robot and control display have subtle deterministic movement. These are illustrative workplace environments, not recordings or claims of deployed integrations.

`src/hospital/Environment.tsx` contains original SVG illustrations. The illustration geometry uses no photographs, image generation, app screenshots, icon packs, or third-party art. The composition uses the Manrope font; see [third-party notices](third-party-notices.md). The root composition supplies an outer `<svg viewBox="0 0 1920 1080">`; exported components return groups that can be translated, scaled, panned, or layered.

## Stage contract

| Component | Coordinates and layering |
| --- | --- |
| `HospitalExterior({frame})` | Full 1920 × 1080 view. Hospital spans x=352–1794, y=218–819. Emergency canopy/sign occupies x=1132–1835, y=521–625. Entry doors occupy x=1240–1671, y=607–819. Sidewalk is y=819–880; road begins below y=880. Keep the main headline in the open upper band, y=35–190. |
| `HospitalInterior({frame, doorOpen, variant})` | Full scene. Rear wall/floor junction is y=749. Open foreground accommodates character feet at y=900–1000. Sliding entry occupies x=25–498, y=243–786. Door leaves slide apart as `doorOpen` moves from 0 to 1. Exterior scenery remains visible through the opening. |
| Interior clinical bay | BAY 02 door occupies x=811–1077, y=321–750. The deep corridor spans x=516–754. These positions support an arrival moving left to right while retaining recognizable environmental cues. |
| Interior waiting area | Arrival/team variants: seats occupy x=1270–1698, ending at y=752; framed art occupies x=1274–1679, y=337–495; planter is centered at x=1800, floor y=751. No seated people are built in. |
| Interior station | Station variant replaces seating with a reception counter at x=1204–1829, y=606–794. Monitor occupies x=1372–1603, y=430–575. A nurse can stand behind the counter near x=1650, feet around y=765, or in front at x=1400, feet around y=960. |
| `Stretcher({frame, children})` | Local bed body occupies x=77–680. Mattress surface is around y=20; chassis reaches y=264; wheels touch y=305; shadow is centered at y=310. The IV stand extends to y=-145. Children are drawn after the mattress and before the front rails. The root places the patient inside this layer with `translate(82 -146) scale(.99)`. Avoid clipping to 700 × 320 because the IV stand extends above zero. |

## Visual system

- Cream `#F7F6F2`, navy `#14213B`, cobalt `#4263EB`, powder blue `#E7EDFF`.
- Restrained warm ochre, soft teal, glass blue, and cream/stone architecture.
- Solid shapes, selective outlines, limited highlights; no gradients.
- Depth comes from layered architecture, a perspective corridor, floor lines, the canopy shadow, seating hardware, and small cast shadows.
- Exterior trees and indoor plants move subtly with `frame`. The clock's second hand and stretcher wheels also animate from `frame`.
- Pass a frozen frame to a stationary stretcher so its wheels do not spin while parked.
- Reception monitor is an illustrative environmental prop, with no patient name, numeric vital reading, or diagnostic conclusion. Use the product scene elsewhere for specific software claims.

## Suggested character blocking

Arrival: open the doors first, then translate the stretcher rightward across the foreground. Account for its scale when aligning floor contact: scene floor is `translateY + 305 × scale`. Draw staff above the environment and place the patient through the stretcher's `children` layer so the near rail remains in front of the blanket. The patient placement is `translate(82 -146) scale(.99)` in local stretcher coordinates.

Team: keep two nurses in the central foreground, x=650–1100, so seating at the right and the care door remain legible. Station: place the manager right of center, with hands and face clear of the environmental monitor and counter. All variants keep the upper band comparatively quiet for concise headline typography.

## Verification

TypeScript compilation passed. The exterior, arrival interior with partly open doors, station interior, and stretcher were rendered independently in Chrome at 1920 × 1080 and visually inspected. Door clipping, signage, palette, environment placement, and moving-wheel geometry were checked without changing the root composition.
