export type Child = {
  id: number;
  display_name: string;
  class_level: number;
  class_section: string | null;
  veracross_id: string | null;
};

export type AttachmentLink = {
  id: number;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  kind: string | null;
  source_kind: string;
  download_url: string;
  sha256?: string;
  downloaded_at?: string | null;
};

export type ParentStatus =
  | "in_progress"
  | "done_at_home"
  | "submitted"
  | "needs_help"
  | "blocked"
  | "skipped";

export type Assignment = {
  id: number;
  child_id: number;
  subject: string | null;
  title: string | null;
  title_en: string | null;
  notes_en: string | null;
  due_or_date: string | null;
  status: string | null;
  portal_status: string | null;
  parent_status: ParentStatus | null;
  priority: number;
  snooze_until: string | null;
  status_notes: string | null;
  tags: string[];
  effective_status: string | null;
  parent_marked_submitted_at: string | null;
  syllabus_context: string | null;
  external_id: string;
  attachments?: AttachmentLink[];
  normalized?: {
    type?: string;
    teacher?: string;
    body?: string;
  };
};

export type AssignmentPatch = Partial<{
  parent_status: ParentStatus | null;
  priority: number;
  snooze_until: string | null;
  status_notes: string | null;
  tags: string[];
  note: string;
  actor: string;
}>;

export type StatusHistoryEntry = {
  id: number;
  field: string;
  old_value: string | null;
  new_value: string | null;
  source: string;
  actor: string | null;
  note: string | null;
  created_at: string | null;
};

export type AssignmentConstants = {
  parent_statuses: ParentStatus[];
  fixed_tags: string[];
};

export type AttachmentFull = AttachmentLink & {
  item_id: number | null;
  item_title: string | null;
  item_subject: string | null;
  item_kind: string | null;
  child_id: number | null;
};

export type SyllabusCycle = {
  name: string;
  start: string;
  end: string;
};

export type OverduePoint = { date: string; count: number };

export type ChildBlock = {
  child: Child;
  overdue: Assignment[];
  due_today: Assignment[];
  upcoming: Assignment[];
  grade_trends: GradeTrend[];
  syllabus_cycle: SyllabusCycle | null;
  overdue_trend: OverduePoint[];
  overdue_sparkline: string;
};

export type TodayData = {
  generated_at: string;
  totals: { overdue: number; due_today: number; upcoming: number };
  children: ChildBlock[];
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
  annotation?: string;
  recent?: Array<{ graded_date?: string | null; grade_pct?: number | null; title?: string | null }>;
};

export type ChildDetail = {
  child: Child;
  overdue: Assignment[];
  due_today: Assignment[];
  upcoming: Assignment[];
  grade_trends: GradeTrend[];
  overdue_trend: OverduePoint[];
  overdue_sparkline: string;
  syllabus_cycle: SyllabusCycle | null;
  counts: { overdue: number; due_today: number; upcoming: number; comments: number };
};

export type Comment = {
  id: number;
  child_id: number;
  subject: string | null;
  title: string | null;
  due_or_date: string | null;
  first_seen_at: string | null;
  normalized?: { teacher?: string; body?: string };
};

export type Note = {
  id: number;
  child_id: number | null;
  note: string;
  tags: string | null;
  note_date: string | null;
  created_at: string | null;
};

export type MessageRow = {
  id: number;
  child_id: number;
  subject: string | null;
  title: string | null;
  due_or_date: string | null;
  first_seen_at: string | null;
  attachments?: AttachmentLink[];
  normalized?: { body?: string; teacher?: string };
};

export type SummaryRow = {
  id: number;
  kind: string;
  child_id: number | null;
  period_start: string;
  period_end: string;
  content_md: string;
  stats: Record<string, unknown>;
  model_used: string;
  created_at: string | null;
};

export type SyllabusCycleFull = {
  name: string;
  start: string;
  end: string;
  topics_by_subject: Record<string, string[]>;
  overridden?: boolean;
  override_note?: string;
  topic_status?: Record<string, Record<string, { status: string; note?: string | null }>>;
};

export type SyllabusDoc = {
  school_year?: string;
  class_level?: number;
  cycles: SyllabusCycleFull[];
};

export type ReplayEvent = {
  event_id: number;
  kind: string;
  child_id: number | null;
  subject: string | null;
  notability: number;
  created_at: string | null;
  payload: Record<string, unknown>;
  channels: Record<string, {
    replay_status: string;
    replay_reason: string | null;
    actual_status: string | null;
    changed: boolean;
  }>;
};

