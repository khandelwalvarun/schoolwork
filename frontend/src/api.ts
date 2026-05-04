/** Phase 17: self-prediction band — three named tiers + a numeric escape
 *  hatch (`%85`). Anything else is rejected by the API. */
export type SelfPredictionBand = "high" | "mid" | "low" | string;

/** Computed once a grade has been linked. */
export type SelfPredictionOutcome = "matched" | "better" | "worse";

/** Phase 22 — dedup'd school-message group. Each group collapses
 *  identical announcements across kids, tagged with the union of
 *  recipients. `llm_summary` is populated lazily on click. */
export type SchoolMessageGroup = {
  group_id: string;       // "grpNN"
  normalized_title: string;
  title: string | null;
  title_en: string | null;
  latest_seen: string | null;
  latest_date: string | null;
  member_count: number;
  kids: Array<{ child_id: number; display_name: string | null }>;
  llm_summary: string | null;
  llm_summary_url: string | null;
  members: Array<{
    id: number;
    child_id: number | null;
    child_name: string | null;
    title: string | null;
    title_en: string | null;
    body: string | null;
    due_or_date: string | null;
    first_seen_at: string | null;
  }>;
};

/** Kid-relevant calendar event. `child_id === null` means it applies
 *  to both kids (school-wide). `source` is `manual` for typed entries
 *  and `school_message` for LLM-extracted ones. */
