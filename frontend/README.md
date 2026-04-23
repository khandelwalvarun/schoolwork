# Parent Cockpit — React frontend

Minimal Vite + React + TanStack Query + Tailwind UI. Proxies `/api/*` to `http://localhost:7777` so you can run the backend and this dev server side by side.

## Prerequisites

- Node.js 20+ (`winget install OpenJS.NodeJS.LTS` or `choco install nodejs-lts`)
- The backend running: `uv run schoolwork-api`

## Dev

```bash
cd frontend
npm install
npm run dev    # http://localhost:7778
```

## Build

```bash
npm run build  # emits dist/
```

## Pages

- `/` — Today (overdue / due-today / upcoming per child, 14-day backlog sparkline, grade-trend sparklines, current cycle badge, syllabus context inline, school messages)
- `/child/:id` — per-kid summary
- `/child/:id/grades` — full grade list + LLM annotations
- `/child/:id/assignments` — filterable assignment table with submitted-override toggle
- `/child/:id/comments` — teacher comments
- `/child/:id/syllabus` — syllabus browser with topic-status markers
- `/messages` — school messages
- `/notes` — parent notes (create + list)
- `/summaries` — past digests
- `/notifications` — events + per-channel delivery + counterfactual replay
- `/settings/channels` — per-channel threshold / mute / rate-limit / quiet-hours editor + test-send
- `/settings/syllabus` — cycle-boundary calibration + topic status
