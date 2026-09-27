# Individual manager overview

Open `/demo#manager`, or choose **Manager overview** beside **Team overview**.

The manager needs to understand each person's interpreted situation. This view retains each named demo profile, conclusion, experimental workload/fatigue/readiness indices, source and interpretation history. It omits the physiological values, reference baselines and sensor charts displayed in the detailed overview.

## Data and interpretation

`toManagerView` projects the existing demo snapshot into a limited presentation object. It copies selected identity fields, derived indices and derived history; it never spreads worker or signal objects. The component receives this object rather than the physiological snapshot.

The values come from the same demo interpretation used in Team overview, including for a team with only one person. These are the existing experimental demo estimates, not a newly trained or validated model.

A **Review suggested** flag uses the existing demo thresholds: workload at least 70, fatigue at least 60, or readiness below 45. **No flag** means none of these rules fired; it is not a declaration that an employee is safe or fit for duty. Confidence is used only as an availability gate and is not displayed as a validated accuracy percentage.

Disconnected, stale, missing, insufficiently supported or invalid interpretations show **Unavailable**, without displaying previous index values as current. Live inputs also require a recent reading and an established personal reference. Manual mode is explicitly identified as presenter-set values and does not inherit recorded history.

The UI is occupation-neutral. It cannot be used as medical, safety or fitness-for-duty clearance for construction, hospitals or air traffic control. Those contexts require validation and appropriate human procedures beyond this demo.

## Privacy and authorization

Hiding measurements while retaining named conclusions is a product distinction, not automatic anonymisation or GDPR compliance. Conclusions that reveal physical or mental health can themselves be health data. See [GDPR Article 4(15), Article 9 and Recital 35](https://eur-lex.europa.eu/eli/reg/2016/679/oj) and the [EDPB's guidance on lawful processing](https://www.edpb.europa.eu/sme/be-compliant/process-personal-data-lawfully_en).

This tab is a demo presentation boundary only. The containing demo still receives its original snapshot through `/api/state` and the WebSocket. Existing company managers can still access physiological measurements within their granted teams through the dashboard, member history and observation endpoints. `/demo` remains disabled in production.

A production interpretation-only manager role needs an appropriately authorised server response containing permitted identity and conclusion fields, with physiological endpoints denied to that role. The legal basis, sensitive-data conditions, purpose, employee rights, retention and applicable workplace requirements need a separate assessment. Neither the UI nor the current sharing switch establishes these conditions.

## Verification

```sh
cd apps/web && npm test
# From neurasign_server_dashboard/:
.venv/bin/python scripts/browser_manager_smoke.py
```

Projection tests cover named conclusions, exact demo thresholds, field exclusion, manual provenance and unavailable states. Browser checks cover named profiles, person selection, interpreted charts, filters, source consistency, absence of raw units and responsive navigation. They do not certify production access controls or GDPR compliance.
