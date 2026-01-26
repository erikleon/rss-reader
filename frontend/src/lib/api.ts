import type { Feed, Item, RefreshResult } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listFeeds: () => request<Feed[]>("/api/feeds"),

  addFeed: (url: string) =>
    request<Feed>("/api/feeds", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  removeFeed: (id: number) =>
    request<void>(`/api/feeds/${id}`, { method: "DELETE" }),

  refresh: () => request<RefreshResult[]>("/api/refresh", { method: "POST" }),

  listItems: (days: number, unreadOnly: boolean, q = "") =>
    request<Item[]>(
      `/api/items?days=${days}&unread_only=${unreadOnly}` +
        (q ? `&q=${encodeURIComponent(q)}` : ""),
    ),

  setRead: (id: number, read: boolean) =>
    request<Item>(`/api/items/${id}/read`, {
      method: "POST",
      body: JSON.stringify({ read }),
    }),

  markAllRead: () =>
    request<{ updated: number }>("/api/items/read-all", { method: "POST" }),

  unread: () =>
    request<{ total: number; by_feed: Record<string, number> }>("/api/unread"),

  importOpml: (xml: string) =>
    request<{ added: number; skipped: number; failed: { url: string; error: string }[] }>(
      "/api/import/opml",
      {
        method: "POST",
        headers: { "Content-Type": "application/xml" },
        body: xml,
      },
    ),
};
