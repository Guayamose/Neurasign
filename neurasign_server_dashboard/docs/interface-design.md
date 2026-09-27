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

The workspace answers four questions in order: how much data is arriving, what needs connection help, which teams are affected, and what to do next.

- **Overview** starts with clickable counts scoped to the chosen team: employees, recent wearable data, connection help and paused sharing. Recent data can include streamed or synced readings; it does not imply every device streams continuously.
- **Connection attention** groups permissions, delayed feeds and incomplete setup. The count is unique people, including partial failures when another signal remains current. Every affected row explains the next step. Unsupported device capabilities are informational; period summaries and paused sharing alone create no alert.
- **Your workforce** offers All employees, Connection help, By team and Sharing paused. Name/team search, data-status filters and 25/50 pagination work together. Default ordering puts objective connection issues first, then names; it is not a health or performance ranking. Team rows show coverage and drill into the whole selected team. Counts reflect authorized data and may overlap: a person can have recent heart-rate data and a missing permission for another signal.
- **Employee details** open only on request in a native modal side panel. Escape, Back to list and the close button restore focus without losing list filters, page or scroll position. Polling retains the same employee; removal from the filtered result closes the panel and returns focus. Paused sharing hides measurements and receipt times.
- **People & teams** puts the searchable employee roster first. Creation and dashboard-account access expand separately. An overview setup action lands on the exact employee, even when names are duplicated.
- **Connections** separates authorized access from actual uploads. Search people/phones, filter Allowed/Revoked access and paginate 25/50 records. Upload time is hidden for paused sharing. Personal gateway credentials are an advanced disclosure.
- **My privacy** is secondary to daily team operations. **Demo & research** contains recorded examples and Model engine, so research demonstrations are distinct from the company workspace.
- Company access retains a clear sign-in form, password visibility, test-account shortcut and mobile form anchor. Recorded examples and models preserve their source labels, evaluation context and existing interpretation rules.

Pagination organizes records already authorized and returned by the API. It is client-side presentation, not server pagination or a claim of production capacity. The current API still has a 100-employee pilot creation limit. Browser fixtures with 200 employees and 137 connections test layout and interaction; production support for hundreds also needs backend limits, bounded queries and load testing. API access rules, model artifacts, inference, consent and production boundaries are unchanged.

## Browser checks

From `neurasign_server_dashboard`, with the local Docker stack running:

```sh
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/browser_controls_smoke.py
.venv/bin/python scripts/browser_manager_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/browser_large_team_smoke.py
.venv/bin/python scripts/browser_connections_smoke.py
.venv/bin/python scripts/browser_model_engine_smoke.py
.venv/bin/python scripts/onboarding_smoke.py
```

Monitoring and control checks share demo state; run those sequentially. The large-team check intercepts browser responses with 200 synthetic people across eight teams and blocks company writes; it does not seed employee measurements. Screenshots live in ignored `artifacts/`. Frontend tests cover filtering, sorting, pagination, partial-signal attention, independent legacy/canonical feeds, freshness, paused sharing and count/filter consistency alongside existing proxy and research boundaries.
