# Parent Cockpit — Build Specification v2

**Version:** v2.0 (supersedes v1.0)
**Scope:** Parent-facing tracker for two children (Tejas, Class 6B; Samarth, Class 4C at Vasant Valley) that ingests Veracross data hourly, overlays the parsed syllabus for context, maintains a proper event history, and fires notifications only when something genuinely warrants your attention. The 4pm digest is the anchor check-in; notifications fill the gaps between.
**Child-facing component:** explicitly out of scope for v2. Revisit after 3-6 months of daily use.
**Success criterion:** the thing you check when you want the state of the world, plus the thing that pings your phone only when a ping is earned.

---

## 1. What changed from v1 and why

v1 treated this as a "parent cockpit with a daily briefing." After seeing the Cowork digest you already find useful, the framing is wrong. What you actually need is:

> **A backlog-and-trend tracker, with a notability engine that notifies you only when something warrants interrupting, a scheduled 4pm digest that gives you the state of the world, and a web UI for when you want to drill in.**

The tables are the product. The prose briefing is a short preamble. The notability engine is the heart — it's what lets the system run every hour without becoming spam.

Three additions relative to v1:

1. **Hourly cron** (not nightly), feeding an event stream
2. **Notability engine** that scores events and fires notifications above a per-channel threshold
3. **Multi-channel notifications** (Telegram + email + in-app), configurable per event kind

---

## 2. Principles (updated)

Unchanged from v1 except as noted:

1. Fewer screens, not more.
2. **The tables are the product.** The briefing prose is a 3-5 sentence preamble.
3. **Notifications are earned, not automatic.** A notification that doesn't change your behavior is noise. If we can't say what you'd do differently, we don't fire.
4. Don't create work for yourself. No task management, no action tracking. Just observation.
5. LLM output must be specific and quantitative. No cheerleading.
6. Respect the spouse. Legible without prior context.
7. No surprises. All failures visible in the UI.
8. Cheap to rebuild. Six months offline and everything still makes sense.
9. **Every event is persisted, even the ones that don't fire.** Debugging and retuning the notability rubric depends on this.

---

## 3. System architecture

```
                  ┌──────────────────────────────────────┐
                  │  Browsers / phones                   │
                  │  Web UI: Vite + React on LAN         │
                  │  Telegram: your private bot          │
                  │  Email: scheduled digests + critical │
                  └──────┬───────────────────┬───────────┘
                         │                   │
                         │ HTTP              │ Telegram Bot API
                         │                   │ SMTP
                  ┌──────▼───────────────────▼───────────┐
                  │          FastAPI app                 │
                  │                                      │
                  │  ┌────────────┐  ┌─────────────────┐ │
                  │  │ Web API    │  │ Notification    │ │
                  │  │ (React)    │  │ dispatcher      │ │
                  │  └────────────┘  └─────────────────┘ │
                  │                                      │
                  │  ┌──────────────────────────────────┐│
                  │  │ Notability engine                ││
                  │  │ - event producers                ││
                  │  │ - rubric scoring                 ││
                  │  │ - dedup / suppression            ││
                  │  └──────────────────────────────────┘│
                  │                                      │
                  │  ┌──────────────────────────────────┐│
                  │  │ APScheduler                      ││
                  │  │ - hourly sync (08:00–22:00 IST)  ││
                  │  │ - 16:00 digest job               ││
                  │  │ - Sunday 20:00 weekly digest     ││
                  │  │ - nightly backup                 ││
                  │  └──────────────────────────────────┘│
                  └──┬─────────────┬────────────┬────────┘
                     │             │            │
              ┌──────▼─────┐ ┌─────▼─────┐ ┌────▼─────────┐
              │  SQLite    │ │  Claude   │ │  Veracross   │
              │  (WAL)     │ │  API      │ │  Playwright  │
              │  app.db    │ │           │ │  scraper     │
              └────────────┘ └───────────┘ └──────────────┘
```

### What changed from v1 architecture
- Added the **notability engine** as a first-class component, not a feature of the briefing job
- Added the **notification dispatcher** with per-channel, per-event-kind routing
- Sync is **hourly during waking hours (08:00–22:00 IST)**, not nightly
- Telegram and SMTP are in the critical path for Weekend 2

