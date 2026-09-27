# UNIVERSE wrist-only acquisition inventory

Status: expanded wrist-only acquisition complete and independently rechecked from disk. All 26,361 selected files are present for the 24 participants; no selected file is missing or corrupt.

Source: [UNIVERSE record 10371068](https://zenodo.org/records/10371068). Its two complete archives total approximately 20.3 GB. This inventory reads their central directories through bounded HTTP Range requests and sums member sizes without retrieving sensor payloads.

The engine's input scope is Empatica wrist measurements and reference labels. Muse EEG and EEG-derived features are excluded from model inputs and evaluation claims.

## Measured selection sizes

Sizes below use decimal MB (1 MB = 1,000,000 bytes).

| Selection | Files | Compressed member bytes | Extracted member bytes |
| --- | ---: | ---: | ---: |
| HR, IBI, EDA, temperature, acceleration, device metadata/event tags and Task_Labels.csv | 970 | 38,556,298 (38.6 MB) | 273,409,081 (273.4 MB) |
| Same selection plus raw optical BVP | 1,101 | 141,915,634 (141.9 MB) | 556,392,358 (556.4 MB) |

Both selections cover available records from all 24 participant IDs across Lab1, Lab2 and Wild. Coverage in the archive does not imply every participant has every session or every signal. File availability, timestamp alignment, labels and signal quality still need validation after extraction.

## Recording duration and training readiness

The [dataset paper, Data Records section, page 8](https://www.nature.com/articles/s41597-024-03738-7.pdf) explains that the approximately 315-hour headline sums recordings from both devices:

| Device | Controlled task recordings | Uncontrolled recordings | Sum |
| --- | ---: | ---: | ---: |
| Empatica E4 | 60.37 hours | 99.33 hours | 159.70 hours |
| Muse S | 60.30 hours | 94.85 hours | 155.15 hours |

These are the authors' reported durations, not independently measured usable hours in our selected files. The approximately 315 hours are not 315 independent hours of wrist recordings. Raw sessions also contain periods outside the reported controlled-task intervals.

The 141.9 MB selection contains raw signal files and separate Task_Labels.csv questionnaire tables. It is not already aligned or ready for training. Direct inspection of the locally available UN_101, UN_102 and UN_103 Lab1 tables found task names and questionnaire scores but no task start/end timestamps. Raw signals plus these tables alone are therefore insufficient to reconstruct laboratory task boundaries. The paper describes using PsychoPy logs and synchronization to construct the Labeled segments.

Some raw index entries also share a signal filename, byte size and CRC across different paths (including merged recordings). Treat these as duplicate candidates and check actual timestamps/content before counting independent recording duration.

Additional wrist-only representations available in the same ZIP indexes are listed below. Each size includes the separate questionnaire tables and excludes EEG files; these are alternative representations, not additional independent recording hours:

| Selection | Compressed bytes including questionnaire tables | Remaining checks |
| --- | ---: | --- |
| Labeled `e4_*.pickle` signal segments | 812,351,803 (812.4 MB) | Task/label semantics, repeated segments, quality and temporal provenance |
| Preprocessed BVP, EDA and temperature | 271,886,776 (271.9 MB) | Available modalities, authors' preprocessing and segment coverage |
| HRV, EDA and temperature feature tables | 3,912,106 (3.9 MB) | Feature definitions, label mapping, window overlap, coverage and preprocessing leakage |

No representation has yet been audited as a training dataset. The expanded acquisition below includes both the task-aligned wrist representations and the timing records needed to investigate the original signals. The 141.9 MB raw estimate must not be presented as a complete ready-to-train package.

The complete wrist selection is preferred for signal-processing experiments. BVP adds 103,359,336 compressed bytes (103.4 MB). A staged transfer can fetch the smaller selection first and add BVP later; experiments that require the waveform must wait for it.

## Why the complete archives are much larger

The ZIP indexes contain several representations of recordings, including EEG. Summing compressed member sizes gives the following breakdown (decimal GB):

| Archive contents | Compressed size |
| --- | ---: |
| Original Muse files under Raw/Muse | 5.289 GB |
| Segmented, labeled signal files under Labeled | 7.790 GB |
| Processed signal files under Preprocessed | 4.629 GB |
| Other Raw files, mainly stretched/synchronized Muse and Empatica representations | 2.410 GB |
| Original wrist files under Raw/Empatica | 0.142 GB |
| Features, standalone labels and documents | 0.009 GB |

ZIP headers and directory records add approximately 0.018 GB, bringing the two archives to 20.287 GB. The Labeled and Preprocessed totals include multiple modalities; they are not additional independent participants or recording hours.

Every non-directory file under Raw/Empatica in both indexes is included in the 1,101-file wrist-and-label selection: no original wrist file is excluded. Task_Labels.csv files are retained separately from the much larger Labeled signal segments. Using the raw selection means signal cleaning, timestamp alignment and feature extraction remain work for the engine; it is not a ready-to-train table.

Reading both ZIP indexes transferred 9,570,881 bytes (9.6 MB). Metadata lookup and index retrieval took 18.21 seconds in this environment. This is a small connectivity probe, not a guaranteed sustained throughput or full-download completion time. Sensor downloads also incur ZIP-header transfers, request latency and possible retries.

## Local inventory artifacts

Ignored files under `data/universe/` relative to the engine root:

- `UNIVERSE_UN_101_to_UN_112.zip.index.json`
- `UNIVERSE_UN_113_to_UN_124.zip.index.json`
- `download-plan.json`

The plan records selected member paths, archive names, compressed/extracted sizes, ZIP offsets and CRCs. It contains no expanded sensor payloads. Previously downloaded demo recordings remain under `neurasign_server_dashboard/data/universe/`.

## Expanded acquisition

The requested research selection contains 26,361 files: 1,548,431,380 compressed member bytes and 5,331,320,225 extracted bytes. It includes the following available records from the two source archives:

| Representation | Files |
| --- | ---: |
| Original Empatica recordings and device metadata | 1,033 |
| Task questionnaire tables | 68 |
| Study notes | 25 |
| PsychoPy timing and task records | 181 |
| Synchronized/stretched Empatica tables | 46 |
| Labeled wrist signal segments | 20,965 |
| Processed wrist signals | 2,213 |
| Wrist feature tables | 1,830 |

The [engine downloader](../scripts/download_universe.py) supports nested Wild recordings, split laboratory recordings and BVP. It checks cached index size/checksum against the source metadata, combines selected ranges into multipart requests, and rejects non-range responses. Excluded signal payloads are not added to the requested ranges. Files are saved atomically only after verifying decompressed byte size and source ZIP CRC32; local SHA-256 digests are recorded. A resumed run verifies completed files and downloads missing or corrupted members. No pickle file is deserialized during acquisition.

The final completion and integrity report is `data/universe/verification.json`, relative to the engine root. Download integrity does not establish clean independent recording duration, correct model labels or validated inference accuracy; those remain separate experimental checks.

## Completed transfer and verification

- Sensor/data transfer: 1,553,770,426 bytes including ZIP/multipart framing, in 314 requests.
- Elapsed transfer and extraction time: 518.05 seconds; zero failed requests or retries.
- Extracted payload: 5,331,320,225 bytes in 26,361 files.
- Participant coverage: UN_101 through UN_124; available Lab1, Lab2 and Wild records.
- Every file passed source ZIP CRC32 and uncompressed-size checks before being saved.
- A separate `--verify-only` run reread all files from disk and found zero missing or corrupt members, downloading no sensor payloads. All 26,361 SHA-256 digests matched the original download manifest.
- The original transfer report is preserved as `data/universe/download-verification.json`; the original manifest is `data/universe/download-manifest.json`.
- Source recordings, questionnaires, logs and generated manifests remain excluded from Git.