export type ReplayResult = {
  events: ReplayEvent[];
  summary: { total?: number; would_send: number; would_suppress: number; changed: number; since_days?: number };
};

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    credentials: "same-origin",
    headers: opts?.body ? { "Content-Type": "application/json", ...(opts.headers || {}) } : opts?.headers,
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

const qs = (p: Record<string, string | number | undefined | null>) => {
  const entries = Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
};

export const api = {
  today: () => fetchJson<TodayData>("/api/today"),
  children: () => fetchJson<Child[]>("/api/children"),
  childDetail: (id: number) => fetchJson<ChildDetail>(`/api/child/${id}`),
  overdue: (childId?: number) =>
    fetchJson<Assignment[]>(`/api/overdue${childId ? `?child_id=${childId}` : ""}`),
  assignments: (p: { child_id?: number; subject?: string; status?: string; limit?: number } = {}) =>
    fetchJson<Assignment[]>(`/api/assignments${qs(p)}`),
  grades: (childId: number, subject?: string) =>
    fetchJson<Array<Record<string, unknown>>>(`/api/grades${qs({ child_id: childId, subject })}`),
  gradeTrends: (childId: number) =>
    fetchJson<GradeTrend[]>(`/api/grade-trends?child_id=${childId}`),
  gradeTrendsAnnotated: (childId: number) =>
    fetchJson<GradeTrend[]>(`/api/grade-trends/annotate?child_id=${childId}`),
  overdueTrend: (childId?: number, days = 14) =>
    fetchJson<OverduePoint[]>(`/api/overdue-trend${qs({ child_id: childId, days })}`),
  comments: (childId?: number) => fetchJson<Comment[]>(`/api/comments${qs({ child_id: childId })}`),
  messages: (sinceDays = 30) => fetchJson<MessageRow[]>(`/api/messages${qs({ since_days: sinceDays })}`),
  notes: (childId?: number) => fetchJson<Note[]>(`/api/notes${qs({ child_id: childId })}`),
  addNote: (note: string, childId?: number, tags?: string) =>
    fetchJson<unknown>(`/api/notes`, {
      method: "POST",
      body: JSON.stringify({ note, child_id: childId, tags }),
    }),
  summaries: (kind?: string) => fetchJson<SummaryRow[]>(`/api/summaries${qs({ kind })}`),
  syllabus: (classLevel: number) => fetchJson<SyllabusDoc>(`/api/syllabus/${classLevel}`),
  setCycleOverride: (classLevel: number, cycleName: string, body: { start?: string | null; end?: string | null; note?: string | null }) =>
    fetchJson<unknown>(`/api/syllabus/${classLevel}/cycle/${encodeURIComponent(cycleName)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  setTopicStatus: (classLevel: number, body: { subject: string; topic: string; status: string | null; note?: string | null }) =>
    fetchJson<unknown>(`/api/syllabus/${classLevel}/topic`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  notifications: (sinceDays = 7) =>
    fetchJson<unknown[]>(`/api/notifications?since_days=${sinceDays}`),
  replayNotifications: (sinceDays = 7, childId?: number) =>
    fetchJson<ReplayResult>(`/api/notifications/replay`, {
      method: "POST",
      body: JSON.stringify({ since_days: sinceDays, child_id: childId }),
    }),
  channelConfig: () => fetchJson<Record<string, unknown>>("/api/channel-config"),
  putChannelConfig: (cfg: unknown) =>
    fetchJson<unknown>("/api/channel-config", { method: "PUT", body: JSON.stringify(cfg) }),
  syncNow: () => fetchJson<unknown>("/api/sync", { method: "POST" }),
  digestRun: () => fetchJson<unknown>("/api/digest/run", { method: "POST" }),
  digestPreview: () => fetchJson<unknown>("/api/digest/preview"),
  markSubmitted: (itemId: number) =>
    fetchJson<unknown>(`/api/assignments/${itemId}/mark-submitted`, { method: "POST" }),
  unmarkSubmitted: (itemId: number) =>
    fetchJson<unknown>(`/api/assignments/${itemId}/mark-submitted`, { method: "DELETE" }),
  attachments: (p: { child_id?: number; source_kind?: string; limit?: number } = {}) =>
    fetchJson<AttachmentFull[]>(`/api/attachments${qs(p)}`),
  patchAssignment: (itemId: number, patch: AssignmentPatch) =>
    fetchJson<Record<string, unknown>>(`/api/assignments/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  assignmentHistory: (itemId: number) =>
    fetchJson<StatusHistoryEntry[]>(`/api/assignments/${itemId}/history`),
  assignmentConstants: () =>
    fetchJson<AssignmentConstants>("/api/assignments/constants"),
};
