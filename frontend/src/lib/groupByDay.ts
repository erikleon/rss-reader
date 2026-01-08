import { parseUtc } from "./datetime";
import type { DayGroup, Item } from "./types";

function dayKey(d: Date): string {
  // Local-time YYYY-MM-DD so items group by the user's calendar day.
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (dayKey(d) === dayKey(today)) return "Today";
  if (dayKey(d) === dayKey(yesterday)) return "Yesterday";

  const sameYear = d.getFullYear() === today.getFullYear();
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}

/** Group an already newest-first list of items into local-day buckets. */
export function groupByDay(items: Item[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const item of items) {
    const d = parseUtc(item.published_at);
    const key = dayKey(d);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(item);
    } else {
      groups.push({ key, label: dayLabel(d), items: [item] });
    }
  }
  return groups;
}