### What is still the same
- One FastAPI app, one SQLite file, one React frontend. No microservices.
- Playwright scraper in-process.
- APScheduler in-process, no separate cron container.
- Deployable with `docker compose up`.

---

## 4. Data model

Seven tables now. The two additions from v1 are `events` and `notifications`. One field added to `veracross_items` (`seen_at`). Everything else unchanged.

```sql
CREATE TABLE children (
    id              INTEGER PRIMARY KEY,
    display_name    TEXT NOT NULL,         -- 'Tejas', 'Samarth'
    class_level     INTEGER NOT NULL,      -- 6, 4
    class_section   TEXT,                   -- '6B', '4C'
    school          TEXT NOT NULL DEFAULT 'Vasant Valley',
    veracross_id    TEXT,
    syllabus_path   TEXT,
    settings        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE veracross_items (
    id              INTEGER PRIMARY KEY,
    child_id        INTEGER NOT NULL REFERENCES children(id),
    kind            TEXT NOT NULL,
    -- 'assignment' | 'grade' | 'comment' | 'attendance'
    -- | 'message' | 'report_card' | 'schedule_item' | 'school_message'
    external_id     TEXT NOT NULL,
    subject         TEXT,
    title           TEXT,
    due_or_date     TEXT,
    raw_json        TEXT NOT NULL,
    normalized_json TEXT,
    status          TEXT,
    -- 'new' | 'seen' | 'assigned' | 'submitted' | 'graded' | 'overdue' | 'dismissed'
    seen_at         TEXT,     -- set when you view the digest containing this item
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (child_id, kind, external_id)
);

CREATE INDEX idx_vc_items_child_kind_date
    ON veracross_items(child_id, kind, due_or_date DESC);
CREATE INDEX idx_vc_items_status
    ON veracross_items(status);

-- NEW: every event ever computed, even if it didn't fire
CREATE TABLE events (
    id              INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL,
    -- 'new_assignment' | 'grade_posted' | 'grade_outlier' | 'comment_short'
    -- | 'comment_long' | 'school_message' | 'overdue_3d' | 'overdue_7d'
    -- | 'backlog_accelerating' | 'subject_concentration' | 'first_grade_of_cycle'
    -- | 'scraper_drift' | 'sync_failed'
    child_id        INTEGER REFERENCES children(id),
    subject         TEXT,
    related_item_id INTEGER REFERENCES veracross_items(id),
    payload_json    TEXT NOT NULL,
    notability      REAL NOT NULL,          -- 0.0–1.0
    dedup_key       TEXT NOT NULL,           -- so same event doesn't re-fire
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dedup_key)
);

CREATE INDEX idx_events_child_time ON events(child_id, created_at DESC);

-- NEW: notifications derived from events, per channel
CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES events(id),
    channel         TEXT NOT NULL,           -- 'telegram' | 'email' | 'inapp' | 'digest'
    status          TEXT NOT NULL,           -- 'pending' | 'sent' | 'failed' | 'suppressed'
    attempted_at    TEXT,
    delivered_at    TEXT,
    error           TEXT,
    message_preview TEXT                      -- first 200 chars for debugging
);

CREATE INDEX idx_notif_event ON notifications(event_id);
CREATE INDEX idx_notif_status ON notifications(status);

-- Rest unchanged from v1
CREATE TABLE parent_notes (
    id              INTEGER PRIMARY KEY,
    child_id        INTEGER REFERENCES children(id),
    note            TEXT NOT NULL,
    tags            TEXT,
    note_date       TEXT NOT NULL DEFAULT (date('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE summaries (
    id              INTEGER PRIMARY KEY,
    child_id        INTEGER REFERENCES children(id),
    kind            TEXT NOT NULL,           -- 'digest_4pm' | 'weekly' | 'cycle_review'
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    content_md      TEXT NOT NULL,
    stats_json      TEXT NOT NULL,
    model_used      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (child_id, kind, period_start)
);

CREATE TABLE llm_calls (
    id              INTEGER PRIMARY KEY,
    purpose         TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_inr        REAL,
    input_hash      TEXT,
    success         INTEGER NOT NULL,
    error           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sync_runs (
    id              INTEGER PRIMARY KEY,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    trigger         TEXT NOT NULL,           -- 'hourly' | 'manual' | 'startup'
    status          TEXT NOT NULL,
    items_new       INTEGER DEFAULT 0,
    items_updated   INTEGER DEFAULT 0,
    events_produced INTEGER DEFAULT 0,
    notifications_fired INTEGER DEFAULT 0,
    error           TEXT,
    warnings        TEXT
);
```

