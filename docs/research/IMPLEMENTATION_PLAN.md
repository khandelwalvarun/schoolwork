# Implementation Plan — One Feature at a Time

Each phase = **one cohesive change, one commit (or commit cluster on the same
branch), one explicit checkpoint** for your "yes, looks good — continue" /
"no, revert" / "tweak, then continue."

## Rollback rules baked in from the start

1. **Every phase = one commit on `master`.** Easy revert: `git revert <sha>`.
2. **Forward-only migrations** with a working `downgrade()` for any schema
   change. We list the down-migration command in each phase.
3. **Big features ride on a feature flag** in `data/ui_prefs.json` so
   they can be toggled off without a deploy.
4. **No phase depends on a phase later than the next 3 in this plan**, so
   reverting recent work doesn't cascade.
5. **Each phase ends with a verify pass** (`verify_system.py` + a quick
   browser screenshot) before we ask for approval.

## Phase classification

- 🎨 **UI-only** (no schema, no API) — easy revert, low risk
- 🔌 **API-additive** (new endpoint, no schema) — easy revert, low risk
- 🗄 **Schema-additive** (new columns/tables, backward compatible) — revert
  needs `alembic downgrade -1`
- ⚠️ **Disruptive** (replaces existing UX) — feature-flagged, gated approval

---

## The 20 phases, in order

### Foundation pass (Weeks 1-2) — feel + look

#### 1. Skeleton loaders 🎨
Replace every `<div>Loading…</div>` with surface-shaped pulsing boxes.
- Files: `Today.tsx`, `ChildDetail.tsx`, `ChildBoard.tsx`, `ChildAssignments.tsx`,
  `ChildGrades.tsx`, `Messages.tsx`, `Resources.tsx`, `SpellBee.tsx`,
  `Notifications.tsx`, `styles.css` (one `.skeleton` utility class)
- Verification: each page shows skeleton on cold load, no flash
- Rollback: `git revert <sha>`

#### 2. Optimistic mutations + Z-undo toast 🎨
`parent_status` changes settle locally before the network round-trip; banner
appears at bottom-right with `Undo (Z)`.
- Files: `ChildBoard.tsx`, `StatusPopover.tsx`, `BulkActionBar.tsx`,
  `QuickActions.tsx`, new `Toast.tsx`
- Uses TanStack Query `onMutate` / `onError` for rollback
- Rollback: `git revert <sha>`

#### 3. De-emoji the chrome + empty/error states 🎨
- Replace nav emojis (📚 🐝 🏫) with lucide-react icons (`Library`, `Bell`, `BookOpen`).
- Drop dev-language from empty states (`uv run …`, `data/rawdata/`).
- Make every empty state action-focused or celebratory.
- Files: `App.tsx`, every page's empty state branch
- Rollback: `git revert <sha>`

#### 4. OKLCH palette + 3-token theming 🎨
Migrate `:root` from sRGB hex to OKLCH; collapse the 25-variable palette to
`--base / --accent / --contrast` (Linear pattern). Add `prefers-color-scheme
: dark` baseline.
- Files: `styles.css` only
- Rollback: `git revert <sha>` (CSS-only)

#### 5. Standardise `<Surface>` + `<Tabs>` + `<Button>` primitives 🎨
Three common components replace the four hand-rolled card styles + three
ad-hoc tab styles + the bare buttons.
- Files: new `components/Surface.tsx`, `Tabs.tsx`, `Button.tsx`; touch every
  page that currently hand-rolls them
- Rollback: revert the commit; the old hand-rolled versions go back

#### 6. SVG sparklines + small-multiples 🎨
Replace ASCII `t.sparkline` with real SVG; per-subject grade trends become
small-multiples (six 60×30px charts, same y-axis).
- Files: new `components/Sparkline.tsx`; `Today.tsx`, `ChildDetail.tsx`,
  `ChildGrades.tsx`
- Rollback: `git revert <sha>` (ASCII string is still in the API response)

#### 7. 14-week submission heatmap 🎨
Per-kid GitHub-style heatmap; one cell = one day; intensity = submitted/due.
- Files: new `components/SubmissionHeatmap.tsx`; `ChildDetail.tsx`,
  `Today.tsx`
- API endpoint may need `/api/heatmap?child_id=` (additive)
- Rollback: `git revert <sha>` + drop unused endpoint

