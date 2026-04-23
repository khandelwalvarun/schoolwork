# Parent Cockpit — React frontend

Minimal Vite + React + TanStack Query + Tailwind UI. Proxies `/api/*` to `http://localhost:8000` so you can run the backend and this dev server side by side.

## Prerequisites

- Node.js 20+ (`winget install OpenJS.NodeJS.LTS` or `choco install nodejs-lts`)
- The backend running: `uv run schoolwork-api`

## Dev

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

## Build

```bash
npm run build  # emits dist/
```

## Pages

- `/` — Today (overdue/due-today/upcoming per child, grade-trend sparklines, school messages)
- `/notifications` — every event + per-channel delivery status
- `/settings` — current `channel_config` JSON (read-only v1)

More pages (ChildDetail, Assignments, Grades, Syllabus, Messages, Summaries, Notes, Settings/Channels) to come.
