# Interface direction

The company workspace prioritizes a manager's next action: understand the team, identify open situations, then coordinate work. It uses the official cobalt brand on a quiet, light operational interface. All product text is English.

## Visual system

| Role | Value |
| --- | --- |
| Canvas | `#F5F7FB` |
| Surface | `#FFFFFF` |
| Primary text | `#172338` |
| Secondary text | `#5F6D82` |
| Dividers | `#DFE5EE` |
| Control outlines | `#BDC8D8` |
| Primary action | `#2854E8` with white text |
| Typography | System sans-serif; operational headings around 28–30 px |
| Body and controls | Generally 14–16 px; main controls at least 44 px high |

The `Brand` component selects the supplied dark or light SVG without altering the original logo. No external image/font request is required. Cobalt identifies actions and selection; written labels and icons convey status alongside color. Reduced motion and visible keyboard focus remain supported. Signal explorer and Model engine retain their separate dark research presentation.

## Information architecture

- **Overview:** team-scoped counts, prioritized open situations, then a searchable employee roster. A manager can act on a situation without inspecting every employee. People/Teams grouping, availability filters and 25/50 pagination organize larger lists. The table scrolls within a bounded region, leaving pagination accessible.
- **Person detail:** availability, active tasks, support, qualifications and clear actions. Measurements are protected at the API. The sample company includes labeled illustrative stress/workload/fatigue/readiness indicators; real accounts do not receive invented estimates.
- **People & teams:** searchable employee profiles, team creation, phone enrollment and owner-managed dashboard access. Employee profiles do not require dashboard accounts.
- **Applications:** three entries explain the job and open its working list: Dynamic Task Assignment, Overload Prevention and Shift Handover. Each list has search, team/status filters, pagination, short status labels and a primary creation action. Candidate choices show eligibility reasons; unavailable candidates are optional. Forms progressively reveal only required context.
- **Connections:** phone access, enrollment and data availability. Connection issues are separate from employee availability or support needs.
- **My privacy:** secondary self-sharing controls, separate from daily manager work.
- **Demo & research:** sample workspace, Signal explorer and Model engine. Research inputs never silently enter company workflows.

The sign-in page contains a simple product diagram and a direct sample-workspace action. `/demo` enters the same company UI with 36 fictional profiles across four teams. Its persistent banner identifies the example and offers a return to sign-in.

## Interaction rules

Use short text to remove ambiguity rather than relying on unexplained icons. A state such as “Support requested” includes a meaning; an action such as “Find a person” describes what happens next. Keep technical source details out of ordinary decisions except when they affect interpretation.

Native dialogs support Escape, focus containment and return to their trigger. Closing details preserves list filters. Deep links identify the application and record. The chosen company survives a refresh within the session. Loading, empty, no-results, missing-context, stale-version and failed-save states each offer an appropriate next action. Temporary network interruptions preserve work in progress and label information as last received; revoked access clears it.

No physiological alert or automatic reassignment is implied by an operational label. Matching uses confirmed work context. The manager confirms an assignment, records support actions and accepts responsibility through explicit handover steps.

## Validation limits

The [applications acceptance](applications.md#interaction-and-verification) checks actual API persistence, permissions, search/filter recovery, first setup, keyboard use and responsive layouts at 1440, 768, 390 and 320 pixels. Source review and rendered screenshots supplement those checks.

Automated tasks and our own visual review do not prove that a first-time nontechnical person will understand every step. A separate observed-user session would establish that. Large-roster checks test presentation and scope; they do not remove API pilot bounds or demonstrate backend capacity.
