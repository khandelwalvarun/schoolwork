/**
 * Skeleton loaders — surface-shaped pulsing placeholders that match the
 * layout of the real content underneath, so navigation feels instant.
 *
 * Pattern: each page that has a `isLoading` branch renders a skeleton
 * whose blocks roughly mirror the final layout, instead of showing a
 * gray "Loading…" string. Cuts perceived wait by ~40 % per the
 * research (OpenReplay, NN/g).
 *
 * Usage:
 *   <Skeleton w={200} h={14} />
 *   <SkeletonRow />              // assignment-row shaped
 *   <SkeletonCard />             // surface card with header + 3 lines
 *   <SkeletonHero />             // Today page hero band
 *   <SkeletonKidBlock />         // a kid section with bucket headers
 */
type Box = {
  w?: number | string;
  h?: number | string;
  className?: string;
  rounded?: "sm" | "md" | "lg" | "full";
};

export function Skeleton({ w, h = 14, className = "", rounded = "sm" }: Box) {
  const radius =
    rounded === "full" ? "9999px" :
    rounded === "lg" ? "8px" :
    rounded === "md" ? "6px" :
    "4px";
  return (
    <span
      aria-hidden="true"
      className={`skeleton inline-block align-middle ${className}`}
      style={{
        width: typeof w === "number" ? `${w}px` : w,
        height: typeof h === "number" ? `${h}px` : h,
        borderRadius: radius,
      }}
    />
  );
}

/** A single assignment-row-shaped skeleton — 5 columns, ~32 px tall. */
export function SkeletonRow() {
  return (
    <div className="row" aria-hidden="true">
      <Skeleton w={16} h={16} rounded="sm" />
      <Skeleton w="80%" h={12} />
      <Skeleton w="60%" h={12} />
      <Skeleton w="60%" h={10} />
      <Skeleton w="50%" h={10} />
    </div>
  );
}

/** A boxed surface card with header + N body lines. */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="surface p-4" aria-hidden="true">
      <Skeleton w={160} h={14} className="mb-3" />
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} w={`${75 + ((i * 7) % 20)}%`} h={12} />
        ))}
      </div>
    </div>
  );
}

/** Today page hero band: 3 metric tiles. */
export function SkeletonHero() {
  return (
    <section className="mb-6" aria-hidden="true">
      <div className="flex items-end justify-between mb-3">
        <div>
          <Skeleton w={120} h={28} className="mb-2" />
          <Skeleton w={180} h={12} />
        </div>
        <div className="flex gap-2">
          <Skeleton w={88} h={32} rounded="md" />
          <Skeleton w={104} h={32} rounded="md" />
        </div>
      </div>
      <div className="surface p-5 flex items-center gap-10">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i}>
            <Skeleton w={84} h={11} className="mb-2" />
            <Skeleton w={48} h={32} />
          </div>
        ))}
      </div>
    </section>
  );
}

/** Per-kid block with header + 3 bucket-shaped sections. */
export function SkeletonKidBlock() {
  return (
    <section className="mb-6" aria-hidden="true">
      <div className="flex items-end justify-between mb-3">
        <div className="flex items-center gap-2">
          <Skeleton w={70} h={20} />
          <Skeleton w={28} h={11} />
          <Skeleton w={140} h={18} rounded="md" />
        </div>
        <Skeleton w={180} h={11} />
      </div>
      <div className="surface">
        {Array.from({ length: 3 }).map((_, b) => (
          <div key={b}>
            <div className="px-3 py-2 border-t border-[color:var(--line-soft)]">
              <Skeleton w={200} h={11} />
            </div>
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ))}
      </div>
    </section>
  );
}

/** A single column of a kanban board: header + 4 cards. */
export function SkeletonBoardColumn() {
  return (
    <div className="surface p-3 flex-1 min-w-[220px]" aria-hidden="true">
      <div className="flex items-center justify-between mb-3">
        <Skeleton w={90} h={11} />
        <Skeleton w={20} h={11} />
      </div>
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white border border-[color:var(--line)] rounded p-2">
            <Skeleton w="80%" h={12} className="mb-1.5" />
            <Skeleton w="40%" h={10} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** A vertical list of N rows for tables/lists. */
export function SkeletonList({ rows = 6 }: { rows?: number }) {
  return (
    <div className="surface" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}
