/**
 * Centralised UI strings — single source of truth for parent-facing
 * vocabulary. The cockpit's database/API uses system-language column
 * names (`parent_status`, `effective_status`, `discuss_with_teacher_at`,
 * "off-trend", "median", etc.); the UI must read in plain English.
 *
 * Never expose internal jargon (MAD, z-score, mastery_decay) to the
 * parent. If you need to surface a system value here, add a mapping —
 * don't render the raw key.
 *
 * Goal: a parent who has never used a productivity app should be able
 * to read every label and know what it means.
 */

import type {
  AnomalyStatus,
  CommentSentiment,
  ParentStatus,
  SelfPredictionOutcome,
} from "../api";

/** Effective row status — what the parent SEES on a row chip.
 *  Plain-English; lower-case (the chip itself can render whatever case). */
export const EFFECTIVE_STATUS_LABEL: Record<string, string> = {
  graded: "graded",
  submitted: "handed in",
  done_at_home: "done",
  in_progress: "in progress",
  needs_help: "needs help",
  blocked: "blocked",
  skipped: "skipped",
  overdue: "overdue",
  pending: "pending",
};

/** Parent-set status — the option labels in the StatusPopover. */
export const PARENT_STATUS_LABEL: Record<ParentStatus, string> = {
  in_progress: "In progress",
  done_at_home: "Done at home",
  submitted: "Handed in",
  needs_help: "Needs help",
  blocked: "Blocked",
  skipped: "Skipped",
};

/** Three-bucket category — what the H/R/C leading badge means in
 *  prose. Used for tooltips and aria-labels on the CategoryChip. */
export const WORK_CATEGORY_LABEL: Record<
  "homework" | "review" | "classwork",
  string
> = {
  homework: "Homework",
  review: "Test or quiz",
  classwork: "Done in class",
};

/** Anomaly-flag acknowledgement state — what each chip means. */
export const ANOMALY_STATUS_LABEL: Record<AnomalyStatus, string> = {
  open: "open",
  reviewed: "reviewed",
  dismissed: "dismissed",
  escalated: "escalated",
};

/** Sentiment tag on a parent comment. */
export const COMMENT_SENTIMENT_LABEL: Record<CommentSentiment, string> = {
  positive: "Win",
  neutral: "Note",
  concern: "Concern",
};

/** Self-prediction outcome (after a grade lands). */
export const SELF_PREDICTION_OUTCOME_LABEL: Record<
  SelfPredictionOutcome,
  string
> = {
  matched: "matched their guess",
  better: "better than they guessed",
  worse: "below their guess",
};

/** Anomaly-detection vocabulary. The detector says "off-trend" or
 *  "MAD>3"; parents see this. */
export function anomalyHeadline(direction: "below" | "above"): string {
  return direction === "below" ? "Unexpected dip" : "Above usual";
}

/** Page-level copy. Centralised so a tone change is one edit, not 30. */
export const COPY = {
  // Today
  todayHero: "Today",
  todaySync: "Sync now",
  todaySendDigest: "Send digest",
  todayAcrossKids: "Across both kids:",
  // ChildDetail
  childDetailPTM: "PTM brief",
  childDetailSunday: "Sunday brief",
  // Audit drawer
  drawerMore: "More",
  drawerActivity: "Activity",
  // Worth-a-chat
  worthAChatTitle: "Worth a chat at PTM",
  worthAChatAddReason: "+ add reason",
  worthAChatPlaceholder: "reason for chat",
  // Anomaly
  anomalyTitle: "Off-trend grades",
  anomalyDismiss: "✓ ack",
  anomalyWhy: "why?",
  // Comments
  commentsTitle: "Comments",
  commentsPlaceholder: "What did you notice? e.g. ran out of time, didn't read directions",
  commentsSave: "Save",
  // Status
  statusEdit: "Edit status",
} as const;