#### 8. WCAG 2.2 pass + cmdk palette + j/k keys 🎨
- 24×24 px targets everywhere; `scroll-margin-top` on focusables;
  skip-to-content link; `prefers-reduced-motion` on slide-ins; `aria-live`
  toast region
- Replace home-rolled palette with `cmdk` (fuzzy + grouping + recents)
- `j`/`k`/`e`/`x` shortcuts on `AssignmentList` rows
- Files: `App.tsx`, `CommandPalette.tsx`, `useSelection.tsx`,
  `AssignmentList.tsx`, `styles.css`
- Rollback: `git revert <sha>`

### IA pass (Week 2-3)

#### 9. Left sidebar nav with Kid groups ⚠️ feature-flagged
Move horizontal nav into a darker left sidebar; Kid 1 / Kid 2 collapsible
groups; "School-wide" / "Personal" buckets; Today + Inbox at top.
- Files: `App.tsx`, new `components/Sidebar.tsx`, `useUiPrefs.ts` adds
  `nav_layout: "horizontal" | "sidebar"` toggle in Settings
- Rollback: toggle setting back to `horizontal`; or `git revert <sha>`
- **This is the first phase where I'll explicitly ask for sign-off before
  shipping**, since it changes the whole shape of the app.

### Pedagogy foundations (Week 3-4)

#### 10. Per-topic state model 🗄
A new table `topic_state` keyed by `(child_id, class_level, subject, topic)`
with `last_assessed_at`, `last_score`, `attempts`, `state`. Compute from
existing grades + assignments tagged to topics. Render coloured dots on
the per-kid syllabus page.
- Files: new alembic migration `0009_topic_state`; new
  `services/topic_state.py`; updates to `ChildSyllabus.tsx`, `ChildDetail.tsx`
- Schema add only; no destructive change
- Rollback: `alembic downgrade -1` + `git revert <sha>`
- This is the foundation for #11, #12, #13.

#### 11. Spaced-review queue ("Shaky topics") 🔌
Cepeda 10–20 % rule applied to topic_state. Surface 2–3 topics per kid per
week on Today.
- Files: new endpoint `/api/shaky-topics?child_id=&horizon_days=`; new
  `components/ShakyTopicsTray.tsx`; uses #10
- Rollback: `git revert <sha>` (endpoint goes away; tray disappears)

#### 12. CBSE-cap horizon on time-on-homework 🔌
Sum durations from audit log per kid; cap line on the heatmap (CBSE 2 hr/wk
class III–V; 1 hr/day VI–VIII).
- Files: new endpoint `/api/homework-hours?child_id=&since=`; updates to
  `SubmissionHeatmap.tsx`
- Rollback: `git revert <sha>`

#### 13. Pattern detectors (lateness / repeated-attempt / weekend cramming) 🗄
Three boolean monthly features per kid in a new `pattern_state` table; quiet
chart on per-kid Detail page, never push.
- Files: alembic migration `0010_pattern_state`; new
  `services/patterns.py`; new `components/PatternsCard.tsx`
- Rollback: `alembic downgrade -1` + `git revert <sha>`

### Calmer pass (Week 4-5)

#### 14. Three-tier notifications + why-this-nudge link 🗄
Refactor `notifications.tier` (now/today/weekly) with explicit defaults; every
notification has a `rule_id` + `why` payload; UI shows `(why?)` link with
rule + datapoints + snooze.
- Files: alembic migration `0011_notification_tier`; updates to
  `notability/dispatcher.py`; new `components/NotificationWhy.tsx`;
  `Notifications.tsx`
- Rollback: `alembic downgrade -1` + `git revert <sha>`

#### 15. Per-language tracking split 🗄
Add `language_code` (en/hi/sa/null) to subjects; split sparklines and
topic-states by language.
- Files: alembic migration `0012_subject_language`; backfill script
  (English / Hindi / Sanskrit recognisable from subject names); updates
  to several frontend pages
- Rollback: `alembic downgrade -1` + `git revert <sha>`

