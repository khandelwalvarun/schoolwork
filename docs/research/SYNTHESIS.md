# Synthesis — Pedagogy ⨯ UI

Both research passes converge on a single thesis:

> **The current cockpit shows _events_. A great cockpit shows _meaning_,
> calmly, and earns the right to interrupt.**

Mapped concretely:

- _Events_ today: every grade, every assignment, every comment as separate rows
  with a status chip. We watch and react.
- _Meaning_ tomorrow: per-topic mastery state with decay; trends, not points;
  a Sunday brief instead of real-time pings; CBSE-cap awareness; conversation
  starters instead of action items; a kid-facing self-regulation loop.

This synthesis picks the **8 changes** where the pedagogy and UI sides agree
strongly enough that they should ship together.

---

## The eight

### 1. Per-topic mastery model with half-life decay
Pedagogy lever: Khan-style heuristics + Cepeda 10–20 % review window.
UI lever: small-multiples of subject sparklines, colored topic dots
(attempted / familiar / proficient / mastered / decaying).
Effort: M backend, M frontend.
**This is the foundation everything else hangs from.**

### 2. Sunday parent brief (replaces real-time pings)
Pedagogy lever: Hill & Tyson — academic socialization is r = +0.39; direct
homework help is r = −0.11. Calm tech.
UI lever: empty-state celebration ("All caught up. Read this Sunday's brief →").
Effort: M backend (digest job exists), S frontend.
Outcome: parents check the cockpit on Sunday evening for 5 minutes, talk to the
kids over dinner, close the tab. That's the win.

### 3. Three-tier notifications: Now / Today / Weekly
Pedagogy lever: Calm tech; Hattie says task-level feedback is the weakest
kind; helicopter-parenting risk.
UI lever: every alert has a `(why?)` link + snooze; default high-grade alerts
to weekly only.
Effort: M backend (channels exist, need tiering), S frontend.

### 4. Kid-facing daily Zimmerman loop
Pedagogy lever: EEF says metacognition + self-regulation = +8 months
progress, lowest cost. Direct meta-analyses: effective from age 5+.
UI lever: a separate `/kid/<id>/today` view with three boxes — *plan*,
*mid-check* (face emoji), *reflect* (1-line). Not for the parent.
Effort: M.
**Most underrated build.** Tejas (12) gets verbose; Sam (9) gets emoji form.

### 5. CBSE-cap aware time-on-homework counter
Pedagogy lever: Cooper meta-analysis + CBSE Circular 52/2020 (2 hr/wk for
III–V; 1 hr/day for VI–VIII).
UI lever: horizontal cap line on the heatmap; if exceeded N consecutive weeks,
surface "talk to school" — not "do more homework."
Effort: S.

### 6. Mobile-first shell (bottom tabs + bottom sheets + swipe actions)
UI lever: parents check on phones; thumb-zone tap accuracy 96 % vs 61 %.
Pedagogy lever: 5-minute Sunday brief is most likely consumed on a phone.
Effort: L. (Worth it.)

### 7. Sidebar IA + de-emoji + skeletons + optimistic mutations
UI levers, four small wins that compound:
- left sidebar with Kid groups → resolves IA flatness
- skeletons → 40 % perceived-wait cut
- optimistic + Z-undo → 2-3× perceived speed
- de-emoji the chrome → calmer
Effort: S/M each.
**Do these together as one "feel" pass.**

### 8. 14-week submission heatmap (per kid)
UI lever: single best chart for "is this kid on track?" — already-familiar
GitHub pattern.
Pedagogy lever: shows the trend research demands instead of single events;
the cap line from #5 lives here.
Effort: M.

---

## What we explicitly say no to

- **Growth-mindset coach.** Sisk et al. 2018 + Case Western: benefits "largely
  overstated." Dweck herself walked it back.
- **Learning-styles segmentation.** Effect size ~0 across four+ meta-analyses.
- **Deep Knowledge Tracing or any per-event ML.** N=2 children. Replication
  fails even with millions of events; it would just be theatre.
- **Real-time push for grades.** Empirically drives parents to ignore the
  channel entirely. Helicopter-parenting risk per Springer 2024 meta-analysis.
- **Auto-suggest "do this together."** Patall et al. 2008: ⅔ of parents give
  unconstructive homework help; the most evidence-based design choice is to
  *withhold* this suggestion.

---

## Suggested execution order

**Week 1 — feel pass (UI #2/#3/#5/#9 from the UI list):**
- Skeletons everywhere (1 day)
- Optimistic mutations + `Z` undo toast (2 days)
- De-emoji + standardise card / surface / chip primitives (1 day)
- Move global nav into left sidebar with Kid groups (2 days)

After Week 1 the app *feels* like a different product. Same data, calmer
surface.

**Week 2 — content pass (Synthesis #1 + #8):**
- Per-topic state model (backend)
- Render colored topic dots on per-kid pages
- Replace ASCII sparklines with SVG sparklines + small-multiples
- Add 14-week submission heatmap

After Week 2 the app *says* something useful, not just lists events.

**Week 3 — calmer pass (Synthesis #2 + #3 + #5):**
- Three-tier notifications with `(why?)` link + snooze
- Sunday brief generation (digest job exists; reskin output)
- CBSE-cap horizon line on the heatmap

After Week 3 the app *interrupts less* and what it does say is more useful.

**Week 4 — kid pass (Synthesis #4):**
- `/kid/<id>/today` view distinct from parent Today
- Plan / mid-check / reflect three-box flow
- Self-prediction calibration loop on tests
- Reflect-after-grade one-tap

After Week 4 the kid is in the loop, not just being watched.

**Week 5+ — mobile pass (Synthesis #6):**
- Bottom tabs
- Bottom sheets for modals
- Swipe actions on rows
- 44 px target audit

After Week 5 the parent can run it from a phone in 30 seconds at school
pickup.

---

Total: ~5 weeks of focused work to take the app from "data dashboard" to
"parenting tool informed by evidence." Most build is straightforward;
the leverage comes from picking the right things to build.
