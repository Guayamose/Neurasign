# UNIVERSE-derived replay

The locally imported `replay.json` contains derived temporal features from actual UNIVERSE recordings
`UN_101/Lab1` and `UN_103/Lab1`, mapped to the fictional workers Alex and Aoi.
The cognitive scores inferred from them are not validated scientific labels.

Source: [UNIVERSE, DOI 10.5281/zenodo.10371068](https://zenodo.org/records/10371068)
by Christoph Anders, Sidratul Moontaha, Samik Real, and Bert Arnrich (2023).
License: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
NEURASIGN transforms the raw Empatica recordings into windowed features and personal
reference statistics. Preserve this attribution when sharing the derived data.

Download details, feature units, transformations, calibration choices, missing-data
handling, reproduction commands, and scientific limits are in
[docs/dataset.md](../../docs/dataset.md). The replay metadata contains source-member
checksums and the exact recording selection. Both the imported replay and raw
downloads under `raw/` are ignored by version control. A fresh checkout uses the
synthetic fixture until you run the download/import commands. Raw samples need
not be retained to run the imported replay.
