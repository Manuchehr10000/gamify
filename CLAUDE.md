# Event Gamification

<!-- Rules and stack only. If the code can show it, it does not belong here. Keep it under 150 lines.
Updates happen at the gate: when a piece passes the CTO check, Claude proposes edits and the owner
approves in one line. After each model release run `/doctor prompt-audit` (Claude Code 2.1.283 or later) to catch stale rules. -->

Ship's rules come from the mg-ship-kit plugin at session start, not from this file. This file holds only what's true of this project.

## What this is
- Online gamification for events: guests play games and solve puzzles to earn coins, then exchange coins for prizes. Built for one client (TAG).
- Not yet decided: set in chat with ship-spec.
- Not yet decided: set in chat with ship-spec.

## Stack
- Backend: Python, FastAPI, Postgres (SQLAlchemy, Alembic) in `backend/`.
- Frontend: React + TypeScript on Vite, Tailwind with shadcn/Base UI, Recharts, lucide-react, in `frontend/`.

## Commands
- Backend (in `backend/`): `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`; copy `.env.example` to `.env`; `.venv/bin/alembic upgrade head`; `.venv/bin/uvicorn app.main:app --reload --port 8000`.
- Frontend (in `frontend/`): `npm install`; `npm run dev` (port 5173, passes `/api` to :8000); `npm run build`; `npm run lint`.
- Tests: `cd backend && .venv/bin/pytest` (needs a local Postgres database `gamify_test`). Run them before calling a piece done.

## Rules the code can't show
- The Worker (deploy/src/index.ts) resends a request the container dropped only for GET/HEAD and the sends in SAFE_SENDS. A new POST goes on that list when repeating it after a success answers with the first result or an "already" answer that reads as done.
- <Add a rule here only when Claude has broken it twice, or a new teammate would need it on day one.>