---

## 5. The notability engine

This is the new heart of the system. Its job is to decide: given what changed in the last sync, does any of it warrant a notification, and on which channel?

### 5.1 Event production

After each sync, the engine walks the diff and produces zero or more events. Each event has:

- a **kind** (from a finite enum)
- a **child_id** (or null for family-level events)
- a **payload** (whatever context the notification will need)
- a **notability score** (0.0 to 1.0)
- a **dedup_key** (so we don't re-fire the same thing)

The dedup_key is critical. Examples:
- `overdue_3d:child=1:item=42` — fires once when item 42 crosses the 3-day-overdue line
- `backlog_accelerating:child=2:week=2026-W17` — at most once per week per kid
- `grade_outlier:child=1:subject=Maths:item=103` — once per outlier grade

### 5.2 Event kinds and notability scores (v1 rubric)

| Event kind | Score | Meaning | When to fire |
|---|---|---|---|
| `new_assignment` | 0.1 | Routine assignment posted | Never notify; shows in digest |
| `assignment_submitted` | 0.1 | Kid submitted something | Never notify |
| `grade_posted_routine` | 0.2 | Grade within ±1σ of subject trend | Never notify |
| `grade_posted_outlier` | 0.7 | Grade >1σ off recent trend (either direction) | Notify |
| `comment_short` | 0.5 | Teacher comment <30 words | Digest only |
| `comment_long` | 0.8 | Teacher comment ≥30 words | Notify |
| `school_message` | 0.6 | Anything in school-wide Messages section | Notify |
| `overdue_3d` | 0.6 | Item crossed 3-days-overdue line | Notify |
| `overdue_7d` | 0.9 | Item crossed 7-days-overdue line | Notify immediately |
| `backlog_accelerating` | 0.7 | Child's overdue count up >50% in 48h | Notify (max 1/week/kid) |
| `subject_concentration` | 0.7 | Single subject >40% of child's overdue (≥4 items) | Notify (max 1/week/subject) |
| `first_grade_of_cycle` | 0.5 | First graded item after a new LC starts | Digest only |
| `report_card_posted` | 0.9 | New report card appears | Notify immediately |
| `scraper_drift` | 0.8 | Scraper saw fewer-than-expected rows | Notify me (not spouse) |
| `sync_failed` | 1.0 | Sync errored out entirely | Notify me |

### 5.3 Channel routing

Each notification channel has a threshold and a per-event-kind mute list. Configurable in settings, stored as JSON in a `channel_config` row.

```yaml
# Default config (settings view can edit)
channels:
  telegram:
    enabled: true
    threshold: 0.6
    mute_kinds: []
    rate_limit:
      max_per_hour: 4
      quiet_hours_ist: "22:00-07:00"   # no sends during sleep
  email:
    enabled: true
    threshold: 0.8              # only high-notability → email
    mute_kinds: []
    rate_limit:
      max_per_day: 6
  inapp:
    enabled: true
    threshold: 0.0              # everything visible in UI's notifications pane
    mute_kinds: []
  digest:                       # the 4pm and weekly digests
    enabled: true
    delivery:
      - telegram
      - email
      - inapp
```

The dispatcher reads this config on each event and decides which channels to fire on. A channel might be skipped if:
- `enabled: false`
- score below `threshold`
- event kind in `mute_kinds`
- rate limit exceeded
- currently in `quiet_hours_ist`
- the dedup_key was already delivered on this channel

### 5.4 The 4pm digest is a notification too

It's just an event of kind `digest_4pm` with notability 1.0, fired by APScheduler at 16:00 IST daily. The digest content is the full state — overdue tables, due-today, upcoming, school messages, grade trends, brief LLM prose at top. Same content rendered for three channels (Telegram: plain text with emoji headers; Email: HTML; In-app: the `/` view).

### 5.5 Retuning the rubric

After 2-4 weeks of real use, you'll have opinions. The design makes retuning cheap:

- All events are in the `events` table, with their scores
- All notifications (including suppressed ones) are in `notifications`
- A small settings page lets you tweak `threshold` and `mute_kinds` per channel
- A "replay" button re-computes notifications for the last 7 days under new config, so you can see what would have fired differently

---

## 6. Veracross integration

Largely unchanged from v1 §5, but hourly instead of nightly.

### 6.1 Sync schedule
- Hourly between 08:00 and 22:00 IST (15 syncs/day)
- Also on manual trigger from the UI
- Also once at app startup (catch up after downtime)
- Skipped during declared quiet hours (22:00–08:00) to not hammer Veracross overnight

### 6.2 What we pull

Same as v1: Student Overview, Classes & Reports, Assignments (per child), Per-class Grade Detail, Teacher Comments, Messages, Attendance. First Weekend 1 task is still: log in manually to your portal (`portals.veracross.eu/<vasantvalley_slug>` — you showed the `.eu` TLD in the Cowork digest), record actual URLs and selectors.

### 6.3 Performance

Scraper cost per sync, rough estimate:
- Auth check (cached cookies): 1 page load
- Per child: 4-5 page loads (overview, assignments, grades, comments, messages)
- Total per hourly sync: ~10-12 pages, 20-30 seconds

At 15 syncs/day, that's ~5 min of scraping per day. Completely fine.

### 6.4 Drift detection

Unchanged from v1. Each page has expected selectors. Zero matches on a non-empty page fires a `scraper_drift` event (notability 0.8, notifies you personally).

---

## 7. Syllabus layer

Unchanged from v1 §6. Two PDFs parsed once per academic year into JSON. Used for:

- Cycle context on each assignment (inline `ⓘ LC1` marker, hover for topic)
- Grade-trend interpretation ("this B- is in LC2 which is when the tougher Fractions word problems start")
- Digest prose ("LC1 wraps up Friday, 3 overdue items in LC1 scope")
- Correlating Veracross assignment titles with syllabus topics (fuzzy match + LLM fallback for ambiguous cases)

Syllabus calibration view lets you drag cycle boundaries or mark topics as covered early/late.

---

## 8. The 4pm digest — structure and content

Fires at 16:00 IST. Content delivered to Telegram + email + in-app, same source, three renders.

### 8.1 Structure (maps directly to the UI's Today view)

```
Parent Cockpit · 4pm digest · <day> <date>
Last sync: <time> <status>    <n> notifications fired today (<m> unseen)

<LLM prose preamble — 3-5 sentences, every sentence quantitative>

🚨 Overdue: <N>    📌 Due today: <N>    📅 Upcoming: <N>
[14-day overdue sparkline, one line per kid, in-app/email only]

📬 School messages (last 7 days)
• [NEW] <title>   <date>
• ...

────────────────────────────────────────
<Kid 1> · <Class>
────────────────────────────────────────
🚨 Overdue — <N> items   [<delta> since <day>]
   Subject  Assignment                          Due     Cycle
   ...

📌 Due Today — <N> items
   ...

📅 Upcoming — <N> items
   ...                                          ⚠ prep advised (if pattern)

Grade trend (last 7 days):
   <Subject> <sparkline>   <grades>   <trend>
   ...

────────────────────────────────────────
<Kid 2> · <Class>
────────────────────────────────────────
(same structure)
```

### 8.2 Channel-specific rendering

- **In-app / Email (HTML)**: full version including sparklines, syllabus-cycle markers, colored trend arrows
- **Telegram (Markdown)**: plain text, emoji headers, sparklines as `▂▃▅▆▇` Unicode blocks, no HTML

The rendering happens in `services/render.py` with three functions that take the same `DigestData` dataclass.

### 8.3 LLM prose preamble

This is where Claude is used. Prompt excerpt:

```
You write the 3-5 sentence preamble to a parent's 4pm school-tracking digest.
Every sentence carries at least one number. No cheerleading. No adjectives
like "great" or "concerning". Factual only.

You will receive:
- Total overdue count, and count 48h ago
- Per-kid overdue breakdown with subject concentrations
- New school admin messages (count only)
- Current learning cycle per kid

Write exactly 3-5 sentences. Example of acceptable output:

  "Backlog at 21, up from 10 Monday — accelerating. Samarth: 12 overdue,
  concentrated in Hindi (3) and Maths (3). Tejas: 9 overdue, 6 of them
  Maths — new pattern this week. Two school admin notices pending."

Example of unacceptable output:

  "It's been a busy week! The kids have a few things to catch up on,
  especially in Maths and Hindi. There are also some important school
  notices that deserve your attention."

Hard rules:
- Never invent data
- No praise, no softeners ("it seems", "perhaps")
- Maximum 5 sentences, minimum 3
- Every sentence must contain at least one number or specific subject name
```

---

## 9. UI specification

### 9.1 Site map

```
/                               Today view (= 4pm digest content, but always current)
/child/:id                      Child overview
/child/:id/assignments          Assignments, filterable
/child/:id/grades               Grades + trends
/child/:id/comments             Teacher comments timeline
/child/:id/syllabus             Syllabus browser for this kid
/messages                       School messages (shared across kids)
/notifications                  All events + which channels fired/suppressed
/notes                          Parent notes
/summaries                      Historical digests
/settings                       Credentials, sync schedule, channel config
/settings/channels              Per-channel thresholds and mute lists
/settings/syllabus              Calibrate cycle boundaries
```

### 9.2 Today view (= `/`)

Matches §8.1 exactly. This is both what shows in-app and what's rendered into the digest sent at 4pm. Same data, same structure — the URL is always the "live" version.

Interactions:
- Clicking an overdue item → opens a detail panel (assignment description, teacher, syllabus context, click-through to Veracross)
- Clicking the sparkline → `/child/:id/grades` for that kid
- Clicking a school message → marks it seen; opens detail
- `Sync now` button top-right
- Note input at bottom

### 9.3 `/notifications`

A chronological list of every event ever computed with:
- Kind + timestamp + notability score + child
- Status per channel: `✓ delivered 16:02` | `— suppressed: below threshold 0.6` | `— suppressed: mute_kinds` | `✗ failed: <error>`
- A "replay with current config" action (re-compute would-fire state)
- Filter by kind, channel, date range

This is the retuning view. You'll live here when calibrating thresholds in month 1.

### 9.4 `/settings/channels`

Per-channel form:

```
Telegram Bot
  [x] Enabled
  Threshold: [0.6 ▼]
  Mute kinds: [ ] new_assignment  [ ] grade_posted_routine  ...
  Rate limit: max [4] per hour
  Quiet hours: [22:00] – [07:00] IST
  Bot token: ••••••••  [edit]
  Chat ID: ••••••••  [edit]
  [Send test message]

Email
  [x] Enabled
  Threshold: [0.8 ▼]
  Mute kinds: [x] scraper_drift  ...
  Rate limit: max [6] per day
  To: varun@example.com, spouse@example.com
  SMTP host: ...
  [Send test message]

In-app
  [x] Enabled
  Threshold: [0.0 ▼]
  (always shows all events)

Digest (scheduled 4pm IST)
  Deliver via: [x] Telegram  [x] Email  [x] In-app
  Time: [16:00] IST
```

Saved as JSON in a `channel_config` table row (one row only, upsert).

### 9.5 Child detail pages

Unchanged from v1 §8.3. Overview / Assignments / Grades / Comments / Syllabus tabs.

---

## 10. Build sequence — four weekends, resequenced

### Weekend 1 — Scraper-first vertical slice
**Goal: see your kids' real Veracross data in a local web UI. No LLM, no notifications, no schedule — just fetch and render.**

- [ ] Repo bootstrap: FastAPI + SQLAlchemy + Alembic + Vite React + Tailwind + Docker Compose
- [ ] Schema migration 001: all 7 tables from §4
- [ ] Playwright scraper v1: auth, session caching, pulls assignments + grades + messages for both kids
- [ ] Normalization layer: raw Veracross → `veracross_items` rows
- [ ] `/api/sync` endpoint to trigger manual sync
- [ ] Minimal Today view: the table structure from §8.1, statically styled, no LLM prose, no sparklines, no delta counts
- [ ] Per-child detail pages: assignments table with filters, grades table

Deliverable: running `docker compose up` and visiting `localhost:3000` shows Tejas and Samarth's real Veracross data in a layout that matches the Cowork digest's structure. Manually hitting `/api/sync` pulls fresh data. This is the minimum viable replacement for Cowork.

**Budget:** this weekend is the hardest. Expect 10-14 hours total. The first 2 hours should be manual exploration of the Veracross portal with DevTools — do not write scraper code until you've seen every page you plan to scrape and have recorded selectors.

### Weekend 2 — Notability engine + multi-channel notifications
**Goal: the system notifies you on Telegram and/or email only when something's worth interrupting you.**

- [ ] Event producers: compute events from sync diff (§5.2 rubric)
- [ ] Notability scoring + dedup_key generation
- [ ] `channel_config` table + settings UI for per-channel config
- [ ] Telegram dispatcher: `httpx` post to bot API with markdown rendering
- [ ] Email dispatcher: plain SMTP with HTML render
- [ ] In-app notification pane at `/notifications`
- [ ] APScheduler: hourly sync job during 08:00–22:00 IST
- [ ] Test messages for each channel in settings
- [ ] Quiet hours enforcement
- [ ] Replay feature: "rerun last 7 days under current config"

Deliverable: by end of weekend, new Veracross assignments and grade changes trigger the right notifications. You adjust the thresholds once, leave it for a week, retune.

### Weekend 3 — Syllabus + trends + 4pm digest
**Goal: the system delivers the 4pm digest across all channels, with syllabus context and grade trend sparklines.**

- [ ] `scripts/parse_syllabus.py` using Claude to extract both PDFs into JSON
- [ ] Commit `data/syllabus/class_4_2026-27.json` and `class_6_2026-27.json`
- [ ] `services/syllabus.py`: cycle lookup by date, topic fuzzy-match for assignments
- [ ] Per-subject grade trend computation (7-day window, sparkline, direction arrow)
- [ ] 14-day overdue sparkline per kid
- [ ] Backlog delta: "+N since Mon" per kid
- [ ] Subject concentration detector (feeds `subject_concentration` event)
- [ ] Acceleration detector (feeds `backlog_accelerating` event)
- [ ] `services/render.py`: three renderers (Telegram / Email / Web) from a single `DigestData` dataclass
- [ ] 16:00 IST scheduled digest job across all configured channels

Deliverable: at 4pm, your phone buzzes with the Telegram digest. Email shows up in your inbox. `/` renders the same content. Content shape matches Cowork's digest + adds delta, sparklines, cycle markers.

### Weekend 4 — LLM prose + polish
**Goal: the briefing prose is good enough to actually read, not skip.**

- [ ] `llm/client.py`: Anthropic SDK wrapper with `llm_calls` logging and cost tracking
- [ ] `prompts/digest_preamble.md`: the quantitative 3-5 sentence generator
- [ ] `prompts/weekly_digest.md`: longer Sunday digest
- [ ] `prompts/explain_item.md`: on-demand "explain this grade / comment" in a drill-down
- [ ] Weekly digest (Sunday 20:00 IST) across all channels
- [ ] `/summaries` view with historical digests
- [ ] Parent notes CRUD at `/notes`
- [ ] Cycle-review stub (triggers on last day of a Learning Cycle, even if empty for now)
- [ ] Monthly LLM spend widget in settings
- [ ] Dogfood for a full week, iterate on prompts based on actual outputs

Deliverable: full product. You've been getting Telegram pings for 3 weeks at this point. The 4pm digest has been arriving for 2 weeks. Now the prose at the top stops being mechanical and becomes genuinely useful.

---

## 11. Operational details

### 11.1 Configuration and secrets

```
# .env
VERACROSS_HOST=portals.veracross.eu        # note .eu, not .com
VERACROSS_SCHOOL_SLUG=<TBD — check on first login>
VERACROSS_USERNAME=<your username>
VERACROSS_PASSWORD=<your password>

ANTHROPIC_API_KEY=sk-ant-...

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_IDS=<your chat id>,<spouse chat id>    # comma-separated

SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=cockpit@localhost
EMAIL_TO=you@example.com,spouse@example.com

APP_SECRET=<random 32 bytes for session signing>
TZ=Asia/Kolkata
```

### 11.2 Deployment

Starts on dev machine (`docker compose up`). When ready:
1. Home Linux box — same compose file, Tailscale for phone access
2. Nightly `sqlite3 app.db ".backup backups/daily.db"` → rsync to Synology
3. Optional: `litestream` for continuous replication

### 11.3 Telegram bot setup (20 minutes)
1. Open Telegram, message `@BotFather`, `/newbot`, pick name
2. Get bot token, paste into `.env`
3. Message your new bot once (any message), then hit `https://api.telegram.org/bot<TOKEN>/getUpdates` to get your chat ID
4. Test from settings UI

### 11.4 Monitoring

Light-touch, all in-app:
- Sync status banner (green/yellow/red) on every page
- Monthly LLM spend widget
- `sync_runs` history under `/settings`
- Drift warnings as a persistent banner until dismissed
- Notification failure rate — red banner if >20% fails in last 24h

### 11.5 Backup and recovery

- Daily atomic SQLite backup
- Weekly rsync to NAS
- Syllabus JSONs in Git
- Prompts in Git
- `.env` in your password manager

Restore: stop app, overwrite `app.db`, start app.

---

## 12. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Notification fatigue → you mute Telegram | High in first month | Replay feature; conservative default thresholds (0.6 Telegram, 0.8 email); weekly review of suppressed vs fired events |
| Veracross HTML change mid-term | High (1-2x/year) | Drift detection; scraper_drift event (notability 0.8); stale-data-ok UI |
| Hourly scraping flagged as unusual | Low | Matches normal parent behavior (portal is hit by lots of parents hourly); we're not hitting `/api/` endpoints, just authenticated parent pages |
| MFA added to Veracross | Medium | Re-auth flow with OTP input; degrade to email-only digest until fixed |
| LLM hallucinates facts | Medium | Prompt is strict "never invent"; structured data is primary, prose is preamble only; spot-check weekly |
| You stop reading Telegram pings | Medium | If Telegram becomes noise, reduce to email-only + in-app; system remains useful without notifications, just less timely |
| Spouse overwhelmed by notifications | Medium | Per-recipient channel config; spouse can get email-only, skip Telegram |
| 4pm digest misses something you needed at noon | Low | Hourly sync + notability engine handles this; digest is anchor, not sole |
| Scraper takes too long → sync backup | Low | Hourly window is plenty; if sync ever goes >5 min, investigate |
| Cost creep | Low | LLM is only in preamble + weekly; structured events don't use LLM; expect ₹100-300/month |

---

## 13. Decisions still needed before Weekend 1

1. **Your Vasant Valley Veracross URL slug.** Log in once, share the part after `portals.veracross.eu/`. Non-negotiable blocker for scraper.
2. **Telegram bot name** (purely cosmetic; `VVSCockpitBot` is fine)
3. **Linux box target for eventual deployment** (arch matters for Docker builds)
4. **Spouse channel preferences** (email only? Telegram too? separate thresholds?)
5. **Initial notability thresholds** — stick with defaults (0.6 Telegram / 0.8 email) or start more conservative (0.7 / 0.9)?

---

## 14. Repo layout

```
parent-cockpit/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                     (uv-managed)
├── alembic.ini
├── .env.example
├── README.md
├── data/
│   └── syllabus/
│       ├── class_4_2026-27.json
│       └── class_6_2026-27.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/
│   │   │   ├── children.py
│   │   │   ├── veracross_items.py
│   │   │   ├── events.py
│   │   │   ├── notifications.py
│   │   │   ├── notes.py
│   │   │   ├── summaries.py
│   │   │   └── llm_calls.py
│   │   ├── api/
│   │   │   ├── dashboard.py
│   │   │   ├── children.py
│   │   │   ├── notifications.py      (in-app notif pane + replay)
│   │   │   ├── notes.py
│   │   │   ├── settings.py
│   │   │   ├── sync.py
│   │   │   └── summaries.py
│   │   ├── services/
│   │   │   ├── syllabus.py
│   │   │   ├── render.py              (3 renderers from DigestData)
│   │   │   ├── briefing.py            (4pm + weekly digest generators)
│   │   │   └── trends.py              (sparkline data, deltas)
│   │   ├── notability/
│   │   │   ├── engine.py              (diff → events)
│   │   │   ├── rubric.py              (scores per event kind)
│   │   │   ├── dedup.py
│   │   │   └── dispatcher.py          (events → channels)
│   │   ├── channels/
│   │   │   ├── base.py                (Channel ABC)
│   │   │   ├── telegram.py
│   │   │   ├── email.py
│   │   │   └── inapp.py
│   │   ├── scraper/
│   │   │   ├── client.py              (Playwright session mgmt)
│   │   │   ├── pages.py
│   │   │   └── normalize.py
│   │   ├── llm/
│   │   │   ├── client.py
│   │   │   └── prompts/
│   │   │       ├── digest_preamble.md
│   │   │       ├── weekly_digest.md
│   │   │       └── explain_item.md
│   │   ├── jobs/
│   │   │   ├── scheduler.py
│   │   │   ├── sync_job.py            (hourly)
│   │   │   ├── digest_job.py          (16:00 daily)
│   │   │   └── weekly_digest_job.py   (Sunday 20:00)
│   │   └── schemas/
│   ├── migrations/
│   ├── scripts/
│   │   ├── parse_syllabus.py
│   │   └── replay_notifications.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/                       (TanStack Query hooks)
        ├── pages/
        │   ├── Today.tsx
        │   ├── ChildDetail.tsx
        │   ├── Assignments.tsx
        │   ├── Grades.tsx
        │   ├── Comments.tsx
        │   ├── Syllabus.tsx
        │   ├── Messages.tsx
        │   ├── Notifications.tsx      (the retuning view)
        │   ├── Notes.tsx
        │   ├── Summaries.tsx
        │   └── Settings.tsx
        ├── components/
        │   ├── OverdueTable.tsx
        │   ├── DueTodayTable.tsx
        │   ├── UpcomingTable.tsx
        │   ├── SchoolMessages.tsx
        │   ├── GradeTrend.tsx
        │   ├── OverdueSparkline.tsx
        │   └── ...
        └── styles/
```

---

## 15. What "done" looks like for v2

End of Weekend 4:

- [ ] The Telegram bot has been buzzing you for 3+ weeks with well-calibrated notifications
- [ ] The 4pm digest arrives daily on Telegram, email, and in the UI — same content, three renders
- [ ] At a glance, the digest tells you: total backlog, per-kid breakdown, subject concentrations, school admin, what's new — every sentence quantitative
- [ ] Grade trends per subject show up as sparklines, you can see "Tejas's Maths is trending down" without squinting
- [ ] Syllabus context is visible inline on every assignment
- [ ] Every notification that fired is visible in `/notifications` with channel delivery status; so is every notification that was suppressed, with the reason
- [ ] The replay feature lets you retune thresholds and see what would have been different
- [ ] Spouse can read the digest (email or Telegram) and understand it without your explanation
- [ ] Monthly LLM spend under ₹300
- [ ] Scraper has survived at least one minor HTML change on the Veracross side, you fixed a selector, data caught up

If all of that is true after 2 weeks of daily use, v2 is done. Sit with it for a quarter. Then, and only then, revisit the child-facing component.
