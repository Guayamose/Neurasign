# Manager access and signal preview

The company workspace now enforces manager privacy on the server. Owners and managers see permitted people, operational context, tasks, support cases and handovers within their company/team scope. Their roles alone do not grant access to physiological measurements.

The dashboard response redacts measurements; direct history and observation requests return 403. Legacy employee accounts retain access to their own measurements. A separate explicit `can_view_measurements` capability controls scoped measurement access; there is no grant UI. See the [applications guide](applications.md#manager-privacy-and-access) and [API contract](applications-contract.md).

In the local sample company at `/demo`, a person's four state indicators are explicitly scripted illustrative estimates. Real company profiles do not receive those example estimates. The trained research models remain separate at `/models`.

## Research presentation at `/signals#manager`

**Manager preview** in the Signal explorer retains named fictional profiles, derived indices and interpretation history while omitting the physiological charts displayed in **Team signals**. `toManagerView` builds a limited presentation object rather than spreading the original signal object.

That particular local research tab is still a browser presentation boundary: its containing signal explorer receives the original demo snapshot. Its workload/fatigue/readiness indices are the existing illustrative formulas, not newly trained models. “Review suggested” uses workload ≥70, fatigue ≥60 or readiness <45; “No flag” means no threshold fired, not that a person is safe or fit for duty. Source and unavailable states remain visible. The route is disabled in production.

The company API's new access policy is separate from this legacy research preview. Neither a preview nor measurement redaction establishes legal compliance or clinical/fitness-for-duty validity.

## Verify

```sh
cd apps/web && npm test
# From neurasign_server_dashboard/ with the local stack running:
.venv/bin/python scripts/browser_manager_smoke.py
.venv/bin/python scripts/browser_applications_smoke.py
```

The first browser script checks the local signal presentation. The applications script uploads a known test measurement, checks manager payload redaction and direct endpoint denial, exercises real workflow writes and verifies removal of access during an open browser session.
