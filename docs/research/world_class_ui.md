# Parent Cockpit — World-Class UI Research

A 3,500-word audit of the existing app, benchmarked against ten reference
products and the canonical literature. Every claim links to a primary source.
The closing section is a prioritised, effort-rated backlog of 13 changes.

---

## Audit of what's currently shipping

**Strengths.** Tokenised palette in `:root` (`--bg-app`, `--ink-*`, `--line*`).
Restrained 14 px base, system font stack, single accent (#1e40af). One row
component (`.row`) reused across pages. Hover-reveal quick-actions à la
Linear. Working ⌘K palette, `:focus-visible` with offset. Keyboard sort ('s'
on grades), DnD bucket reorder, audit drawer, sync status bar.

**Weaknesses.**

1. The top nav is a horizontal flat list of 12+ items wrapped onto two lines
   on narrow screens; no left sidebar; no clear primary/secondary hierarchy.
2. Surface tokens are inconsistently applied: half the pages use `.surface`,
   the other half hand-roll `bg-white border border-gray-200 rounded
   shadow-sm`.
3. Heavy emoji usage as iconography in nav, headers, page titles. The Linear
   team explicitly identified emoji/icon clutter as the noise to cut.
4. No mobile story. Everything is `max-w-6xl mx-auto` desktop layout.
5. Three different kanban-card / row / grade-row visual languages.
6. Loading is `<div>Loading…</div>` everywhere. No skeletons, no scroll
   preservation, no optimistic updates.
7. Decorative chips are leaking — Board uses 5 different soft-tinted
   backgrounds for columns, adjacent to chips that use the same tints.
   That's "badge soup."

---

## 1. Reference apps — patterns worth stealing

### Linear (the gold standard for calm density)

*Sources: [Linear: How we redesigned the UI part II](https://linear.app/now/how-we-redesigned-the-linear-ui),
[Linear: A calmer interface](https://linear.app/now/behind-the-latest-design-refresh)*

The 2024-25 redesign explicitly pushed **chrome to recede**: the sidebar
darkened by several shades while content stayed bright. Every icon was scaled
down and stripped of coloured backgrounds. The team migrated from HSL → **LCH**
so they could express any theme as just three vars (base, accent, contrast).

Steal:
- **Recede the chrome.** Move global nav into a left sidebar with a darker
  neutral background.
- **Three-token theming** (`--base`, `--accent`, `--contrast`) instead of the
  current 25 individual variables.
- **Reduce icon density**: page-title emojis are the kind of "non-essential
  ornament" Linear killed.

### Superhuman (speed is the product)

*Sources: [Superhuman: Speed as the Product](https://blakecrosley.com/guides/design/superhuman),
[Superhuman keyboard shortcuts PDF](https://download.superhuman.com/Superhuman%20Keyboard%20Shortcuts.pdf)*

Internal target is 50–60 ms per interaction. Vim-style J/K nav, command
palette doubles as a passive shortcut tutor (every command renders its hotkey
beside it — adoption +20 % post-onboarding). 150 ms slide-out animations.
Optimistic UI with a 5-second `Z` undo toast.

Steal:
- **Optimistic mutations + undo toast** for `parent_status` changes.
- **J/K row navigation**: selection model already exists.
- **Command palette shows the shortcut next to each entry**.

### Apple HIG — system-tier polish

*Sources: [Apple HIG home](https://developer.apple.com/design/human-interface-guidelines)*

Steal:
- **Inset-grouped lists** on iPhone-width: a card surface, rounded 10–12 px,
  with internal rows separated by hairlines.
- **Hierarchical push transitions**: 160 ms slide signals depth.
- **Disclosure indicators**: rows that drill down get a subtle right-chevron;
  rows that don't, don't.

### Things 3 (personal task UX, character)

Steal:
- **Checkbox-as-ritual.** Things' is a 16 px circle that fills with a check on
  tap, with a 200 ms ease.
- **One primary action per page**, big and confident. Today's HeroBand has
  *two* equal buttons — pick one as primary blue.

### Notion (density + flexibility)

Steal:
- **Per-kid sidebar groups** like "Private / Shared / Teamspaces": Kid 1 /
  Kid 2 / School-wide / Personal — collapsible, drag-reorderable.
- **Recent items pile** at the top of the sidebar.

### Stripe + Vercel/Geist (data-dense business apps)

Steal:
- **Remove chart titles, add the trend.** Today's HeroBand shows numbers with
  no trend. Stripe always pairs the number with `+12 % vs last week` and a
  60-pixel sparkline.
- **Geist Mono** for any numeric grid (grades %, file sizes, scores).

### Apple Schoolwork / ClassDojo / Toddle / Veracross — peer ed-tech

What works:
- Schoolwork's student home: "tasks due in next 7 days" then "later" — your
  Today page mirrors this.
- Toddle's family app does well at *photos/videos as primary content*.
- Veracross "My Children" lives in a **left sidebar**, which is the layout
  most parents already see at school.

What fails (don't repeat):
- ClassDojo defaults to "Stories" instead of progress — many clicks to
  actually see how their kid is doing.
- Seesaw on phones is "clunky and slow"; messaging requires search instead of
  scroll.

---

## 2. Information architecture

The right top-level shape:

```
Sidebar (left, dark surface, 240 px)
├─ Today                          ⌘1
├─ Inbox  (Messages + Notifications)   ⌘2
├─ ─────
├─ Kid 1  (collapsible)           ⌘3
│   ├─ Overview
│   ├─ Board
│   ├─ Assignments
│   ├─ Grades
│   ├─ Comments
│   └─ Syllabus
├─ Kid 2  (collapsible)           ⌘4
├─ ─────
├─ School-wide
│   ├─ Resources
│   └─ Spell Bee
├─ Personal
│   ├─ Notes
│   └─ Summaries
└─ ─────
   Settings
```

**Why a global Today wins**: parents need a single inbox-zero surface; the
Schoolwork app uses the same pattern. **Inbox vs Search:** merge `Messages` +
`Notifications` into a unified Inbox; add Search as the omnipresent ⌘K result
type.

---

## 3. Type, spacing, colour tokens

### Type scale

```
--text-xs:  11 px  (chip, monospace meta)
--text-sm:  13 px  (table body, secondary)
--text-base:14 px  (UI body — current)
--text-md:  16 px  (read-mode prose, message body)
--text-lg:  18 px  (kid name, section heading)
--text-xl:  22 px  (page title)
--text-2xl: 28 px  (Today's hero number)
```

Drop `text-4xl` from the HeroBand — 36 px-bold-red is shouting at parents who
already feel guilty about overdue homework.

### Colour token upgrade (no full rewrite needed)

```css
:root {
  --bg-app:    oklch(98%  0.005 80);
  --bg-card:   oklch(100% 0     0 );
  --ink-primary:   oklch(20%  0.01  280);
  --accent:    oklch(45%  0.18  260);
  --red:       oklch(55%  0.21  25 );
}
@property --accent { syntax: '<color>'; inherits: true; initial-value: oklch(45% 0.18 260); }
```

Then add a `.dark` selector that flips just three values à la Linear.

---

## 4. Density vs whitespace

| Surface | Audience need | Density target |
|---|---|---|
| `Today` | Scan kids in 5 sec | Linear-dense |
| `ChildBoard` | Drag, decide, drag | Linear-dense |
| `Resources` | Find a PDF | Linear-dense |
| `ChildDetail` overview | Reassurance, not data | Apple-airy |
| `AuditDrawer` (timeline) | Read a story | Apple-airy |
| `Messages` (read body) | Read a story | Apple-airy |
| `Settings` | One thing at a time | Apple-airy |

---

## 5. Mobile

49 % of users are thumb-only; tap accuracy in the natural thumb zone is
**96 %** vs **61 %** in the stretch zone, and 267 % faster.

Essential patterns:
1. **Bottom tab bar** with 4 destinations: Today / Inbox / Kid (active) / More.
2. **Active-kid switcher** as a segmented control above the page title.
3. **Swipe left** = "Mark submitted" (green). **Swipe right** = "Snooze" (amber).
4. **Bottom sheets, not modals**, for `StatusPopover` and `AuditDrawer`.
5. **Sticky page header** compressing on scroll.
6. **44 × 44 px touch targets** minimum.

---

## 6. Data viz that's actually useful

The single best chart for "is the kid on track" is a **GitHub-style 14-week
submission heatmap** — one cell per day, colour intensity = (submitted
assignments / due assignments).

Concrete picks:
- **HeroBand metric tiles**: number + sparkline + delta-vs-7-days-ago.
- **Per-kid grade trends**: small-multiples — six 60 × 30 px line charts, one
  per subject, same y-axis scale.
- **`Today` calendar heatmap**: 14 cols × 2 rows, last 28 days.
- **What NOT to do**: pie charts of subjects, 3D anything, donut charts of
  "completion %".

---

## 7. Empty states / onboarding / errors

Three flavours: **information-focused**, **action-focused**, **celebration-
focused**.

Per page:
- **Today, all caught up**: celebration with one suggested action.
- **Resources / SpellBee empty**: action-focused, drop-zone front and centre.
- **Search no results**: suggest broadening.
- **Sync failed**: include a "Retry" button right there.
- **Onboarding**: a 30-second 3-card carousel on first load.

---

## 8. Performance perception

Optimistic updates make apps perceived **2–3× faster**; immediate visual
feedback cuts perceived wait by **40 %**.

Plan:
1. **Skeletons not spinners.** Replace `<div>Loading…</div>` with surface-
   shaped grey boxes that pulse.
2. **Optimistic mutations** for `parent_status`. React Query `onMutate` to set
   the cache, `onError` to roll back.
3. **Undo toast** (`Z`) on every mutation, 5 sec window.
4. **Scroll restoration**: React Router v6's `<ScrollRestoration />`.
5. **Prefetch on hover.**
6. **Targeted query keys.** Don't `invalidateQueries()` with no args.

---

## 9. Accessibility (WCAG 2.2)

1. **Target Size (2.5.8, AA)** — 24 × 24 CSS px minimum.
2. **Focus Not Obscured (2.4.11, AA)** — sticky header can hide a focused row;
   add `scroll-margin-top: 80 px`.
3. **Focus indicator contrast** 3:1, ≥ 2 px.
4. **Don't rely on colour alone** — overdue red is paired with "Overdue"
   label (good); grade trend arrows are colour-only — add explicit "+3 %" or
   "↑ improving" text.
5. **Skip-to-content link** at the top.
6. **`prefers-reduced-motion`** — slide-ins should be no-ops.
7. **`aria-live="polite"` toast region** for sync results, undo toasts.

---

## 10. Anti-patterns to avoid

- **Emoji as primary navigation** — currently rampant. Replace with proper
  icons.
- **Badge soup** — Board's column tints match chip backgrounds. Pick one role
  per tint.
- **Modal-on-modal** — currently `AuditDrawer` can be open while
  `StatusPopover` opens.
- **Dev language in prod UI** — `data/rawdata/` and `uv run …` shouldn't
  appear.
- **`alert()` and `confirm()`** for delete. Use real dialogs / toasts.

---

## Prioritised backlog — 13 changes

| # | Change | Pages touched | Effort | Why |
|---|---|---|---|---|
| 1 | **Move global nav to a left sidebar** with Today / Inbox / Kid groups | `App.tsx` | M | Resolves IA flatness; chrome can recede. |
| 2 | **Replace `<div>Loading…</div>` with surface-shaped skeletons** | every page | S | 40 % perceived-wait reduction. |
| 3 | **Optimistic `parent_status` mutations + Z-undo toast** | `ChildBoard`, `StatusPopover`, `BulkActionBar`, `Today` | M | 2-3× perceived speed. |
| 4 | **Mobile bottom-tab nav + bottom-sheet modals + swipe row actions** | shell + `AuditDrawer`, `StatusPopover`, `AssignmentList` | L | Parents check on phones. |
| 5 | **De-emoji the chrome.** Replace emoji titles with neutral lucide icons | every page | S | Calmer-UI lever. |
| 6 | **Migrate `:root` to OKLCH + 3-token theming** | `styles.css` | S | Wider gamut, AAA-ready dark theme cheap. |
| 7 | **Replace ASCII sparklines with SVG sparklines + small-multiples** | Today, ChildDetail, ChildGrades | M | Tufte's intent + a11y. |
| 8 | **Add a 14-week submission heatmap** to each kid's overview | ChildDetail, Today | M | Best "on-track?" visual. |
| 9 | **Upgrade command palette** to `cmdk` with fuzzy search, grouping, recents | CommandPalette | S | Best-practice baseline. |
| 10 | **Empty / error states with one clear action** per page; remove dev language | Resources, SpellBee, Today, Messages | S | First-impression UX. |
| 11 | **Standardise on `<Surface>` + `<Tabs>` + `<Button>` components** | every page | M | Constraint = style. |
| 12 | **A11y pass**: 24 × 24 px targets, scroll-margin-top, skip-to-content | global | S | WCAG 2.2 AA conformance. |
| 13 | **`j`/`k`/`e`/`x` keyboard nav** on assignment lists | AssignmentList, useSelection | S | Power-user delight. |

**Top three to do first:** #2 skeletons (1 day, biggest perception win),
**#1 sidebar** (3 days, biggest IA win), **#3 optimistic + undo** (2 days,
biggest interaction win). Together they make the app feel like a different
product.