export type KidEvent = {
  id: number;
  child_id: number | null;
  title: string;
  description: string | null;
  event_type: string | null;
  importance: number;     // 1 normal · 2 important · 3 critical
  start_date: string;     // YYYY-MM-DD
  end_date: string | null;
  start_time: string | null;
  location: string | null;
  source: string;
  source_ref: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

/** Parent-uploaded library file. The LLM classifier fills in `llm_*`
 *  fields shortly after upload — they may be null on first list. */
export type LibraryFile = {
  id: number;
  filename: string;
  original_filename: string | null;
  sha256: string;
  size_bytes: number | null;
  mime_type: string | null;
  child_id: number | null;
  uploaded_at: string | null;
  note: string | null;
  llm_kind: string | null;
  llm_subject: string | null;
  llm_class_level: number | null;
  llm_summary: string | null;
  llm_keywords: string[];
  llm_processed_at: string | null;
  llm_model: string | null;
  llm_error: string | null;
};

export type PortfolioItem = {
  id: number;
  child_id: number;
  subject: string | null;
  topic: string | null;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  kind: string | null;
  note: string | null;
  uploaded_at: string | null;
  sha256: string;
};

/** Per-kid 1-paragraph synthesis for the Today page header.
 *  Built by services/daily_brief.py; cached in-memory keyed by
 *  (child_id, date). `has_signal=false` → "nothing pressing today"
 *  flavour (UI may collapse to a quiet line). */
export type DailyBrief = {
  child_id: number;
  child_name: string;
  generated_for: string;
  summary: string;
  has_signal: boolean;
  pack_row_ids: number[];
};

export type SentimentPoint = {
  bucket_start: string;
  n: number;
  mean_score: number | null;
};

export type SentimentTrend = {
  points: SentimentPoint[];
  total_comments: number;
  window_days: number;
  bucket_days: number;
  direction: "rising" | "falling" | "flat" | null;
  honest_caveat: string;
};

export type SelfPredictionCalibration = {
  summary: {
    total: number;
    matched: number;
    better: number;
    worse: number;
    share_matched: number | null;
  };
  rows: Array<{
    item_id: number;
    child_id: number;
    subject: string | null;
    title: string | null;
    self_prediction: SelfPredictionBand | null;
    self_prediction_outcome: SelfPredictionOutcome | null;
    self_prediction_set_at: string | null;
  }>;
};

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
  /** Original-language description from the assignment-detail popup. May
   *  be multi-paragraph. Empty/null when the planner-only path was the
   *  only source (no detail fetch). */
  body?: string | null;
  /** Phase 17: Zimmerman self-prediction loop. Bands map to score
   *  ranges in services/self_prediction.py. */
  self_prediction?: SelfPredictionBand | null;
  self_prediction_set_at?: string | null;
  self_prediction_outcome?: SelfPredictionOutcome | null;
  /** Cached 1-sentence "the ask in plain English" (assignment kind)
   *  OR Claude-generated anomaly hypothesis (grade kind). Populated
   *  lazily on AuditDrawer open. The semantic differs by `kind`. */
  llm_summary?: string | null;
  /** "assignment" | "grade" | "comment" | "school_message" — needed by
   *  the AuditDrawer to branch on grade-vs-assignment behavior. */
  kind?: string;
  due_or_date: string | null;
  status: string | null;
  portal_status: string | null;
  parent_status: ParentStatus | null;
  priority: number;
  snooze_until: string | null;
  status_notes: string | null;
  tags: string[];
  effective_status: string | null;
  /** Phase 24 — attention-lifecycle zone, computed server-side. Drives
   *  the FRESH / STEADY / ARCHIVED partitioning of every assignment list. */
  attention_zone?: "fresh" | "steady" | "archived";
  parent_marked_submitted_at: string | null;
  /** Phase 23: parent flagged this item as "worth a chat" at the next
   *  PTM. Timestamp = on; null = off. The optional note carries the
   *  parent's reason (e.g. "ask why score dropped"). The PTM brief
   *  surfaces flagged items as a dedicated subsection per subject. */
  discuss_with_teacher_at?: string | null;
  discuss_with_teacher_note?: string | null;
  syllabus_context: string | null;
  external_id: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  detail_fetched_at?: string | null;
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
  /** Toggle "worth a chat" flag. true = flag on (server stamps now()),
   *  false = clear flag + clear note. Sending only the note (without
   *  this) updates the note while preserving the on/off state — and
   *  also implicitly turns the flag on if the note is non-empty. */
  discuss_with_teacher: boolean;
  discuss_with_teacher_note: string | null;
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

/** Phase 24 — recently-graded item rendered as a pellet next to the
 *  kid's name. Stays visible for ~48h after the grade lands; anomalous
 *  grades stay until the underlying anomaly score recovers. */
export type FreshGradePellet = {
  item_id: number;
  subject: string | null;
  title: string | null;
  pct: number;
  score_text: string | null;
  graded_date: string | null;
  hours_ago: number | null;
  tone: "green" | "amber" | "red" | "gray";
  anomalous: boolean;
};

/** Phase 25 — practice-prep workspace types. A session is a stateful
 *  prep workspace; iterations accumulate as the parent steers the LLM
 *  with prompts; classwork scans ground the next iteration. */
export type PracticeKind = "review_prep" | "assignment_help" | "review_work";

export type PinnedSourceType = "library" | "resource" | "syllabus_topic";

export type PinnedSource = {
  type: PinnedSourceType;
  ref: string | number;
  label: string;
};

export type ScanPurpose = "classwork_reference" | "student_work";

export type ReviewWorkVerdict = "correct" | "partially_correct" | "incorrect" | "unclear";

export type ReviewWorkItem = {
  ref: string;
  verdict: ReviewWorkVerdict;
  what_kid_did: string;
  feedback: string;
  suggestion: string | null;
};

export type ReviewWorkScore = {
  value: number;
  max: number;
  confidence: "high" | "medium" | "low";
};

export type PracticeQuestion = {
  n: number;
  stem: string;
  type: string;
  marks: number;
  expected_answer?: string;
  expected_solution_md?: string;
  topic_ref?: string;
};

export type PracticeHelpSection = {
  heading: string;
  body_md: string;
  kind?: "step" | "example" | "hint" | "warning" | "optional" | "reference" | string;
};

export type PracticeOutputJson = {
  title?: string;
  // review_prep:
  instructions?: string;
  questions?: PracticeQuestion[];
  answer_key?: string;
  // assignment_help:
  summary?: string;
  format?: string;
  sections?: PracticeHelpSection[];
  next_steps?: string[];
  // review_work:
  overall_assessment?: string;
  estimated_score?: ReviewWorkScore | null;
  by_question?: ReviewWorkItem[];
  general_suggestions?: string[];
  // all:
  honest_caveat?: string;
};

export type PracticeIterationOut = {
  id: number;
  session_id: number;
  iteration_index: number;
  parent_prompt: string | null;
  output_md: string;
  output_json: PracticeOutputJson | null;
  llm_used: boolean;
  llm_model: string | null;
  llm_input_tokens: number | null;
  llm_output_tokens: number | null;
  duration_ms: number | null;
  error: string | null;
  created_at: string | null;
};

export type PracticeClassworkScanOut = {
  id: number;
  session_id: number | null;
  child_id: number;
  subject: string;
  attachment_id: number;
  purpose: ScanPurpose;
  extracted_summary: string | null;
  extracted_topics: string[] | null;
  extracted_text_present: boolean;
  extracted_at: string | null;
  uploaded_at: string | null;
};

export type PracticeSessionOut = {
  id: number;
  child_id: number;
  subject: string;
  topic: string | null;
  linked_assignment_id: number | null;
  title: string;
  kind: PracticeKind;
  status: string;
  preferred_iteration_id: number | null;
  pinned_sources?: PinnedSource[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  iterations: PracticeIterationOut[];
  scans: PracticeClassworkScanOut[];
};

export type PracticeSessionListItem = {
  id: number;
  child_id: number;
  subject: string;
  topic: string | null;
  title: string;
  kind: PracticeKind;
  status: string;
  iteration_count: number;
  linked_assignment_id: number | null;
  preferred_iteration_id: number | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type ChildBlock = {
  child: Child;
  overdue: Assignment[];
  due_today: Assignment[];
  upcoming: Assignment[];
  grade_trends: GradeTrend[];
  fresh_pellets?: FreshGradePellet[];
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
    title_en?: string | null;
    due_or_date: string | null;
    attachments?: AttachmentLink[];
    normalized?: { body?: string; teacher?: string };
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
  fresh_pellets?: FreshGradePellet[];
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
  title_en?: string | null;
  due_or_date: string | null;
  first_seen_at: string | null;
  attachments?: AttachmentLink[];
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

export type ResourceFile = {
  scope: "schoolwide" | "kid";
  kid_slug: string | null;
  child_id: number | null;
  category: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  modified_at: number;
  download_url: string;
};

export type ResourcesResponse = {
  schoolwide: Record<string, ResourceFile[]>;
  kids: Array<{
    child_id: number;
    display_name: string;
    kid_slug: string;
    by_category: Record<string, ResourceFile[]>;
  }>;
};

export type ShakyTopic = {
  child_id: number;
  subject: string;
  topic: string;
  state: "attempted" | "familiar" | "proficient" | "decaying";
  last_score: number | null;
  last_assessed_at: string | null;
  attempt_count: number;
  shakiness: number;
  reasons: string[];
};

export type ShakyTopicsResponse = {
  kids: Array<{
    child_id: number;
    display_name: string;
    items: ShakyTopic[];
  }>;
  limit_per_kid: number;
};

/** Per-week homework-load buckets. The cockpit can't measure real
 *  time-on-task — est_minutes is a per-class estimate (assignment
 *  count × default minutes-per-item). The earlier CBSE policy-cap
 *  horizon was removed (it didn't reflect what the school actually
 *  assigns; the line was misleading). */
export type HomeworkLoadWeek = {
  week_start: string;  // ISO date — Monday of that week
  items: number;
  est_minutes: number;
  /** Per-bucket split: how many items used assigned-date vs fell back
   *  to due-date. Lets the UI footnote a bucket whose accuracy is
   *  partly degraded. */
  by_source?: { assigned: number; due: number };
};

export type HomeworkLoadKid = {
  child_id: number;
  class_level: number;
  weeks: HomeworkLoadWeek[];
  est_minutes_per_item: number;
  honest_caveat: string;
  /** "assigned_date_with_due_fallback" once the bucket-by-assigned
   *  patch lands; older payloads omit. */
  bucketing?: string;
  /** Share (0..1) of items that fell back from assigned-date to
   *  due-date because no assigned-date was captured. */
  fallback_share?: number;
  /** Human-readable footnote about the bucketing source. */
  bucketing_note?: string;
};

export type HomeworkLoadAll = {
  kids: HomeworkLoadKid[];
  weeks: number;
};

/** Monthly behavioural patterns. Each flag is boolean — `detail`
 *  carries supporting evidence the UI shows on hover. By design, these
 *  never push notifications. */
export type PatternMonth = {
  child_id: number;
  month: string;             // "YYYY-MM"
  lateness: boolean;
  repeated_attempt: boolean;
  weekend_cramming: boolean;
  detail: {
    lateness: { count: number; threshold: number; examples: string[] };
    repeated_attempt: {
      topics: Array<{ subject: string; topic: string; count: number; examples: string[] }>;
      threshold: number;
    };
    weekend_cramming: {
      weekend: number;
      weekday: number;
      total: number;
      fraction?: number;
      fraction_threshold: number;
      min_sample?: number;
      examples?: string[];
      note?: string;
    };
  };
  updated_at: string | null;
};

export type PatternsAll = {
  kids: Array<{
    child_id: number;
    display_name: string;
    months: PatternMonth[];
  }>;
};

/** Per-rule snooze the parent set from the (why?) popover. The
 *  dispatcher reads these and suppresses with reason "snoozed by parent"
 *  until `until` passes. `child_id === null` means kid-agnostic. */
export type NotificationSnooze = {
  id: number;
  rule_id: string;
  child_id: number | null;
  until: string;       // ISO datetime in UTC
  reason: string | null;
  created_at?: string;
};

/** Per-channel notification row, decorated with Phase-14 explainer fields.
 *  `tier` mirrors the rubric's delivery tier ("now" | "today" | "weekly").
 *  `rule_id` is the event-kind name. `why` is the structured payload that
 *  fed the rule (datapoints, threshold, child_id, etc.). */
export type NotificationRow = {
  channel: string;
  status: string;
  delivered_at?: string | null;
  error?: string | null;
  tier?: "now" | "today" | "weekly" | null;
  rule_id?: string | null;
  why?: Record<string, unknown> | null;
};

export type NotificationEvent = {
  id: number;
  kind: string;
  child_id: number | null;
  subject: string | null;
  notability: number;
  dedup_key: string;
  created_at: string;
  payload: Record<string, unknown>;
  notifications: NotificationRow[];
};

export type ExcellenceStatus = {
  child_id: number;
  year_label: string;
  year_start: string;
  year_end: string;
  grades_count: number;
  above_85_count: number;
  current_year_avg: number | null;
  on_track: boolean;
  above_85_share: number;
  below_85_recent: Array<{
    id: number;
    subject: string | null;
    title: string | null;
    graded_date: string;
    grade_pct: number;
  }>;
  threshold: number;
};

export type LanguageCode = "en" | "hi" | "sa" | null;

export type MasteryState =
  | "attempted"
  | "familiar"
  | "proficient"
  | "mastered"
  | "decaying"
  | null;

export type TopicDetail = {
  child_id: number;
  subject: string;
  topic: string;
  bare_topic: string;
  state: MasteryState;
  last_assessed_at: string | null;
  last_score: number | null;
  attempt_count: number;
  proficient_count: number;
  language_code: LanguageCode;
  linked_grades: Assignment[];
  linked_assignments: Assignment[];
  portfolio_items: PortfolioItem[];
};

export type TopicStateRow = {
  subject: string;
  topic: string;
  state: "attempted" | "familiar" | "proficient" | "mastered" | "decaying";
  language_code?: LanguageCode;
  last_assessed_at: string | null;
  last_score: number | null;
  attempt_count: number;
  proficient_count: number;
};

export type SpellBeeList = {
  filename: string;
  number: number | null;
  size_bytes: number;
  mime_type: string;
  child_id: number;
  kid_slug: string;
  download_url: string;
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
  gradeAnomalies: (childId?: number) =>
    fetchJson<Array<{
      grade_id: number;
      subject: string;
      graded_date: string;
      pct: number;
      reason: string;
      child_id?: number;
      child_name?: string;
    }>>(`/api/anomalies${childId ? `?child_id=${childId}` : ""}`),
  explainGradeAnomaly: (gradeId: number, force = false) =>
    fetchJson<{
      grade_id: number;
      anomalous: boolean;
      reason: string;
      explanation: string | null;
      cached: boolean;
      llm_used: boolean;
    }>(`/api/grades/${gradeId}/explain-anomaly${force ? "?force=true" : ""}`, {
      method: "POST",
    }),
  summarizeAssignment: (itemId: number, force = false) =>
    fetchJson<{
      item_id: number;
      summary: string | null;
      cached: boolean;
      llm_used: boolean;
    }>(`/api/assignments/${itemId}/summarize${force ? "?force=true" : ""}`, {
      method: "POST",
    }),
  setSelfPrediction: (itemId: number, prediction: string | null) =>
    fetchJson<{
      item_id: number;
      self_prediction: SelfPredictionBand | null;
      self_prediction_set_at: string | null;
      self_prediction_outcome: SelfPredictionOutcome | null;
    }>(`/api/assignments/${itemId}/self-prediction`, {
      method: "POST",
      body: JSON.stringify({ prediction }),
    }),
  selfPredictionCalibration: (childId?: number) =>
    fetchJson<SelfPredictionCalibration>(
      `/api/self-prediction/calibration${childId ? `?child_id=${childId}` : ""}`,
    ),
  schoolMessagesGrouped: (limit = 50) =>
    fetchJson<SchoolMessageGroup[]>(`/api/school-messages/grouped?limit=${limit}`),
  schoolMessageSummarize: (groupId: string) =>
    fetchJson<{
      group_id: string;
      summary: string;
      url: string | null;
      members: number;
      llm_used: boolean;
    }>(`/api/school-messages/${encodeURIComponent(groupId)}/summarize`, {
      method: "POST",
    }),
  mindsparkProgress: (childId?: number) =>
    fetchJson<{
      kids: Array<{
        child_id: number;
        child_name: string;
        sessions: Array<{
          id: number;
          external_id: string;
          subject: string | null;
          topic_name: string | null;
          started_at: string | null;
          duration_sec: number | null;
          questions_total: number | null;
          questions_correct: number | null;
          accuracy_pct: number | null;
        }>;
        topics: Array<{
          id: number;
          subject: string;
          topic_name: string;
          topic_id: string | null;
          accuracy_pct: number | null;
          questions_attempted: number | null;
          time_spent_sec: number | null;
          mastery_level: string | null;
          last_activity_at: string | null;
          updated_at: string | null;
        }>;
      }>;
    }>(`/api/mindspark/progress${childId ? `?child_id=${childId}` : ""}`),
  mindsparkSync: (childId?: number) =>
    fetchJson<Record<string, unknown>>(
      `/api/mindspark/sync${childId ? `?child_id=${childId}` : ""}`,
      { method: "POST" },
    ),
  events: (childId?: number, daysAhead?: number, includePast = true) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (daysAhead != null) p.set("days_ahead", String(daysAhead));
    if (!includePast) p.set("include_past", "false");
    return fetchJson<KidEvent[]>(`/api/events?${p.toString()}`);
  },
  upsertEvent: (e: Partial<KidEvent>) =>
    fetchJson<KidEvent>(`/api/events`, {
      method: "POST",
      body: JSON.stringify(e),
    }),
  deleteEvent: (id: number) =>
    fetchJson<{ ok: boolean; id: number }>(
      `/api/events/${id}`,
      { method: "DELETE" },
    ),
  extractEventsFromMessages: (days = 60, only_new = true) =>
    fetchJson<{
      messages_scanned: number;
      events_extracted: number;
      events_inserted: number;
      events_skipped_dup: number;
    }>(
      `/api/events/extract-from-messages?days=${days}&only_new=${only_new}`,
      { method: "POST" },
    ),
  libraryList: (childId?: number, kind?: string, subject?: string) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (kind) p.set("kind", kind);
    if (subject) p.set("subject", subject);
    return fetchJson<LibraryFile[]>(`/api/library?${p.toString()}`);
  },
  libraryUpload: async (
    files: File[],
    childId?: number,
    note?: string,
  ) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (note) p.set("note", note);
    const r = await fetch(
      `/api/library/upload${p.toString() ? `?${p.toString()}` : ""}`,
      { method: "POST", body: fd, credentials: "same-origin" },
    );
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return (await r.json()) as {
      saved: Array<{
        id: number;
        filename: string;
        sha256: string;
        size_bytes: number | null;
        uploaded_at: string | null;
      }>;
      errors: Array<{ filename: string; error: string }>;
    };
  },
  libraryReclassify: (libraryId: number) =>
    fetchJson<Record<string, unknown>>(
      `/api/library/${libraryId}/reclassify`,
      { method: "POST" },
    ),
  libraryDelete: (libraryId: number) =>
    fetchJson<{ ok: boolean; id: number }>(
      `/api/library/${libraryId}`,
      { method: "DELETE" },
    ),
  portfolioList: (childId: number, subject?: string, topic?: string) => {
    const p = new URLSearchParams({ child_id: String(childId) });
    if (subject) p.set("subject", subject);
    if (topic) p.set("topic", topic);
    return fetchJson<PortfolioItem[]>(`/api/portfolio?${p.toString()}`);
  },
  portfolioUpload: async (
    childId: number,
    subject: string,
    topic: string,
    files: File[],
    note?: string,
  ) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const p = new URLSearchParams({
      child_id: String(childId),
      subject,
      topic,
    });
    if (note) p.set("note", note);
    const r = await fetch(`/api/portfolio/upload?${p.toString()}`, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return (await r.json()) as {
      saved: Array<{
        id: number;
        filename: string;
        mime_type: string | null;
        size_bytes: number | null;
        uploaded_at: string | null;
      }>;
      errors: Array<{ filename: string; error: string }>;
    };
  },
  portfolioDelete: (attachmentId: number) =>
    fetchJson<{ ok: boolean; id: number }>(
      `/api/portfolio/${attachmentId}`,
      { method: "DELETE" },
    ),
  sundayBriefMarkdown: async (childId?: number): Promise<string> => {
    const p = new URLSearchParams({ format: "md" });
    if (childId) p.set("child_id", String(childId));
    const r = await fetch(`/api/sunday-brief?${p.toString()}`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.text();
  },
  ptmBrief: (childId: number) =>
    fetchJson<{
      child_id: number;
      child_name: string;
      class_section: string | null;
      as_of: string;
      headline: string;
      subjects: Array<{
        name: string;
        teacher: string | null;
        n_grades: number;
        avg_pct: number | null;
        direction: string;
        current_state: string;
        talking_points: string[];
        questions_for_teacher: string[];
        evidence_row_ids: number[];
        parent_raised: Array<{
          item_id: number;
          kind: string;
          title: string | null;
          title_en: string | null;
          due_or_date: string | null;
          note: string | null;
        }>;
      }>;
      general_questions: string[];
      things_to_ignore: string[];
      parent_raised_general: Array<{
        item_id: number;
        kind: string;
        title: string | null;
        title_en: string | null;
        due_or_date: string | null;
        note: string | null;
      }>;
      honest_caveat: string;
      llm_used: boolean;
    }>(`/api/ptm-brief?child_id=${childId}`),
  ptmBriefMarkdown: async (childId: number): Promise<string> => {
    const r = await fetch(`/api/ptm-brief?child_id=${childId}&format=md`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.text();
  },
  dailyBrief: (childId?: number, refresh = false) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (refresh) p.set("refresh", "true");
    if (childId) {
      return fetchJson<DailyBrief>(`/api/daily-brief?${p.toString()}`);
    }
    return fetchJson<DailyBrief[]>(`/api/daily-brief?${p.toString()}`);
  },
  sentimentTrend: (childId?: number, windowDays = 28, bucketDays = 7) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    p.set("window_days", String(windowDays));
    p.set("bucket_days", String(bucketDays));
    return fetchJson<SentimentTrend>(`/api/sentiment-trend?${p.toString()}`);
  },
  listNotificationSnoozes: () =>
    fetchJson<NotificationSnooze[]>(`/api/notification-snoozes`),
  addNotificationSnooze: (body: {
    rule_id: string;
    child_id?: number | null;
    until: string;
    reason?: string;
  }) =>
    fetchJson<NotificationSnooze>(`/api/notification-snoozes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteNotificationSnooze: (snoozeId: number) =>
    fetchJson<{ ok: boolean; id: number }>(
      `/api/notification-snoozes/${snoozeId}`,
      { method: "DELETE" },
    ),
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
  // ── practice-prep workspace ─────────────────────────────────────────
  practiceStartSession: (body: {
    child_id: number;
    subject: string;
    topic?: string | null;
    linked_assignment_id?: number | null;
    title?: string | null;
    initial_prompt?: string | null;
    kind?: PracticeKind;
    use_llm?: boolean;
  }) =>
    fetchJson<PracticeSessionOut>(`/api/practice/sessions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  practiceIterateSession: (sessionId: number, parentPrompt: string, useLlm = true) =>
    fetchJson<PracticeSessionOut>(
      `/api/practice/sessions/${sessionId}/iterate`,
      {
        method: "POST",
        body: JSON.stringify({ parent_prompt: parentPrompt, use_llm: useLlm }),
      },
    ),
  practiceGetSession: (sessionId: number) =>
    fetchJson<PracticeSessionOut>(`/api/practice/sessions/${sessionId}`),
  practiceListSessions: (
    childId?: number,
    subject?: string,
    includeArchived = false,
    limit = 100,
  ) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (subject) p.set("subject", subject);
    if (includeArchived) p.set("include_archived", "true");
    p.set("limit", String(limit));
    return fetchJson<PracticeSessionListItem[]>(
      `/api/practice/sessions?${p.toString()}`,
    );
  },
  practiceArchiveSession: (sessionId: number, archive = true) =>
    fetchJson<PracticeSessionOut>(
      `/api/practice/sessions/${sessionId}/archive`,
      { method: "POST", body: JSON.stringify({ archive }) },
    ),
  practiceSetPreferred: (iterationId: number) =>
    fetchJson<PracticeSessionOut>(
      `/api/practice/iterations/${iterationId}/preferred`,
      { method: "POST" },
    ),
  practiceSetSources: (sessionId: number, pinnedSources: PinnedSource[]) =>
    fetchJson<PracticeSessionOut>(
      `/api/practice/sessions/${sessionId}/sources`,
      {
        method: "POST",
        body: JSON.stringify({ pinned_sources: pinnedSources }),
      },
    ),
  practiceIterationMarkdown: async (sessionId: number, iterationId: number) => {
    const r = await fetch(
      `/api/practice/sessions/${sessionId}/iterations/${iterationId}/markdown`,
    );
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.text();
  },
  practiceUploadScans: async (
    childId: number,
    subject: string,
    files: File[],
    sessionId?: number,
    extract = true,
    purpose: ScanPurpose = "classwork_reference",
  ) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const p = new URLSearchParams({
      child_id: String(childId),
      subject,
    });
    if (sessionId) p.set("session_id", String(sessionId));
    p.set("extract", String(extract));
    p.set("purpose", purpose);
    const r = await fetch(`/api/practice/scans/upload?${p.toString()}`, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return (await r.json()) as {
      saved: PracticeClassworkScanOut[];
      errors: Array<{ filename: string; error: string }>;
    };
  },
  practiceScanThumbnailUrl: (scanId: number) =>
    `/api/practice/scans/${scanId}/thumbnail`,
  practiceListScans: (
    childId?: number,
    subject?: string,
    sessionId?: number,
    unboundOnly = false,
  ) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (subject) p.set("subject", subject);
    if (sessionId) p.set("session_id", String(sessionId));
    if (unboundOnly) p.set("unbound_only", "true");
    return fetchJson<PracticeClassworkScanOut[]>(
      `/api/practice/scans?${p.toString()}`,
    );
  },
  practiceBindScan: (scanId: number, practiceSessionId: number | null) =>
    fetchJson<PracticeClassworkScanOut>(
      `/api/practice/scans/${scanId}/bind`,
      {
        method: "POST",
        body: JSON.stringify({ practice_session_id: practiceSessionId }),
      },
    ),
  practiceDeleteScan: (scanId: number) =>
    fetchJson<{ ok: boolean; id: number }>(
      `/api/practice/scans/${scanId}`,
      { method: "DELETE" },
    ),

  worthAChat: (childId?: number, kind?: string, limit = 200) => {
    const p = new URLSearchParams();
    if (childId) p.set("child_id", String(childId));
    if (kind) p.set("kind", kind);
    p.set("limit", String(limit));
    return fetchJson<Assignment[]>(`/api/worth-a-chat?${p.toString()}`);
  },
  assignmentConstants: () =>
    fetchJson<AssignmentConstants>("/api/assignments/constants"),
  resources: (childId?: number) =>
    fetchJson<ResourcesResponse>(`/api/resources${childId ? `?child_id=${childId}` : ""}`),
  topicState: (childId: number) =>
    fetchJson<TopicStateRow[]>(`/api/topic-state?child_id=${childId}`),
  topicDetail: (childId: number, subject: string, topic: string) => {
    const p = new URLSearchParams({
      child_id: String(childId),
      subject,
      topic,
    });
    return fetchJson<TopicDetail>(`/api/topic-detail?${p.toString()}`);
  },
  excellence: (childId: number) =>
    fetchJson<ExcellenceStatus>(`/api/excellence?child_id=${childId}`),
  shakyTopics: (limit = 3) =>
    fetchJson<ShakyTopicsResponse>(`/api/shaky-topics?limit=${limit}`),
  homeworkLoad: (childId: number, weeks = 8) =>
    fetchJson<HomeworkLoadKid>(
      `/api/homework-load?child_id=${childId}&weeks=${weeks}`,
    ),
  homeworkLoadAll: (weeks = 8) =>
    fetchJson<HomeworkLoadAll>(`/api/homework-load?weeks=${weeks}`),
  patterns: (childId: number) =>
    fetchJson<PatternMonth[]>(`/api/patterns?child_id=${childId}`),
  patternsAll: () =>
    fetchJson<PatternsAll>(`/api/patterns`),
  spellbeeLists: (childId: number) =>
    fetchJson<SpellBeeList[]>(`/api/spellbee/lists?child_id=${childId}`),
  spellbeeLinkedAssignments: (childId?: number) =>
    fetchJson<SpellBeeLinkedAssignment[]>(
      `/api/spellbee/linked-assignments${childId ? `?child_id=${childId}` : ""}`,
    ),
  spellbeeUpload: async (childId: number, files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const r = await fetch(`/api/spellbee/upload?child_id=${childId}`, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return (await r.json()) as { saved: SpellBeeList[]; errors: Array<{ filename: string; error: string }> };
  },
  spellbeeDelete: (childId: number, filename: string) =>
    fetchJson<unknown>(`/api/spellbee/list/${childId}/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),
  spellbeeRename: (childId: number, filename: string, newName: string) =>
    fetchJson<SpellBeeList>(
      `/api/spellbee/list/${childId}/${encodeURIComponent(filename)}/rename`,
      { method: "POST", body: JSON.stringify({ new_name: newName }) },
    ),
};

export type SpellBeeLinkedAssignment = {
  id: number;
  child_id: number;
  child_name: string;
  subject: string | null;
  title: string | null;
  title_en: string | null;
  due_or_date: string | null;
  status: string | null;
  detected_list_number: number | null;
  matched_list: SpellBeeList | null;
};
