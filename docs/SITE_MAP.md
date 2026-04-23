# Veracross Parent Portal — Site Map

Living document. Every URL pattern, what it carries, and how the scraper accesses it. Updated whenever we discover a new surface. Last refreshed **2026-04-23**.

> **Scope:** `portals.veracross.eu/vasantvalleyschool/parent` + its two companion subdomains (`portals-embed.veracross.eu`, `documents.veracross.eu`) + the Google-Drive PDFs that school-wide pages link to.

Legend
- 🟢 **JSON component** — direct JSON endpoint on the main portal, fast + cheap.
- 🟡 **Server-rendered HTML** — parse with BeautifulSoup, moderate cost.
- 🟠 **Embed iframe** — loaded from `portals-embed.veracross.eu`, contains the actual data.
- 🔴 **Documents subdomain** — `documents.veracross.eu`, PDFs + per-period grade reports.
- 🔵 **External (Drive etc.)** — third-party links embedded on school-content pages.

---

## 1. Authentication

- **Login page**: `https://portals.veracross.eu/vasantvalleyschool/parent` (form with username + password).
  - The submit button has `data-disable-with="loading..."` — Playwright's `.click()` times out waiting for it to become "enabled"; pressing **Enter** in the password field works reliably.
- **CSRF token**: `<meta name="csrf-token" content="…">` on every authenticated page. Required for `X-CSRF-Token` header on XHR POSTs.
- **Session**: single cookie jar, shared across `portals.veracross.eu`, `portals-embed.veracross.eu`, `documents.veracross.eu` in practice.
- **Session lifetime**: ~1.5 hours of idle-ish activity observed. Re-login is cheap and handled in `scraper/client.py:_ensure_authenticated`.

---

## 2. Main portal (`portals.veracross.eu/vasantvalleyschool/parent`)

### 2.1 JSON component endpoints 🟢

Pattern: `/component/<ComponentName>/<component_id>/load_data[?params]`.
Called with `X-Requested-With: XMLHttpRequest` + `X-CSRF-Token`.

