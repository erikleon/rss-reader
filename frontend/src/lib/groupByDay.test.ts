import { describe, expect, it } from "vitest";
import { groupByDay } from "./groupByDay";
import type { Item } from "./types";

function item(id: number, published_at: string): Item {
  return {
    id,
    feed_id: 1,
    guid: `g${id}`,
    title: `Item ${id}`,
    link: null,
    summary: null,
    published_at,
    fetched_at: published_at,
    read: false,
  };
}

describe("groupByDay", () => {
  it("buckets items by local (UTC, pinned) calendar day", () => {
    // Newest-first, as the API returns them. Midday UTC stays on the same day.
    const items = [
      item(1, "2026-01-06T12:00:00"),
      item(2, "2026-01-06T09:00:00"),
      item(3, "2026-01-05T20:00:00"),
    ];
    const groups = groupByDay(items);
    expect(groups.map((g) => g.key)).toEqual(["2026-01-06", "2026-01-05"]);
    expect(groups[0].items.map((i) => i.id)).toEqual([1, 2]);
    expect(groups[1].items.map((i) => i.id)).toEqual([3]);
  });

  it("returns an empty list for no items", () => {
    expect(groupByDay([])).toEqual([]);
  });

  it("preserves every item exactly once", () => {
    const items = [
      item(1, "2026-02-01T10:00:00"),
      item(2, "2026-02-01T08:00:00"),
      item(3, "2026-01-31T23:00:00"),
      item(4, "2026-01-15T12:00:00"),
    ];
    const flattened = groupByDay(items).flatMap((g) => g.items.map((i) => i.id));
    expect(flattened).toEqual([1, 2, 3, 4]);
  });
});
