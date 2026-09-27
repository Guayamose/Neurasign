import type { RosterPerson } from "./company-roster";

/** Connection and availability facts only. These helpers never assess a person's health. */
export type AttentionSignal = {
  status: string;
  source?: string;
  availability?: string;
  measurement_kind?: string;
  latest?: { received_at: number; timestamp?: number } | null;
};
export type AttentionPerson = Omit<RosterPerson, "signals"> & { signals?: AttentionSignal[] };
export type AttentionKind = "permission" | "stale" | "setup" | "unsupported" | null;
export type Attention = { kind: AttentionKind; label: string; nextStep: string; issueCount: number; priority: number };
export type TeamSummary = { total: number; currentWearable: number; attention: number; paused: number; summary: number; waiting: number };
export type TeamGroup<T extends AttentionPerson> = { id: string; name: string; people: T[]; summary: TeamSummary };

type ChannelState = "current" | "summary" | "paused" | "permission" | "stale" | "setup" | "unsupported";
type Channel = { state: ChannelState; source?: string };
const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
const isPaused = (person: AttentionPerson) => !person.sharing || person.status === "paused";
const isIssue = (state: ChannelState) => state === "permission" || state === "stale" || state === "setup" || state === "unsupported";

// These mirror the API's sample/window freshness and permitted clock skew.
const FRESHNESS_SECONDS = 60;
const MAX_FUTURE_SECONDS = 5;
function isRecent(timestamp: number | undefined, serverTime: number): boolean {
  return typeof timestamp === "number" && Number.isFinite(timestamp) && timestamp > 0 && Number.isFinite(serverTime)
    && timestamp <= serverTime + MAX_FUTURE_SECONDS && serverTime - timestamp <= FRESHNESS_SECONDS;
}

function signalState(signal: AttentionSignal, serverTime: number): ChannelState {
  // Availability remains meaningful when a source has older observations on file.
  if (signal.status === "paused") return "paused";
  if (signal.status === "permission_required" || signal.availability === "permission_required") return "permission";
  if (signal.status === "unsupported" || signal.availability === "unsupported") return "unsupported";
  if (signal.status === "waiting") return "setup";
  if (signal.status === "summary") return "summary";
  if (signal.status === "delayed") return "stale";
  if (signal.status === "current") {
    if (!signal.latest) return "setup";
    if (signal.measurement_kind === "summary") return "summary";
    // Canonical status is authoritative when using older snapshot contracts
    // without timestamps. Receipt time is never used to claim fresh data.
    return signal.latest.timestamp === undefined || isRecent(signal.latest.timestamp, serverTime) ? "current" : "stale";
  }
  return "setup";
}

function channelsFor(person: AttentionPerson, serverTime: number): Channel[] {
  if (isPaused(person)) return [];
  const signals = person.signals ?? [];
  const channels = signals.map(signal => ({ state: signalState(signal, serverTime), source: signal.source }));
  // The API can expose these feeds side by side. `source` says wearable or
  // recording, not device identity, so it cannot establish supersession.
  if (person.latest) {
    channels.push({ state: isRecent(person.latest.timestamp, serverTime) ? "current" : "stale", source: person.latest.source });
  }
  return channels.length ? channels : [{ state: "setup" }];
}

function attentionFor(person: AttentionPerson, channels: Channel[]): Attention {
  if (isPaused(person)) return { kind: null, label: "Sharing paused", nextStep: "", issueCount: 0, priority: 0 };
  const count = (state: ChannelState) => channels.filter(channel => channel.state === state).length;
  const issueCount = channels.filter(channel => isIssue(channel.state)).length;
  if (count("permission")) return {
    kind: "permission", label: "Permission needed", priority: 4, issueCount,
    nextStep: "Ask the employee to review signal permissions in the phone app.",
  };
  if (count("stale")) return {
    kind: "stale", label: "No recent measurements", priority: 3, issueCount,
    nextStep: "Check the phone connection and when the device last measured or synced.",
  };
  if (count("setup")) {
    const hasMeasurements = channels.some(channel => channel.state === "current" || channel.state === "summary");
    return {
      kind: "setup", label: hasMeasurements ? "Waiting for a signal" : "Awaiting first measurements", priority: 1, issueCount,
      nextStep: hasMeasurements ? "Check whether the pending signal is ready to measure or sync."
        : person.signals?.length ? "Check the connected source and its next measurement or sync."
          : "Check phone setup and whether sharing is enabled in the phone app.",
    };
  }
  if (count("unsupported")) return {
    // Unsupported is an expected capability limit, not a failed connection.
    kind: "unsupported", label: channels.every(channel => channel.state === "unsupported") ? "No supported measurements" : "Some signals unavailable",
    nextStep: "Review which measurements this device supports.", issueCount, priority: 0,
  };
  return { kind: null, label: count("current") ? "Measurements up to date" : count("summary") ? "Period summaries available" : "Sharing paused",
    nextStep: "", issueCount: 0, priority: 0 };
}

export function classifyAttention(person: AttentionPerson, serverTime: number): Attention {
  return attentionFor(person, channelsFor(person, serverTime));
}

/** Use this same predicate for the live-wearable total and its drill-down view. */
export function hasCurrentWearableData(person: AttentionPerson, serverTime: number): boolean {
  return channelsFor(person, serverTime).some(channel => channel.state === "current" && channel.source === "wearable");
}

/** Presence counts may overlap: a current wearable can also have a delayed signal. */
export function summarizeTeam(people: readonly AttentionPerson[], serverTime: number): TeamSummary {
  const summary: TeamSummary = { total: people.length, currentWearable: 0, attention: 0, paused: 0, summary: 0, waiting: 0 };
  for (const person of people) {
    if (isPaused(person)) { summary.paused++; continue; }
    const channels = channelsFor(person, serverTime);
    if (hasCurrentWearableData(person, serverTime)) summary.currentWearable++;
    if (attentionFor(person, channels).priority > 0) summary.attention++;
    if (channels.some(channel => channel.state === "summary")) summary.summary++;
    if (channels.some(channel => channel.state === "setup")) summary.waiting++;
  }
  return summary;
}

/** Accept a filtered roster to group only the people currently in view. */
export function groupTeams<T extends AttentionPerson>(people: readonly T[], teams: readonly { id: string; name: string }[], serverTime: number): TeamGroup<T>[] {
  const groups = new Map<string, { id: string; name: string; people: T[] }>();
  for (const team of teams) groups.set(team.id, { id: team.id, name: team.name, people: [] });
  for (const person of people) {
    const id = person.team_id || "unassigned";
    if (!groups.has(id)) groups.set(id, { id, name: person.team_id ? "Other team" : "Unassigned", people: [] });
    groups.get(id)!.people.push(person);
  }
  return Array.from(groups.values(), group => ({ ...group, summary: summarizeTeam(group.people, serverTime) }))
    .sort((a, b) => b.summary.attention - a.summary.attention || collator.compare(a.name, b.name) || collator.compare(a.id, b.id));
}
