export type ApplicationId = "hub" | "tasks" | "prevention" | "handover";
export type ApplicationApi = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
export type Priority = "low" | "normal" | "high" | "urgent";
export type Provenance = "human_report" | "demo";
export type ApplicationTeam = { id: string; name: string };
export type OperationalPerson = {
  id: string; name: string; team_id: string | null; skills: string[];
  availability: "available" | "busy" | "unavailable" | "unknown";
  max_active_tasks: number | null; active_task_count: number; open_case_count: number;
  context_note: string; context_provenance: "human_reported" | "demo" | "missing";
  context_version: number; can_edit: boolean;
  status?: "support_needed" | "check_in" | "available" | "unavailable";
  provenance?: "human_report" | "demo" | "none";
  interpretation?: { stress: { level: string; score: number }; workload: { level: string; score: number }; fatigue: { level: string; score: number }; readiness: { level: string; score: number }; source: "illustrative"; updated_at: number } | null;
};
export type ApplicationTask = {
  id: string; title: string; description: string; team_id: string; required_skills: string[];
  priority: Priority; status: "open" | "assigned" | "in_progress" | "completed" | "canceled";
  assignee_id: string | null; responsible_member_id: string | null; due_at: number | null;
  created_by: string; created_at: number; updated_at: number; version: number; provenance: Provenance;
};
export type SupportAction = { id: string; kind: string; note: string; actor_id: string; created_at: number };
export type SupportCase = {
  id: string; employee_id: string; team_id: string; category: "workload" | "break_request" | "coverage" | "other";
  summary: string; priority: Priority; status: "open" | "in_progress" | "resolved";
  actions: SupportAction[]; resolution: string | null; responsible_member_id: string | null;
  version: number; provenance: Provenance; created_at: number; updated_at: number;
};
export type ShiftHandover = {
  id: string; title: string; team_id: string; sender_member_id: string; recipient_member_id: string;
  task_ids: string[]; case_ids: string[]; note: string; status: "pending" | "accepted" | "canceled";
  accepted_at: number | null; version: number; created_at: number; updated_at: number;
  can_accept: boolean; can_cancel?: boolean; provenance: Provenance;
};
export type ApplicationRecipient = { id: string; name: string; role: string; team_ids: string[] };
export type ApplicationsData = {
  organization: { id: string; name: string; is_demo: boolean; demo_label?: string };
  permissions: { can_manage: boolean; can_create_cases: boolean; can_accept_handovers: boolean };
  people: OperationalPerson[]; teams: ApplicationTeam[]; recipients: ApplicationRecipient[];
  tasks: ApplicationTask[]; cases: SupportCase[]; handovers: ShiftHandover[]; server_time: number;
};
export type TaskCandidate = {
  employee_id: string; name: string; eligible: boolean; score: number | null;
  reasons: string[]; missing: string[]; active_task_count: number; open_case_count: number;
};
export type TaskCandidates = { task_id: string; version: number; candidates: TaskCandidate[] };

export const applicationInfo = {
  tasks: { title: "Dynamic Task Assignment", short: "Tasks", description: "Match the work to an available, qualified person.", action: "Create task", steps: ["Define the task", "Review candidates", "Confirm assignment"] },
  prevention: { title: "Overload Prevention", short: "Support cases", description: "Record a concern. Agree on support. Follow through.", action: "Open support case", steps: ["Record a concern", "Take action", "Confirm resolution"] },
  handover: { title: "Shift Handover", short: "Handovers", description: "Pass responsibility on, without losing pending work.", action: "Create handover", steps: ["Select pending work", "Choose recipient", "Recipient accepts"] },
} as const;

export const statusLabels: Record<string, string> = { open: "Needs review", assigned: "Assigned", in_progress: "In progress", completed: "Completed", canceled: "Canceled", resolved: "Resolved", pending: "Awaiting acceptance", accepted: "Accepted" };
export const categoryLabels = { workload: "Workload concern", break_request: "Break request", coverage: "Coverage needed", other: "Other concern" };
export const actionLabels: Record<string, string> = { check_in: "Check-in", break: "Break agreed", coverage: "Coverage arranged", adjust_work: "Work adjusted", note: "Follow-up note" };
export const availabilityLabels = { available: "Available", busy: "Busy", unavailable: "Unavailable", unknown: "Not confirmed" };
export const isTaskPending = (task: Pick<ApplicationTask, "status">) => !["completed", "canceled"].includes(task.status);
export const isCasePending = (item: Pick<SupportCase, "status">) => item.status !== "resolved";
export function provenanceLabel(value: string) { return value === "demo" ? "Demo scenario" : value === "missing" ? "Not provided" : "Human-reported"; }
export function normalizeSearch(value: string) { return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim(); }
export function matchesApplicationItem(item: { team_id: string; status: string }, query: string, team: string, status: string, text: string) {
  const active = !["completed", "canceled", "resolved", "accepted"].includes(item.status);
  return (!team || item.team_id === team) && (status === "all" || (status === "active" ? active : status === "closed" ? !active : item.status === status)) && normalizeSearch(query).split(/\s+/).every(word => normalizeSearch(text).includes(word));
}
export function eligibleRecipients(recipients: ApplicationRecipient[], team: string) {
  return recipients.filter(person => person.role === "owner" || person.role === "manager" && person.team_ids.includes(team));
}
export function parseSkills(value: string) { return [...new Set(value.split(",").map(item => item.trim().toLowerCase()).filter(Boolean))]; }
export function selectTaskCandidates(candidates: TaskCandidate[], query: string, includeUnavailable: boolean) {
  const words = normalizeSearch(query).split(/\s+/);
  return candidates.filter(candidate => (includeUnavailable || candidate.eligible) && words.every(word => normalizeSearch(candidate.name).includes(word)))
    .sort((a, b) => Number(b.eligible) - Number(a.eligible));
}
export function displayTime(value: number | null | undefined) {
  return value ? new Date(value * 1000).toLocaleString("en-GB", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Not set";
}
