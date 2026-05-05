/**
 * ItemCommentsThread — parent observation log for one assignment /
 * review / grade row, rendered inline in the AuditDrawer.
 *
 * Why it's structured this way:
 *   Comments are first-class signal for future LLM aggregation. The
 *   capture form deliberately exposes sentiment + topic + tag fields
 *   so the parent can leave the LLM pre-faceted handles ("4 concern-
 *   tagged Math review comments mentioning 'didn't read directions'").
 *
 *   Body is required; everything else is optional. Friction stays low:
 *   you can leave a one-liner without touching the meta fields.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, CommentSentiment, ItemComment } from "../api";
import { formatRelative } from "../util/dates";

const SENTIMENT_OPTIONS: {
  key: CommentSentiment;
  label: string;
  emoji: string;
  cls: string;
}[] = [
  {
    key: "positive",
    label: "Win",
    emoji: "✓",
    cls: "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100",
  },
  {
    key: "neutral",
    label: "Note",
    emoji: "·",
    cls: "border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100",
  },
  {
    key: "concern",
    label: "Concern",
    emoji: "!",
    cls: "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100",
  },
];

export function ItemCommentsThread({ itemId }: { itemId: number }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<ItemComment[]>({
    queryKey: ["item-comments", itemId],
    queryFn: () => api.itemComments(itemId),
  });

  const [body, setBody] = useState("");
  const [sentiment, setSentiment] = useState<CommentSentiment | null>(null);
  const [topic, setTopic] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  // Topic + tags hidden by default — most observations don't need
  // them. Power users can open "More" to add structured handles for
  // LLM aggregation.
  const [showMore, setShowMore] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      api.createItemComment(itemId, {
        body,
        sentiment,
        topic: topic.trim() || null,
        tags: parseTags(tagsRaw),
      }),
    onSuccess: () => {
      setBody("");
      setSentiment(null);
      setTopic("");
      setTagsRaw("");
      setShowMore(false);
      qc.invalidateQueries({ queryKey: ["item-comments", itemId] });
      qc.invalidateQueries({ queryKey: ["item-comment-counts"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteItemComment(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["item-comments", itemId] });
      qc.invalidateQueries({ queryKey: ["item-comment-counts"] });
    },
  });

  const setMutation = useMutation({
    mutationFn: ({
      id,
      next,
    }: {
      id: number;
      next: { sentiment?: CommentSentiment | null };
    }) => api.updateItemComment(id, next),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["item-comments", itemId] }),
  });

  const comments = data ?? [];

  return (
    <section>
      <div className="text-xs font-semibold text-gray-500 uppercase mb-1 flex items-center gap-2">
        <span>Comments</span>
        {comments.length > 0 && (
          <span className="text-[10px] text-gray-500">· {comments.length}</span>
        )}
      </div>

      {/* Capture area. Default state: just textarea + 3 sentiment
          chips + Save. Topic and tags hide behind a "More" toggle —
          they're useful for LLM clustering later but not worth
          showing every parent every time. */}
      <div className="border border-gray-200 rounded p-2 bg-gray-50/40">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => e.stopPropagation()}
          placeholder="What did you notice? e.g. ran out of time, didn't read directions"
          className="w-full text-sm border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-200"
          rows={2}
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {SENTIMENT_OPTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() =>
                  setSentiment((cur) => (cur === s.key ? null : s.key))
                }
                title={`Tag as ${s.label.toLowerCase()}`}
                className={
                  "text-[11px] px-2 py-0.5 rounded border " +
                  (sentiment === s.key
                    ? `border-2 ${s.cls}`
                    : "border-gray-300 bg-white text-gray-500 hover:border-gray-400")
                }
              >
                {s.emoji} {s.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setShowMore((x) => !x)}
            className="text-[11px] text-gray-500 hover:text-gray-800"
            title="Optional: topic + tags help future pattern discovery"
          >
            {showMore ? "less" : "more"}
          </button>
          <button
            type="button"
            onClick={() => {
              if (body.trim() && !create.isPending) create.mutate();
            }}
            disabled={!body.trim() || create.isPending}
            className="ml-auto text-[11px] px-3 py-0.5 rounded bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {create.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        {showMore && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.stopPropagation()}
              placeholder="topic (e.g. fractions)"
              className="text-[11px] border border-gray-300 rounded px-2 py-0.5 w-36"
            />
            <input
              type="text"
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
              onKeyDown={(e) => e.stopPropagation()}
              placeholder="tags, comma-separated"
              className="text-[11px] border border-gray-300 rounded px-2 py-0.5 flex-1 min-w-[100px]"
            />
          </div>
        )}
        {create.isError && (
          <div className="text-xs text-red-700 mt-1">
            {String(create.error)}
          </div>
        )}
      </div>

      {/* Thread */}
      <ul className="mt-3 space-y-2">
        {isLoading && (
          <li className="text-xs text-gray-500 italic">Loading…</li>
        )}
        {!isLoading && comments.length === 0 && (
          <li className="text-xs text-gray-500 italic">
            No comments yet. The first one you add seeds the LLM
            pattern-mining for this kid.
          </li>
        )}
        {comments.map((c) => (
          <li
            key={c.id}
            className={
              "border rounded px-2 py-1.5 text-sm " +
              (c.sentiment === "concern"
                ? "border-amber-200 bg-amber-50/60"
                : c.sentiment === "positive"
                ? "border-emerald-200 bg-emerald-50/60"
                : "border-gray-200 bg-white")
            }
          >
            <div className="flex items-baseline gap-2 flex-wrap">
              {c.sentiment && <SentimentChip kind={c.sentiment} />}
              <span className="text-gray-900 leading-snug whitespace-pre-wrap">
                {c.body}
              </span>
            </div>
            {(c.topic || c.tags.length > 0) && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                {c.topic && (
                  <span className="text-gray-600">
                    topic: <span className="font-medium">{c.topic}</span>
                  </span>
                )}
                {c.tags.map((t) => (
                  <span key={t} className="chip-gray text-[10px]">
                    {t}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-1 flex items-center gap-3 text-[10px] text-gray-500">
              <span title={c.created_at ?? ""}>
                {c.created_at ? formatRelative(c.created_at) : "just now"}
                {c.author !== "parent" && <> · {c.author}</>}
              </span>
              <CycleSentimentLink
                current={c.sentiment}
                onPick={(next) => setMutation.mutate({ id: c.id, next: { sentiment: next } })}
                disabled={setMutation.isPending}
              />
              <button
                type="button"
                onClick={() => {
                  if (
                    confirm("Delete this comment? It's permanently removed.")
                  ) {
                    remove.mutate(c.id);
                  }
                }}
                className="ml-auto text-gray-400 hover:text-red-700"
              >
                delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function SentimentChip({ kind }: { kind: CommentSentiment }) {
  const map: Record<CommentSentiment, { label: string; cls: string }> = {
    positive: { label: "✓ win", cls: "chip-emerald" },
    neutral: { label: "· note", cls: "chip-gray" },
    concern: { label: "! concern", cls: "chip-amber" },
  };
  const m = map[kind];
  return <span className={m.cls}>{m.label}</span>;
}

function CycleSentimentLink({
  current,
  onPick,
  disabled,
}: {
  current: CommentSentiment | null;
  onPick: (s: CommentSentiment | null) => void;
  disabled: boolean;
}) {
  const order: (CommentSentiment | null)[] = [null, "positive", "neutral", "concern"];
  const next = order[(order.indexOf(current) + 1) % order.length];
  const label = next === null ? "clear" : next;
  return (
    <button
      type="button"
      onClick={() => onPick(next)}
      disabled={disabled}
      className="text-blue-700 hover:underline disabled:opacity-50"
      title="Cycle sentiment tag"
    >
      → {label}
    </button>
  );
}
