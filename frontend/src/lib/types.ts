export interface Feed {
  id: number;
  user_id: number;
  url: string;
  title: string;
  site_url: string | null;
  added_at: string;
  last_fetched_at: string | null;
  last_error: string | null;
}

export interface Item {
  id: number;
  feed_id: number;
  guid: string;
  title: string;
  link: string | null;
  summary: string | null;
  published_at: string;
  fetched_at: string;
  read: boolean;
}

export interface RefreshResult {
  id: number;
  title: string;
  new_count: number;
  error: string | null;
}

export interface DayGroup {
  /** Local calendar day, e.g. "2026-01-06". */
  key: string;
  /** Human label, e.g. "Today" / "Yesterday" / "Mon, Jan 6". */
  label: string;
  items: Item[];
}
