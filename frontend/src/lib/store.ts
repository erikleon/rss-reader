import { derived, get, writable } from "svelte/store";
import { AuthError, api } from "./api";
import { groupByDay } from "./groupByDay";
import type { Article, Feed, Item, Me } from "./types";

export const feeds = writable<Feed[]>([]);
export const items = writable<Item[]>([]);

export const days = writable<number>(30);
export const unreadOnly = writable<boolean>(false);
export const searchQuery = writable<string>("");

export const loadingItems = writable<boolean>(false);
export const refreshing = writable<boolean>(false);
export const error = writable<string | null>(null);
/**
 * Set when the server refuses who we are, rather than what we asked for.
 *
 * Kept apart from `error` because the whole page is wrong in this case, not one
 * action. Showing an empty feed list with a red line above it would read as
 * "you have no feeds" and send somebody looking in the wrong place.
 */
export const authError = writable<{ status: number; message: string } | null>(null);
/** The login the server resolved this browser to. */
export const me = writable<Me | null>(null);
export const lastRefresh = writable<string | null>(null);

/** Unread count per feed id, and the overall total (mirrored in the page title). */
export const unreadByFeed = writable<Map<number, number>>(new Map());
export const unreadTotal = writable<number>(0);

export async function loadUnreadCounts() {
  try {
    const { total, by_feed } = await api.unread();
    const map = new Map<number, number>();
    for (const [id, n] of Object.entries(by_feed)) map.set(Number(id), n);
    unreadByFeed.set(map);
    unreadTotal.set(total);
    document.title = total > 0 ? `(${total}) RSS Reader` : "RSS Reader";
  } catch (e) {
    report(e);
  }
}

/** Items grouped into local-day buckets for rendering. */
export const dayGroups = derived(items, ($items) => groupByDay($items));

/** Title lookup so each item can show its source feed. */
export const feedTitles = derived(feeds, ($feeds) => {
  const map = new Map<number, string>();
  for (const f of $feeds) map.set(f.id, f.title);
  return map;
});

function report(e: unknown) {
  if (e instanceof AuthError) {
    authError.set({ status: e.status, message: e.message });
    return;
  }
  error.set(e instanceof Error ? e.message : String(e));
}

export async function loadMe() {
  try {
    me.set(await api.me());
  } catch (e) {
    report(e);
  }
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
    const q = get(searchQuery).trim();
    // While searching, span all history rather than the day window.
    const window = q ? 0 : get(days);
    items.set(await api.listItems(window, get(unreadOnly), q));
    await loadUnreadCounts();
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

// --- Reader view ---------------------------------------------------------- //
/** The item being read, or null when the reader is closed. */
export const readerItem = writable<Item | null>(null);
export const readerArticle = writable<Article | null>(null);
export const readerLoading = writable<boolean>(false);

/**
 * Open the reading pane for an item.
 *
 * The first open goes and fetches the page, which is slow enough to need the
 * loading state. Opening also marks the item read, matching what clicking the
 * title already does: you opened it, you read it.
 */
export async function openReader(item: Item, refresh = false) {
  readerItem.set(item);
  readerArticle.set(null);
  readerLoading.set(true);
  markRead(item);
  try {
    readerArticle.set(await api.article(item.id, refresh));
  } catch (e) {
    report(e);
    readerItem.set(null);
  } finally {
    readerLoading.set(false);
  }
}

export function closeReader() {
  readerItem.set(null);
  readerArticle.set(null);
}

// --- Mark-read-on-scroll (persisted preference) --------------------------- //
const MROS_KEY = "rss:markReadOnScroll";

function initialMarkReadOnScroll(): boolean {
  try {
    return localStorage.getItem(MROS_KEY) === "1";
  } catch {
    return false;
  }
}

export const markReadOnScroll = writable<boolean>(initialMarkReadOnScroll());
markReadOnScroll.subscribe((v) => {
  try {
    localStorage.setItem(MROS_KEY, v ? "1" : "0");
  } catch {
    // no localStorage (e.g. tests); preference simply isn't persisted
  }
});

/** Mark an item read (idempotent); used by the scroll observer. */
export async function markRead(item: Item) {
  if (item.read) return;
  try {
    const updated = await api.setRead(item.id, true);
    items.update(($items) =>
      $items.map((i) => (i.id === updated.id ? updated : i)),
    );
    await loadUnreadCounts();
  } catch (e) {
    report(e);
  }
}

export async function toggleRead(item: Item) {
  try {
    const updated = await api.setRead(item.id, !item.read);
    items.update(($items) =>
      $items.map((i) => (i.id === updated.id ? updated : i)),
    );
    await loadUnreadCounts();
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

// --- Keyboard navigation -------------------------------------------------- //
export const selectedId = writable<number | null>(null);

function selectBy(delta: number) {
  const list = get(items);
  if (!list.length) return;
  const idx = list.findIndex((i) => i.id === get(selectedId));
  const next = idx < 0 ? 0 : Math.min(Math.max(idx + delta, 0), list.length - 1);
  selectedId.set(list[next].id);
}

export const selectNext = () => selectBy(1);
export const selectPrev = () => selectBy(-1);

function selectedItem(): Item | undefined {
  const id = get(selectedId);
  return get(items).find((i) => i.id === id);
}

export function openSelected() {
  const item = selectedItem();
  if (!item) return;
  if (item.link) window.open(item.link, "_blank", "noopener");
  if (!item.read) toggleRead(item);
}

/** Open the reading pane for whatever j/k has selected. Bound to `r`. */
export function openReaderForSelected() {
  const item = selectedItem();
  if (item?.link) openReader(item);
}

export function toggleSelectedRead() {
  const item = selectedItem();
  if (item) toggleRead(item);
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
