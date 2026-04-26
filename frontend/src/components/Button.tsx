/**
 * Button — the canonical action element.
 *
 * Variants:
 *   primary    bold blue, used once per page (Things 3 rule)
 *   secondary  white surface + neutral border (default for Sync, Refresh, etc.)
 *   ghost      no border, hover bg only
 *   danger     red surface for destructive actions
 *
 * Sizes: sm (h-7) | md (h-9, default) | lg (h-11).
 *
 * Bonus: built-in disabled + loading state with spinner. Loading suppresses
 * the click + keeps width stable (pulses a skeleton bar over the label).
 */
import { ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VAR_CLASS: Record<Variant, string> = {
  primary:
    "bg-blue-700 text-white border border-blue-800 hover:bg-blue-800 active:bg-blue-900 disabled:bg-blue-400",
  secondary:
    "bg-white text-gray-800 border border-[color:var(--line)] hover:bg-gray-50 active:bg-gray-100 disabled:opacity-50",
  ghost:
    "bg-transparent text-gray-700 border border-transparent hover:bg-gray-100 active:bg-gray-200",
  danger:
    "bg-red-600 text-white border border-red-700 hover:bg-red-700 active:bg-red-800 disabled:bg-red-300",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "h-7 px-2 text-xs gap-1",
  md: "h-9 px-3 text-sm gap-1.5",
  lg: "h-11 px-4 text-base gap-2",
};

export function Button({
  children,
  variant = "secondary",
  size = "md",
  loading = false,
  leftIcon,
  rightIcon,
  className = "",
  disabled,
  ...rest
}: Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={
        "inline-flex items-center justify-center rounded transition-colors disabled:cursor-not-allowed " +
        `${VAR_CLASS[variant]} ${SIZE_CLASS[size]} ${className}`.trim()
      }
    >
      {loading ? (
        <span className="inline-flex items-center gap-1.5">
          <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.25" />
            <path d="M12 2 a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" fill="none" />
          </svg>
          <span className="opacity-70">{children}</span>
        </span>
      ) : (
        <>
          {leftIcon}
          <span>{children}</span>
          {rightIcon}
        </>
      )}
    </button>
  );
}