| Component | Purpose | Notes |
|---|---|---|
| `MyChildrenParent/1274/load_data` | Child roster: `person_pk`, `first_name`, `last_name`, `student_photo_url`, `where_is_student_now`, `reports` (list of academic documents + URLs). | **Authoritative** source for children. Seeded via `backend/scripts/seed_children.py`. |
| `MyEventsParent/1273/load_data?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Upcoming family events for the next ~5 days. | ISO date params. |
| `ArticleBannerCarousel/<id>/load_data` | Homepage banner articles. | Multiple component IDs (5530, 5731…). |
| `ArticleMasonryCardList/<id>/load_data` | Masonry article grid. | Multiple IDs. |
| `ArticleVerticalCardList/2778/load_data` | Vertical news list. | Typically the "News" block. |

### 2.2 Navigation HTML pages 🟡

| Path | Data | Used by |
|---|---|---|
| `/` (portal root) | Shell + widgets; iframe into planner links. | CSRF extraction. |
| `/profile` | Parent account. | Not scraped. |
| `/messages` | **School message list** — each `.vx-list__item.message` has `.message-from`, `.message-subject`, `.message-category`, `.message-date-sent`, and an `a.message-link → /detail/email/{id}`. | `scraper/parsers.parse_messages_list`. |
| `/messages/categories/<id>` | Filtered message list. | Not scraped (redundant with /messages). |
| `/detail/email/<int>` | One school message's full body. `.vx-record-title`, `.vx-data-field` for From/Sent/To. | `parse_email_detail`. |
| `/detail/assignment/<int>` | One assignment's detail. `.detail-assignment` → `.vx-record-header__course-description`, `.vx-record-title`, `.vx-data-field × {Date Assigned, Due Date, Max Score, Weight, Notes}`. | `parse_assignment_detail`. |
| `/detail/event/<GUID>` | One event's detail. | Not scraped yet. |
| `/detail/master_attendance/<int>` | Attendance detail. | Not scraped yet (TODO). |
| `/detail/article/<base64>` | School article body. | Not scraped (low signal). |
| `/calendar/household` + `/calendar/school` | Calendar views; data comes from JSON endpoints below. | Not needed directly. |
| `/calendar/household/events?begin_date=MM/DD/YYYY&end_date=MM/DD/YYYY` | **Family event JSON** (note MM/DD/YYYY, URL-encoded). | Can substitute for the component `MyEventsParent` for wider windows. |
| `/calendar/school/events?begin_date=MM/DD/YYYY&end_date=MM/DD/YYYY` | School-wide event JSON. | Same as above for school scope. |
| `/directory/faculty-staff` | Staff directory. | Not scraped. |
| `/pages/<Slug>` | **School-content pages.** Static-ish HTML with embedded links (Drive PDFs, Google Forms, Sheets, external websites). Known slugs: `Syllabus-2026-27`, `Dec-Exam-Syllabus-2025`, `book-list-2026`, `reading-lists-2025`, `School%20Committees`, `Monthly-Quiz-Jr-School`, `Monthly-Quiz-Sr-School`, `News-Letter`, `Library%20Magazine`, `Career_College`, `Event-Archives`, `Vasant-Valley-Insights`, `Assessment-Schedule-2026-27`. | Syllabus & book-list pages carry the per-class Drive links we need (see §6). |
| `/student/<vc_id>/overview` | Per-student shell; contains iframe → planner. | Student ID comes from `MyChildrenParent`. |
| `/student/<vc_id>/daily-schedule` | Daily schedule shell; iframe into embed daily schedule (not scraped yet). | — |
| `/student/<vc_id>/recent-updates` | Recent-updates shell; iframe. | — |
| `/student/<vc_id>/upcoming-assignments` | Upcoming shell; iframe. | — |
| `/student/<vc_id>/academic-report-history` | Report-card history shell; links to PDFs on `documents.veracross.eu`. | Not scraped yet (TODO). |
| `/student/<vc_id>/classes/<cid>/assignments` | Per-class assignments shell. | Class ID extracted here for grade-report URLs. |
| `/student/<vc_id>/classes/<cid>/grade_detail` | Per-class grade shell; iframe → embed grade_detail (see §3.2). | Not used directly. |

### 2.3 iCal subscriptions

| Path | Data |
|---|---|
| `/calendar/subscribe/school` | School-calendar iCal redirect. Not scraped. |
| `/calendar/subscribe/mine` | Personal iCal redirect. Not scraped. |

---

## 3. Embed subdomain (`portals-embed.veracross.eu/vasantvalleyschool/parent`) 🟠

Real per-student data lives here.

### 3.1 Planner

`/planner?p=<vc_id>&school_year=<year>` — the **single most important URL** per kid.

- **Classes list**: `.timeline-row[data-row-id]` → first cell has `.title` (subject), `.subtitle` (teacher), and `a[href*=\"/classes/<cid>\"]` (class_id).
- **Assignments**: `.assignment[data-assignment-id]` → `.assignment-type`, `.assignment-description`, `.badge` (status: DUE / OVERDUE / SUBMITTED / GRADED).
- **Date mapping**: top `.timeline-row.header` has date strings in each `.timeline-cell`; column index → date.
- **Summary/due row**: top section repeats urgent assignments without row-id — Pass 2 in parser picks those up, status only.

Parsed by `scraper/parsers.parse_planner`.

### 3.2 Per-class grade shell

`/children/<vc_id>/classes/<cid>/grade_detail`

- HTML scaffold with class selector + `<a href=\"https://documents.veracross.eu/.../grade_detail/<cid>?grading_period=<N>\">` per learning cycle.
- We currently hard-code period IDs (`13=LC1, 15=LC2, 19=LC3, 21=LC4`) in `config.Settings.grading_period_ids`. TODO: parse dynamically from this shell page the first time we encounter a class.

---

## 4. Documents subdomain (`documents.veracross.eu/vasantvalleyschool`) 🔴

### 4.1 Per-period grade report

`/grade_detail/<class_id>?grading_period=<N>&key=_`

- Rich HTML: `table.data_table` (summary by assignment type) + `table.data_table.grades` (per-assignment rows with Due Date, Assignment, Score, Grade%, Points Earned/Possible).
- Parsed by `scraper/parsers.parse_grade_report`.

### 4.2 Academic documents (report cards)

`/academic_document/<id>` — returns a **PDF** report card.

- Discovered via `MyChildrenParent` JSON (`children[].reports['Report Card'][].report_url`).
- Authenticated via same session cookie.
- Not yet downloaded by the scraper; see TODO §7.

---

## 5. External (Drive, Sheets, Forms, other school URLs) 🔵

Found inside `/pages/*` HTML. Not authenticated via our portal session.

| Source | What |
|---|---|
| Google Drive file links `drive.google.com/file/d/<id>/view` | Syllabi, book lists, reading lists, exam schedules. |
| Google Sheets | Activity rosters, committee lists. |
| Google Forms | Consent forms, sign-ups. |
| `sciencemag.vasantvalley.org` | School publication. |
| `chawlabookdepot.com` | Book vendor. |

Drive files are reachable via `https://drive.google.com/uc?id=<id>&export=download` for most shared-link files. For larger files Drive sometimes shows a virus-scan confirmation page that requires a follow-up GET; our downloader handles this.

---

## 6. Syllabus PDF index (auto-extracted from `/pages/Syllabus-2026-27`)

Discovered 2026-04-23. Kept in `backend/app/syllabus_links.py` in code so it can be refreshed programmatically.

| Class | Drive file ID | Note |
|---|---|---|
| Foundation | `1gbw4bQyzUofa8G9YBD-DFk7L5tYcBNyu` | |
| Nursery | `1lIvOnjmpVrE3shCE7xUs32LFzZ_DLhmY` | |
| Class 1 | `1xRAoosTBKQEnmZ8CFVwD-crfKV2ebrjK` | |
| Class 2 | `1fllIbiQsEeN240N7mGgdOMulqamS16dY` | |
| Class 3 | `1LwkYk5bFEtHk19QsZwFSsWeVF8vM9w9j` | |
| **Class 4** | **`12ZbNa2c-r2_BSKknABHhCJDFqrC8tQNt`** | **Samarth** |
| Class 5 | `1PcSast7uOGbOdPbU1PtWK1pIHHGWkMr8` | |
| **Class 6** | **`1OeDNkUvJ528brGGSW1gowDwe40yua4ZN`** | **Tejas** |
| Class 7 | `18yItDyLgt_DN7XG2V98XmmjJ3kkDYDS3` | |
| Class 8 | `1eNgOWcalcBe9UunMKkQjj0TJiEsMS8sP` | |
| Class 8 IGCSE | `1otEGlPNt1ElB3bEVO0byMBR-O9KiYChR` | |
| Class 9 | `1YHaIWJ1VJx8mjoR714Y0Zy96gO1fJ3yx` | |
| Class 9 IGCSE | `1147PDDAkeHx-NtwumDeB6-q02apVy4kf` | |
| Class 10 | `1kQCuAJICZAfeJ_wfaspKqEnOlgPYdleG` | |
| Class 10 IGCSE | `1UjkY7aQGLTaClkiCbt36vxC93pnzvEVd` | |
| Class 11 | `1BXXaFo3pS2MBJ6f5hTiEnvexxjvpUlwJ/` | |
| Class 11 A Level | `1E1tNmKCs2TXmUIDK3pOlOi9iRlIPMZYn` | |
| Class 12 | `1n2KAC-blhJ3zZNMB09TETp_xYJ7WSznP` | |
| Class 12 AS Level | `1hKobMTeqqkSYYpL_KwxU3NWvOSDbet_0` | |

Book-list PDFs (a separate page, `/pages/book-list-2026`): Class 6 `1MWQkt32vhZ-OlzpL7_oJ0LHKjTDN0yh0`, Class 7 `1UbW4bmYNfttE6A8zX2tPyhrklETpxZmN`, etc. Class 4's book list is on another page TBD.

---

## 7. Open discoveries / TODO

- [ ] Parse `portals-embed.veracross.eu/.../children/<sid>/classes/<cid>/grade_detail` once per class to learn the actual grading_period IDs (instead of hard-coding).
- [ ] Scrape `/detail/master_attendance/<int>` and `/student/<sid>/academic-report-history`.
- [ ] Archive report-card PDFs from `documents.veracross.eu/.../academic_document/<id>`.
- [ ] Scrape per-class "class website" links (inside planner first cell) — potential homework descriptions.
- [ ] Subscribe iCal feeds at `/calendar/subscribe/*` for offline calendar syncing.

## 8. Refresh policy

Re-run `scripts/recon.py` quarterly (or after any Veracross UI change) to catch new patterns. Manifest + network captures live under `recon/output/` (git-ignored). Site-map update goes in §§2–6 of this doc.
