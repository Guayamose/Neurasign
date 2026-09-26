# Synthetic demonstration recording

`replay.json` is generated deterministically by `scripts/generate_fixtures.py`.
It contains no UNIVERSE participant observations. Every value is a synthetic
illustration used to exercise the common inference, routing, and orchestration
pipeline. The **developer guided-scenario API** selects this fixture at 30× replay for
a repeatable capacity-change trajectory. Ordinary incident examples preserve the
selected monitoring source. Human diagnosis review and architecture approval are
explicit actions; the interactive story has no guaranteed completion time.

`incident.json` supplies fictional operational evidence to actual Gemini model
calls. Sample inputs are separate from generated outputs. Each returned artifact
identifies real Gemini execution or an explicit local fallback.

The separate `data/universe/replay.json` contains real recorded features.
See [docs/dataset.md](../../docs/dataset.md) for provenance and limitations.
