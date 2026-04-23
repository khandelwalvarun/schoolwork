export type Child = {
  id: number;
  display_name: string;
  class_level: number;
  class_section: string | null;
  veracross_id: string | null;
};

export type Assignment = {
  id: number;
  child_id: number;
  subject: string | null;
  title: string | null;
  due_or_date: string | null;
  status: string | null;
  external_id: string;
  normalized?: {
    type?: string;
    teacher?: string;
    body?: string;
  };
};

export type TodayData = {
  generated_at: string;
  totals: { overdue: number; due_today: number; upcoming: number };
  children: Array<{
    child: Child;
    overdue: Assignment[];
    due_today: Assignment[];
    upcoming: Assignment[];
  }>;
  messages_last_7d: Array<{
    id: number;
    subject: string | null;
    title: string | null;
    due_or_date: string | null;
  }>;
  last_sync: {
    id: number;
    status: string;
    started_at: string;
    ended_at: string | null;
    items_new: number;
    items_updated: number;
    notifications_fired: number;
  } | null;
};

export type GradeTrend = {
  subject: string;
  count: number;
  latest: number;
  avg: number;
  min: number;
  max: number;
  sparkline: string;
  arrow: string;
};

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin", ...opts });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  today: () => fetchJson<TodayData>("/api/today"),
  children: () => fetchJson<Child[]>("/api/children"),
  overdue: (childId?: number) =>
    fetchJson<Assignment[]>(`/api/overdue${childId ? `?child_id=${childId}` : ""}`),
  gradeTrends: (childId: number) =>
    fetchJson<GradeTrend[]>(`/api/grade-trends?child_id=${childId}`),
  notifications: (sinceDays = 7) =>
    fetchJson<unknown[]>(`/api/notifications?since_days=${sinceDays}`),
  channelConfig: () => fetchJson<unknown>("/api/channel-config"),
  syncNow: () => fetchJson<unknown>("/api/sync", { method: "POST" }),
  digestRun: () => fetchJson<unknown>("/api/digest/run", { method: "POST" }),
  digestPreview: () => fetchJson<unknown>("/api/digest/preview"),
};
