# One team workspace, three applications

NEURASIGN combines a private team overview with three connected operational applications. They share employees, teams, permissions and saved records. Managers confirm actions; changing a recommendation never silently moves someone's work.

## Try the complete example

Start `docker compose up --build -d` from the repository root, then open **http://localhost:3000/demo**, or choose **Explore the interactive demo** on the sign-in page. This signs into the public local emulator account and opens **Northstar Operations**, an isolated sample company with **36 fictional people across four teams**. No provider key, dataset or wearable is required.

The sample uses the same components and API workflows as a company workspace. Its banner stays visible throughout; actions persist in this example only. Reopening it keeps your changes. A page refresh preserves the chosen company and application record within the session. **Back to sign in** signs out. Production disables sample-company creation and the `/demo` entry route.

1. **Overview:** see people, support requests, unassigned tasks and pending handovers. Open an attention item to act directly, or find a person by name/team. People and Teams views, status filters and pagination support larger rosters.
2. **Dynamic Task Assignment:** open a task, review its requirements and eligible people, select someone, then confirm **Assign**. Start and complete the assignment from its detail panel. Create another task at any time.
3. **Overload Prevention:** open a support case, record a check-in, break, coverage or work adjustment, then resolve it after follow-up. Opening a case from a person's overview preselects that person.
4. **Shift Handover:** choose pending tasks/cases and a named recipient, then send the handover. The recipient reviews and accepts it. Until acceptance, responsibility stays with the sender/current responsible person. Acceptance does not change a task's assigned employee.

The one-account sample includes self-addressed example handovers so the entire acceptance step can be demonstrated locally. Real workspace handovers support separate sender and recipient accounts; acceptance tests exercise two authenticated accounts.

## What drives each application

| Application | Inputs | Saved outcome |
| --- | --- | --- |
| Dynamic Task Assignment | Team, qualifications, confirmed availability, current tasks, task limit and open support cases | An explicit assignment and its lifecycle |
| Overload Prevention | A human-reported concern, person, category and priority | Support actions, follow-up and resolution |
| Shift Handover | Pending work, a recipient with team access and an optional note | A tracked transfer of responsibility on acceptance |

A candidate is ineligible if availability or required context is missing, qualifications do not match, they are busy/unavailable, they have reached their task limit, or they have an open support case. The interface gives reasons and offers **Edit work context**. Operational matching is a transparent rules-based ranking, not an AI confidence percentage or a health clearance. A missing context field never silently becomes “available”.

**Overload Prevention currently manages reported concerns.** It does not automatically diagnose overload from received physiology. Real employee stress, workload, fatigue and readiness predictions are not connected to these workflows yet. The sample person's four state indicators are explicitly **illustrative estimates**. Research models run separately at `/models`; recorded/synthetic signal exploration and the optional Jev/Gemini incident example live at `/signals`.

## Manager privacy and access

Owners and managers receive identity, permitted work context, actions and connection metadata within their company/team scope. Their roles do **not** grant access to physiological values. The API redacts measurements from the dashboard payload and denies direct history/observation requests with 403. Browser hiding is not the boundary.

Legacy employee accounts can access their own shared measurements. A stored, explicit `can_view_measurements` capability can grant appropriately scoped measurement access; the application has no capability-granting UI. This is an implemented access policy, not a certification of legal compliance.

Company/team checks apply to every workflow read and write. Assignment rechecks current eligibility. Version checks reject stale edits; idempotency keys prevent duplicate effects on retries. Only the named recipient can accept a handover. A handover whose captured work changed must be canceled and recreated after review.

## First use with a real company

Create a company and use **People & teams → Create team → Add employee**. Confirm each employee's qualifications, availability and task limit using their overview's **Edit work context** action. Then create a task or support case in Applications. Empty and missing-context states explain the next action without inventing readings or employee states.

Use **Connect phone** for QR enrollment. Connection status is separate from operational availability: a phone receiving data does not mean an employee is available, recovered or fit for duty. Phone setup does not require an employee dashboard account.

## Interaction and verification

The company UI uses light surfaces, the official cobalt logo, readable labels, familiar icons and written status meanings. Each application has search, team/status filters, bounded lists and one clear primary action. Details and forms use keyboard-accessible dialogs; list filters remain when they close. Temporary refresh failures show an interruption notice and preserve draft input; rejected access removes protected data.

The UI paginates already-authorized snapshots. The API's pilot limits remain explicit; this is not a capacity claim for hundreds of active wearables. Automated acceptance exercises 80 real local profiles, 40 scoped employees, all three persisted workflows, blank-company setup, permission revocation, mobile layouts and failed-save recovery. It cannot establish first-time human usability without actual participants.

- [API contract](applications-contract.md)
- [Phone enrollment and team access](phone-onboarding.md)
- [Verification record](verification.md)

Run the local end-to-end acceptance with the Docker stack, Chrome and Playwright installed:

```sh
.venv/bin/python scripts/browser_applications_smoke.py
.venv/bin/python scripts/browser_sample_workspace_smoke.py
```

The script creates isolated disposable companies and accounts in local emulators, uploads explicitly labeled test data and never calls a provider or cloud deployment. Results and screenshots stay under ignored `artifacts/`.
