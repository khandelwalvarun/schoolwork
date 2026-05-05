/**
 * Canonical chip vocabulary — single source of truth for status pills.
 *
 * Before this, every component re-rolled chip styles inline (e.g.
 * "bg-red-100 text-red-800 border-red-200 px-1.5 py-0 rounded"), so
 * subtle drift was inevitable: some used py-0, some py-0.5, some
 * rounded, some rounded-full. Three or four near-identical anomaly-
 * status chips lived in the codebase.
 *
 * If you need a status pill, USE ONE OF THESE. If your status doesn't
 * fit any of these, add it here first.
 */
import { ReactNode } from "react";
import type { AnomalyStatus } from "../api";

/** Generic Chip — matches the `.chip-*` classes in styles.css. The
 *  named tone variants are pre-styled; pass `tone` to pick. */
export function Chip({
  tone = "gray",
  title,
  children,
  className = "",
}: {
  tone?:
    | "red"
    | "amber"
    | "blue"
    | "green"
    | "purple"
    | "gray"
    | "violet"
    | "emerald";
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`chip-${tone} ${className}`} title={title}>
      {children}
    </span>
  );
}

/** Off-trend grade acknowledgement state. Used in the GradeAnomalyCard
 *  on the grades page and in the AnomalyTray on Today. */
export function AnomalyStatusChip({ status }: { status: AnomalyStatus }) {
  const map: Record<AnomalyStatus, { label: string; tone: Parameters<typeof Chip>[0]["tone"] }> = {
    open: { label: "open", tone: "red" },
    reviewed: { label: "reviewed", tone: "blue" },
    dismissed: { label: "dismissed", tone: "gray" },
    escalated: { label: "escalated", tone: "violet" },
  };
  const m = map[status];
  return <Chip tone={m.tone} title={`Anomaly status: ${m.label}`}>{m.label}</Chip>;
}

/** Worth-a-chat at PTM — parent-flagged for the next teacher meeting.
 *  `compact` shows a tight "💬 PTM" pill (for assignment rows where
 *  space is precious); default shows the full "💬 worth a chat". */
export function WorthAChatChip({
  note,
  compact = false,
}: {
  note?: string | null;
  compact?: boolean;
}) {
  return (
    <Chip
      tone="violet"
      title={note ? `Worth a chat at PTM — ${note}` : "Worth a chat at PTM"}
    >
      {compact ? "💬 PTM" : "💬 worth a chat"}
    </Chip>
  );
}

/** Three-bucket schoolwork category — Homework / Review / Classwork.
 *  Used as a leading badge on every assignment row.
 *  Sized 20×20 (w-5 h-5) with 10px letter — readable when scanning a
 *  long list. Colour follows the documented precedence in styles.css:
 *  blue=link/primary, purple=system-classified, gray=neutral. */
export function CategoryChip({
  category,
}: {
  category: "homework" | "review" | "classwork" | null | undefined;
}) {
  const c = category || "homework";
  const meta = {
    homework: { letter: "H", tone: "blue" as const, label: "Homework" },
    review: { letter: "R", tone: "purple" as const, label: "Review" },
    classwork: { letter: "C", tone: "gray" as const, label: "Classwork (in class)" },
  }[c];
  return (
    <span
      className={
        "shrink-0 inline-flex items-center justify-center w-5 h-5 rounded text-white text-meta font-bold " +
        (c === "homework"
          ? "bg-blue-600"
          : c === "review"
          ? "bg-purple-600"
          : "bg-gray-500")
      }
      title={meta.label}
      aria-label={meta.label}
    >
      {meta.letter}
    </span>
  );
}

/** Sync state on the Today hero. */
export function SyncStateChip({
  ok,
  never,
}: {
  ok: boolean;
  never: boolean;
}) {
  if (never) return <Chip tone="gray">Never synced</Chip>;
  return ok ? (
    <Chip tone="emerald">✓ Synced</Chip>
  ) : (
    <Chip tone="red">✗ Sync failed</Chip>
  );
}
