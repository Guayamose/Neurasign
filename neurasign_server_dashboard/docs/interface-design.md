# Interface direction

NEURASIGN combines the approved Cobalto identity with a readable operational interface. Company access keeps an editorial cover; everyday monitoring uses compact headings, explicit controls and searchable lists.

## Shared visual system

| Role | Value |
| --- | --- |
| Canvas | `#0D1321` |
| Raised surface | `#131A2A` |
| Primary text | `#F5F7FC` |
| Secondary text | `#B0BCD0` |
| Dividers | `#38465F` |
| Control outlines | `#65748F` |
| Primary action | `#2854E8` with white text |
| Dark-surface accent | `#6C8BFF` |
| Operational headings | Arial / Helvetica, usually 34–40 px |
| Main copy | 14–16 px; supporting metadata at least 12 px |
| Main controls | At least 44 px high |

The shared `Brand` component uses the approved horizontal SVG without recoloring or changing its proportions. The original dark and light assets and brand tokens are copied into `public/brand/`; Docker includes this directory in its standalone image. The favicon uses the approved symbol. No external image or font request is required. `SignalOrb` remains a decorative halftone sphere on the access page, not a physiological visualization.

Use cobalt for actions, selection and signal lines. Chart series also use labeled neutral tones. Status meanings are written out; users do not need to distinguish colors to understand them. Fine rules and restrained surfaces keep the interface calm. Keyboard focus uses light cobalt and reduced-motion preferences apply globally.

## Information hierarchy

- Company access shows a clear sign-in form, password visibility, a local test-account shortcut and a mobile link directly to the form.
- Company overview uses a summary strip and a roster. Search by name/team, filter by team or data status, sort by name or arrival, and show 25 or 50 people per page. **View signals** opens the selected person's measurements; **Back to list** restores focus to their button. Selection survives polling, but clears on navigation or when filters exclude the person.
- Data status describes sharing and signal availability, not a person's wellbeing. Period summaries and permission requirements stay distinct from delayed measurements. Paused sharing hides measurements and arrival times. Recent uploads do not make old measurements current.
- People & teams has the same search/paging pattern while preserving invitation, phone-pairing, sharing and revocation controls.
- Recorded monitoring keeps people and physiological signals visible. Formula estimates, reference tables and provenance expand when needed. Secondary examples sit in the **Use cases** menu, with keyboard navigation and Escape.
- Model engine uses a four-model selector and one selected-model view. Method, input period, evaluation scope and predictions versus recorded references remain explicit. Technical details expand separately.
- Mobile rosters become labeled rows with full-width actions; narrow charts use start/end time labels to avoid overlap.

Pagination organizes records already authorized and returned by the API. It is client-side presentation, not server pagination or a claim of tested production capacity. API access rules, model artifacts, inference, consent and production boundaries are unchanged.

## Browser checks

From `neurasign_server_dashboard`, with the local Docker stack running:

```sh
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/browser_controls_smoke.py
.venv/bin/python scripts/browser_manager_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/browser_large_team_smoke.py
.venv/bin/python scripts/browser_model_engine_smoke.py
```

Monitoring and control checks share demo state; run those sequentially. The large-team check intercepts browser responses with 100 synthetic people and blocks company writes; it does not seed employee measurements. Screenshots live in ignored `artifacts/`. Frontend tests cover filtering, stable sorting, pagination and source/freshness edge cases alongside existing proxy and research boundaries.
