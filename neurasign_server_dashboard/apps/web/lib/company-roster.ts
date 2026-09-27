/** Presentation-only organization of the records already authorized by the API. */
export type DataStatus = "current" | "stale" | "summary" | "waiting" | "paused" | "permission_required" | "unsupported";
export type RosterSort = "name" | "name_desc" | "recent" | "oldest";
export type RosterPerson = {
  id: string; name: string; team_id?: string | null; sharing: boolean; status?: string; last_received_at?: number | null;
  latest?: { received_at: number; timestamp?: number; source?: string } | null;
  signals?: { status: string; source?: string; latest?: { received_at: number } | null }[];
};
export const dataStatusLabels: Record<DataStatus, string> = {
  current: "Current", stale: "No recent data", summary: "Period summary", waiting: "Awaiting data",
  paused: "Sharing paused", permission_required: "Permission needed", unsupported: "Unavailable",
};
const normalize = (value: string) => value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });

export function personDataStatus(person: RosterPerson): DataStatus {
  if (!person.sharing || person.status === "paused") return "paused";
  const signals = person.signals ?? [];
  if (signals.some(signal => signal.status === "current") || Boolean(person.latest && person.status === "current")) return "current";
  if (signals.some(signal => signal.status === "delayed")) return "stale";
  if (signals.some(signal => signal.status === "summary")) return "summary";
  if (signals.some(signal => signal.status === "permission_required")) return "permission_required";
  if (signals.length && signals.every(signal => signal.status === "unsupported")) return "unsupported";
  if (person.latest && person.status === "stale") return "stale";
  return "waiting";
}

export function lastReceived(person: RosterPerson): number | null {
  if (personDataStatus(person) === "paused") return null;
  const times = [person.last_received_at, person.latest?.received_at, ...(person.signals ?? []).filter(signal => signal.status !== "paused").map(signal => signal.latest?.received_at)]
    .filter((time): time is number => typeof time === "number" && Number.isFinite(time) && time > 0);
  return times.length ? Math.max(...times) : null;
}

export function personSource(person: RosterPerson): string {
  if (personDataStatus(person) === "paused") return "Measurements hidden";
  const sources = new Set([person.latest?.source, ...(person.signals ?? []).filter(signal => signal.status !== "paused" && signal.latest).map(signal => signal.source)].filter(Boolean));
  if (sources.has("recording") && sources.has("wearable")) return "Wearable + DEMO RECORDING";
  if (sources.has("recording")) return "DEMO RECORDING";
  if (sources.has("wearable")) return "Wearable measurements";
  return "No measurements yet";
}

export function selectRoster<T extends RosterPerson>(people: readonly T[], teams: readonly { id: string; name: string }[], options: {
  query?: string; team?: string; status?: string; sharing?: string; sort?: RosterSort;
} = {}): T[] {
  const names = new Map(teams.map(team => [team.id, team.name]));
  const words = normalize(options.query ?? "").split(/\s+/).filter(Boolean);
  const result = people.filter(person => {
    if (options.team === "unassigned" ? Boolean(person.team_id) : options.team && options.team !== person.team_id) return false;
    if (options.status && personDataStatus(person) !== options.status) return false;
    if (options.sharing === "enabled" && !person.sharing || options.sharing === "paused" && person.sharing) return false;
    const searchable = normalize(`${person.name} ${names.get(person.team_id ?? "") ?? "Unassigned"}`);
    return words.every(word => searchable.includes(word));
  });
  return result.sort((a, b) => {
    const byName = collator.compare(a.name, b.name) || collator.compare(a.id, b.id);
    if (options.sort === "name_desc") return -byName;
    if (options.sort === "recent" || options.sort === "oldest") {
      const first = lastReceived(a), second = lastReceived(b);
      if (first === null && second !== null) return 1;
      if (second === null && first !== null) return -1;
      if (first !== null && second !== null && first !== second) return options.sort === "recent" ? second - first : first - second;
    }
    return byName;
  });
}

export function rosterPage<T>(items: readonly T[], requestedPage: number, requestedSize: number) {
  const size = requestedSize === 50 ? 50 : 25;
  const pages = Math.max(1, Math.ceil(items.length / size));
  const page = Math.min(pages - 1, Math.max(0, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 0));
  const start = page * size;
  return { items: items.slice(start, start + size), page, pages, size, total: items.length,
    first: items.length ? start + 1 : 0, last: Math.min(start + size, items.length) };
}

/** Legacy summaries expire by measurement time; a newer upload cannot refresh them. */
export function legacyDataStatus(person: RosterPerson, serverTime: number): DataStatus {
  if (!person.sharing || person.status === "paused") return "paused";
  if (!person.latest) return "waiting";
  return typeof person.latest.timestamp === "number" && Number.isFinite(person.latest.timestamp) && serverTime - person.latest.timestamp <= 60 ? "current" : "stale";
}
export function hasCurrentWearable(person: RosterPerson, serverTime: number): boolean {
  if (!person.sharing || person.status === "paused") return false;
  return Boolean(person.signals?.some(signal => signal.status === "current" && signal.source === "wearable") || person.latest?.source === "wearable" && legacyDataStatus(person, serverTime) === "current");
}
