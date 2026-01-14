import { derived, get, writable } from "svelte/store";
import { api } from "./api";
import { groupByDay } from "./groupByDay";
import type { Feed, Item } from "./types";

export const feeds = writable<Feed[]>([]);
export const items = writable<Item[]>([]);

export const days = writable<number>(30);
export const unreadOnly = writable<boolean>(false);

export const loadingItems = writable<boolean>(false);
export const refreshing = writable<boolean>(false);
export const error = writable<string | null>(null);
export const lastRefresh = writable<string | null>(null);

/** Items grouped into local-day buckets for rendering. */
export const dayGroups = derived(items, ($items) => groupByDay($items));

/** Title lookup so each item can show its source feed. */
export const feedTitles = derived(feeds, ($feeds) => {
  const map = new Map<number, string>();
  for (const f of $feeds) map.set(f.id, f.title);
  return map;
});

function report(e: unknown) {
  error.set(e instanceof Error ? e.message : String(e));
}

export async function loadFeeds() {
  try {
    feeds.set(await api.listFeeds());
  } catch (e) {
    report(e);
  }
}

export async function loadItems() {
  loadingItems.set(true);
  try {
    items.set(await api.listItems(get(days), get(unreadOnly)));
  } catch (e) {
    report(e);
  } finally {
    loadingItems.set(false);
  }
}

export async function addFeed(url: string) {
  error.set(null);
  await api.addFeed(url); // let caller catch to keep the input on failure
  await Promise.all([loadFeeds(), loadItems()]);
}

export async function removeFeed(id: number) {
  try {
    await api.removeFeed(id);
    await Promise.all([loadFeeds(), loadItems()]);
  } catch (e) {
    report(e);
  }
}

export async function refresh() {
  refreshing.set(true);
  error.set(null);
  try {
    const results = await api.refresh();
    const total = results.reduce((sum, r) => sum + r.new_count, 0);
    const failed = results.filter((r) => r.error).length;
    lastRefresh.set(
      `${total} new item${total === 1 ? "" : "s"}` +
        (failed ? ` · ${failed} feed${failed === 1 ? "" : "s"} failed` : ""),
    );
    await Promise.all([loadFeeds(), loadItems()]);
  } catch (e) {
    report(e);
  } finally {
    refreshing.set(false);
  }
}

export async function toggleRead(item: Item) {
  try {
    const updated = await api.setRead(item.id, !item.read);
    items.update(($items) =>
      $items.map((i) => (i.id === updated.id ? updated : i)),
    );
  } catch (e) {
    report(e);
  }
}

export async function markAllRead() {
  try {
    await api.markAllRead();
    await loadItems();
  } catch (e) {
    report(e);
  }
}

export const importStatus = writable<string | null>(null);

export async function importOpml(xml: string) {
  importStatus.set("Importing…");
  error.set(null);
  try {
    const r = await api.importOpml(xml);
    importStatus.set(
      `Imported ${r.added} feed${r.added === 1 ? "" : "s"}` +
        (r.skipped ? `, ${r.skipped} already subscribed` : "") +
        (r.failed.length ? `, ${r.failed.length} failed` : ""),
    );
    await Promise.all([loadFeeds(), loadItems()]);
  } catch (e) {
    importStatus.set(null);
    report(e);
  }
}
