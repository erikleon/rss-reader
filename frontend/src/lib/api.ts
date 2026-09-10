import type { Article, Feed, Item, Me, RefreshResult } from "./types";

/**
 * Sent on every request. The server rejects unsafe methods without it.
 *
 * Identity here comes from a Tailscale header the ingress adds, so the server
 * cannot tell a request this app made from one another site told the browser to
 * make. A cross-site form cannot set a custom header at all, and a cross-site
 * fetch that tries one has to pass a preflight the server does not answer.
 */
const CSRF_HEADER = "X-RSS-Reader";

/** Thrown when the server refuses the request's identity rather than its content. */
export class AuthError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "AuthError";
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      [CSRF_HEADER]: "1",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    if (res.status === 401 || res.status === 403) {
      throw new AuthError(res.status, detail);
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  me: () => request<Me>("/api/me"),

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

  article: (id: number, refresh = false) =>
    request<Article>(`/api/items/${id}/article${refresh ? "?refresh=true" : ""}`),

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
