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
