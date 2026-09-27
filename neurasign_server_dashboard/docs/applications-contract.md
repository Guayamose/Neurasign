# Operational applications contract

All routes require a Firebase dashboard identity. Applications are restricted to owners and managers; managers can read and mutate only assigned teams. Neither role grants physiological measurement access. Application inputs are operational context recorded by a human; no model consumes employee measurements.

Base: `/api/v1/organizations/{org}/applications`. Responses are direct JSON objects; successful creates and transitions return HTTP 200. Invalid access returns 403, invalid state/version/request reuse returns 409, invalid input returns 422. IDs are hexadecimal strings. Dates in responses are epoch seconds; task due dates in requests are timezone-aware ISO strings.

`GET <base>` returns `{organization:{id,name,is_demo,demo_label},permissions:{can_manage,can_create_cases,can_accept_handovers},people,teams:[{id,name}],recipients:[{id,name,role,team_ids}],tasks,cases,handovers,server_time}`.

A person is `{id,name,team_id,skills:string[],availability:'available'|'busy'|'unavailable'|'unknown',max_active_tasks:number|null,active_task_count,open_case_count,context_note,context_provenance:'human_reported'|'demo'|'missing',context_version,can_edit,status:'support_needed'|'check_in'|'available'|'unavailable',provenance:'human_report'|'demo'|'none',interpretation}`. `interpretation` is null in real companies. Only the isolated sample company may return `{stress:{score,level},workload:{score,level},fatigue:{score,level},readiness:{score,level},source:'illustrative',updated_at}`. Stress/workload/fatigue levels are low/moderate/elevated; readiness levels are limited/fair/good; no measured or validated employee inference is implied.

`PATCH <base>/people/{id}/context`: `{version,skills,availability,max_active_tasks,context_note?}`. Initial version is 0. Skills are trimmed/lowercased/deduplicated. Task limit is 1–20. Returns the person.

Task: `{id,title,description,team_id,required_skills,priority,status,assignee_id,responsible_member_id,due_at,created_by,created_at,updated_at,version,provenance}`. Status: open, assigned, in_progress, completed, canceled. Priority: low, normal, high, urgent. Provenance: human_report or demo.

- `POST /tasks`: `{request_id,title,description?,team_id,required_skills,priority,due_at?}`.
- `GET /tasks/{id}/candidates`: `{task_id,version,candidates:[{employee_id,name,eligible,score:number|null,reasons:string[],missing:string[],active_task_count,open_case_count}]}`. Score is a transparent operational ranking, not confidence. Missing context, unavailable/busy, missing required skills, a reached task limit or any open support case prevents assignment.
- `POST /tasks/{id}/assign`: `{request_id,version,employee_id}`. Rechecks eligibility atomically; requires an open task.
- `POST /tasks/{id}/transition`: `{request_id,version,action:'start'|'complete'|'cancel',note?}`. Start requires assigned, complete requires assigned or in_progress, cancel requires nonterminal status.

Case: `{id,employee_id,team_id,category,summary,priority,status,actions:[{id,kind,note,actor_id,created_at}],resolution,responsible_member_id,version,provenance,created_at,updated_at}`. Status: open, in_progress, resolved. Category: workload, break_request, coverage, other.

- `POST /cases`: `{request_id,employee_id,category,summary,priority}`. Team comes from the employee.
- `POST /cases/{id}/actions`: `{request_id,version,kind:'check_in'|'break'|'coverage'|'adjust_work'|'note',note}`. Adds an action and marks in_progress.
- `POST /cases/{id}/resolve`: `{request_id,version,note}`. Requires a prior recorded action; terminal cases cannot change.

Handover: `{id,title,team_id,sender_member_id,recipient_member_id,task_ids,case_ids,note,status,accepted_at,version,created_at,updated_at,can_accept,can_cancel,provenance}`. Status: pending, accepted, canceled.

- `POST /handovers`: `{request_id,title,team_id,recipient_member_id,task_ids,case_ids,note?}`. Requires at least one pending work item in this team. An item cannot belong to multiple pending handovers.
- `POST /handovers/{id}/accept`: `{request_id,version}`. Only the named recipient may accept. Rechecks current recipient team permission, pending work states and captured work versions. Atomically transfers `responsible_member_id`, preserving employee assignee/subject IDs.
- `POST /handovers/{id}/cancel`: `{request_id,version}`. Sender or owner only. Cancel and recreate if included work changed.

Every POST request ID is 8–128 characters `[A-Za-z0-9_-]`, scoped to actor and operation. Repeating identical input returns the saved result; different input with the same ID conflicts. Versions increment on mutation. Context PATCH uses optimistic versioning. Snapshot and candidate GETs are read views; assignment always rechecks current data. Persistence uses organization-scoped documents and a bounded manifest (300 tasks, 300 cases, 150 handovers).

Text limits: title 120, task description 1000, case summary 500, action/resolution/context note 500, handover note 1000. Skills: at most 30 values, each 1–60 characters. A case may contain 50 actions; a handover may include 30 tasks and 30 cases.

`POST /api/v1/applications/demo` is available only to the authenticated built-in local emulator account, never in production. Returns `{organization,created}`. Creates one separate reusable sample company with 36 fictional employee profiles, four teams, seeded work and clearly illustrative states. Repeated calls preserve edits. Seed version 2 updates only untouched original sample labels on an explicit request; it preserves work that a human has changed. No measurements or phone credentials are seeded. The current real company is not modified. Self-addressed sample handovers allow explicit acceptance by the one real signed-in test account.

Company dashboard members expose `measurements_access`/`can_view_measurements` and `connection:{status,current_count,issue_count,last_received_at,issue_kind,next_step}`. Without own-employee access or the explicit stored measurement capability, physiological features are null, latest is null, signals is empty, and history/observation endpoints return 403. Receipt metadata remains visible within team scope while sharing is enabled; pausing hides the connection receipt timestamp. Period summaries and unsupported capabilities do not count as connection issues. Explicit capability does not bypass team-at-capture restrictions. No broad capability grant UI is provided.