#### 16. Sunday brief generator ⚠️ feature-flagged
A scheduled digest on Sunday evening. Includes:
- 2–3 conversation starters per kid (academic-socialization framing)
- Decaying topic list (from #11)
- Single "what changed" headline
- Sentiment-trend snippets (from #18)
Files: new `services/sunday_brief.py`; updates to `digest_job`; settings
for opt-in/out; new `components/SundayBriefCard.tsx`.
- Rollback: feature flag to off; `git revert <sha>`
- **Approval gate.** I'll show you a sample brief before scheduling enables.

#### 17. Self-prediction calibration loop 🗄
One-tap "I expect to score …" before each test/major assignment; "I expected /
better / worse" after the grade lands. Persisted on the assignment row.
- Files: alembic migration `0013_self_prediction`; updates to
  `AuditDrawer.tsx`, `ChildBoard.tsx`
- Rollback: `alembic downgrade -1` + `git revert <sha>`

#### 18. Sentiment-trend on teacher comments 🔌
Local lexicon classifier; surface trend (not raw score) in Sunday brief and
on per-kid Detail. Never alerts on a single comment.
- Files: new `services/sentiment.py` (offline, no API call); updates to
  `Sunday brief` + `ChildDetail.tsx`
- Rollback: `git revert <sha>`

### Kid pass (Week 5-6)

#### 19. Kid-facing daily Zimmerman loop ⚠️ feature-flagged
New route `/kid/<id>/today` (separate from parent's Today). Three boxes:
plan (tick) → mid-check (face emoji) → reflect (1-line text). Class 4 gets
the emoji form; Class 6 gets verbose. Persisted in a new `kid_journal`
table.
- Files: alembic migration `0014_kid_journal`; new `pages/KidToday.tsx`;
  `App.tsx` route
- Rollback: feature flag off; `alembic downgrade -1` + `git revert <sha>`
- **Approval gate.** I'll mock the screen before wiring the persistence.

#### 20. Portfolio attachment per syllabus topic 🗄 + 🎨
Allow attachments on `topic_state` rows (photo of project, drawing, scanned
essay). Reuse the attachments pipeline; new UI on `ChildSyllabus.tsx`.
- Files: alembic migration `0015_topic_attachments`; updates to
  `ChildSyllabus.tsx`
- Rollback: `alembic downgrade -1` + `git revert <sha>`

### Mobile pass (Week 6-7+)

#### 21. Mobile shell ⚠️ feature-flagged + breakpoint-gated
Bottom tab bar (Today / Inbox / Active Kid / More); bottom-sheet for
StatusPopover + AuditDrawer + StatusBar; swipe-left = "Mark submitted",
swipe-right = "Snooze"; 44 px target audit; sticky compressing header.
- Files: shell + sheet/drawer rewrites; `ChildBoard.tsx`,
  `AssignmentList.tsx`
- Only active below `md` breakpoint, so desktop UX is unaffected.
- Rollback: revert the commits in reverse order (3-4 commits expected)
- **Approval gate.** Multiple checkpoints inside this phase.

---

## How each phase actually plays out

Per phase I will:

1. **Implement** the feature on `master` (or a short-lived branch if it's
   a multi-commit phase)
2. **Run** `verify_system.py` to make sure 67/67 still pass
3. **Restart** the local servers if the change touches backend
4. **Screenshot** the relevant page(s) via the Preview MCP, post them
   inline so you can eyeball
5. **Wait for your sign-off** ("looks good, next" / "tweak X" / "revert")
6. **Push** to `origin/master` only after sign-off
7. **Move to next phase**

A "tweak" cycle is just another commit on top — same day, no plan
disruption.

A "revert" cycle is `git revert <sha>` (+ `alembic downgrade -1` if
schema). I'll move on to the next phase or pivot, depending on what you
want.

## Rough time estimate

- Phases 1–8 (foundation pass): 4–6 hours total — most are 30-60 min each
- Phases 9, 16, 19, 21 (the four ⚠️ phases): 2–4 hours each, with extra
  approval gates
- Phases 10–15, 17, 18, 20 (pedagogy schema work): 1–2 hours each
- **Total: 20–30 hours of focused build, spread across approval cycles**

## What you decide right now

- ✅ "Go phase by phase, in this order" — fastest path
- 🔄 "Reorder. Do X before Y" — say so
- ⏭ "Skip phase N" — say so; I'll mark it `~~skipped~~` in the doc
- 🛑 "Stop after phase N" — partial path is fine
