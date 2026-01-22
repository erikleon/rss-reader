/**
 * The API serializes timestamps as naive UTC (no timezone suffix), e.g.
 * "2026-01-05T14:30:00". `new Date()` would interpret that as local time, so we
 * append "Z" when no timezone designator is present to force UTC.
 */
export function parseUtc(iso: string): Date {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : iso + "Z");
}

/** Short local time, e.g. "2:30 PM". */
export function formatTime(iso: string): string {
  return parseUtc(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Full local date+time, for tooltips, e.g. "Jan 6, 2026, 2:30 PM". */
export function formatAbsolute(iso: string): string {
  return parseUtc(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Compact relative time, e.g. "just now", "5m ago", "3h ago", "2d ago". */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = parseUtc(iso);
  const sec = Math.round((now.getTime() - then.getTime()) / 1000);
  if (sec < 45) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  const wk = Math.round(day / 7);
  if (wk < 5) return `${wk}w ago`;
  return then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
