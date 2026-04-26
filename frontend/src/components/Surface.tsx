/**
 * Surface — the canonical "card" container.
 *
 * Replaces the four+ hand-rolled patterns that were drifting:
 *   bg-white border border-gray-200 rounded shadow-sm
 *   bg-white border border-gray-300 rounded
 *   bg-gray-50 border border-gray-200 rounded
 *   surface (the existing utility class)
 *
 * Variants:
 *   default — bordered card, white surface, soft shadow
 *   flat    — same colors but no shadow (use inside another surface)
 *   muted   — subdued background; for inline alerts / empty states
 *
 * Padding:
 *   none | sm (12 px) | md (16 px, default) | lg (24 px)
 */
type Tone = "default" | "flat" | "muted" | "amber" | "red" | "purple";
type Padding = "none" | "sm" | "md" | "lg";

const TONE_CLASS: Record<Tone, string> = {
  default: "bg-white border border-[color:var(--line)] rounded-lg shadow-sm",
  flat:    "bg-white border border-[color:var(--line)] rounded-lg",
  muted:   "bg-[color:var(--bg-muted)] border border-[color:var(--line)] rounded-lg",
  amber:   "bg-amber-50 border border-amber-200 rounded-lg",
  red:     "bg-red-50 border border-red-200 rounded-lg",
  purple:  "bg-purple-50 border border-purple-200 rounded-lg",
};

const PAD_CLASS: Record<Padding, string> = {
  none: "",
  sm:   "p-3",
  md:   "p-4",
  lg:   "p-6",
};

export function Surface({
  children,
  tone = "default",
  padding = "md",
  className = "",
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & {
  tone?: Tone;
  padding?: Padding;
}) {
  return (
    <div className={`${TONE_CLASS[tone]} ${PAD_CLASS[padding]} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
