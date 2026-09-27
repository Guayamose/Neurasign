# Third-party notices — hospital film

## Manrope typography

The film composition uses the Manrope typeface through the pinned `@fontsource/manrope` dependency. Copyright 2019 The Manrope Project Authors: https://github.com/sharanda/manrope.

Manrope is distributed under the **SIL Open Font License 1.1**. The editable archive includes its complete copyright and license notice at `docs/licenses/Manrope-OFL.txt`, copied without modification from the installed font package. The font is installed by `npm ci`; it has not been modified. Original character and environment shapes do not depend on a third-party illustration or icon library. The composition's typography is a separate font dependency.

## Rendering and development software

The editable source uses Remotion, React, TypeScript and the related packages pinned in `package-lock.json`. Their implementation code is not bundled in the editable archive; install it with `npm ci`. Each dependency retains its own license and notices in the installed package.

Remotion uses its own software license. A copy of the installed version's full license is included at `docs/licenses/Remotion-LICENSE.md`; consult it for the terms applicable to your use and organization. This notice does not grant additional rights to Remotion or other dependencies. Official project: https://www.remotion.dev/.

Google Chrome and FFmpeg are external production tools and are not distributed in the archive. The Python audio production scripts use NumPy and SciPy when audio is rebuilt; their packages are not included.

## Narration, sound and artwork

The English narrator is the **Iapetus stock synthetic voice**, generated with Google Gemini API model `gemini-3.8-flash-tts` using the project's authorized credential. It is not a cloned person or a recorded performer. The source WAVs and safe production metadata are included for local reassembly; credentials are excluded. Rendering the supplied mix makes no API call. Generation provenance and timings are documented in `hospital-audio.md` and `public/audio/hospital-narration.json`.

Music and editorial sound effects are original local synthesis, with no third-party loops or stock recordings. Characters, environments and props are original editable SVG artwork. The NEURASIGN logo copies come from the user's supplied brand assets; their inclusion does not transfer ownership of the mark.

The hospital film contains **no Mixkit/Pexels footage**, no footage or sound from the Astra reference, no stock character art and no real employee or patient information. The previous live-action sample and its media are excluded from this archive.
