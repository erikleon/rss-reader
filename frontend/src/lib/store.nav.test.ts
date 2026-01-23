import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";
import { items, selectedId, selectNext, selectPrev } from "./store";
import type { Item } from "./types";

function mk(id: number): Item {
  return {
    id,
    feed_id: 1,
    guid: `g${id}`,
    title: `Item ${id}`,
    link: null,
    summary: null,
    published_at: "2026-01-06T12:00:00",
    fetched_at: "2026-01-06T12:00:00",
    read: false,
  };
}

beforeEach(() => {
  selectedId.set(null);
  items.set([mk(1), mk(2), mk(3)]);
});

describe("keyboard selection", () => {
  it("selects the first item when nothing is selected", () => {
    selectNext();
    expect(get(selectedId)).toBe(1);
  });

  it("advances and clamps at the last item", () => {
    selectNext(); // 1
    selectNext(); // 2
    selectNext(); // 3
    selectNext(); // stays at 3
    expect(get(selectedId)).toBe(3);
  });

  it("moves back and clamps at the first item", () => {
    selectedId.set(2);
    selectPrev(); // 1
    selectPrev(); // stays at 1
    expect(get(selectedId)).toBe(1);
  });

  it("does nothing when there are no items", () => {
    items.set([]);
    selectedId.set(null);
    selectNext();
    expect(get(selectedId)).toBe(null);
  });
});
