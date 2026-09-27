# Interface direction

NEURASIGN uses retro-futurist editorial minimalism across company access, the company workspace, recorded monitoring and the anonymous model engine.

## Shared visual system

| Role | Value |
| --- | --- |
| Canvas | `#090a09` |
| Raised surface | `#101110` |
| Primary text | `#f0eee8` |
| Secondary text | `#a3a39b` |
| Dividers | `#30322d` |
| Accent | `#ff6b35` |
| Headlines | Arial / Helvetica, large size and tight spacing |
| Metadata | System monospace, short labels |

The shared `Brand` component draws the dot-matrix wordmark as SVG. `SignalOrb` draws a static halftone sphere for the access page. Neither requires an external asset or font request. The sphere is decorative and is not a physiological visualization.

Use orange for the primary action, selection and signal lines. Multiple chart series use orange and neutral tones with explicit labels. Status meanings remain written out. Surfaces use fine rules, minimal corners and space instead of shadows, colored cards or decorative gradients. Keyboard focus is orange and reduced-motion preferences apply globally.

## Information hierarchy

- Company access pairs one visual with the sign-in form. The test account remains one click away; its credentials are available in a disclosure. On mobile, the header access link skips directly to the form.
- Company overview uses a ruled summary strip and flatter person rows. Empty workspaces show the connection steps and an explicit setup action.
- Recorded monitoring keeps people and physiological signals visible. Formula estimates, reference tables and source/change details expand when needed. Secondary examples sit in the **Use cases** menu, which supports keyboard navigation and Escape.
- Model engine uses a narrow four-model selector and one selected-model view. Method, input period, evaluation scope and the distinction between predictions and recorded references remain explicit. Technical provenance and longer explanations expand separately.
- Narrow charts show start and end times to prevent overlapping time labels.

The redesign changes presentation and navigation. It does not change data sources, trained artifacts, model metrics, tenancy, consent, interpretation rules or production boundaries.

## Browser checks

From `neurasign_server_dashboard`, with the local Docker stack running:

```sh
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/browser_controls_smoke.py
.venv/bin/python scripts/browser_manager_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/browser_model_engine_smoke.py
```

Monitoring and control checks share demo state; run those sequentially. Screenshots live in the ignored `artifacts/` directory. The frontend also retains its automated tests, TypeScript checks and production image build.
