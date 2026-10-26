# Event Gamification

<!-- Rules and stack only. If the code can show it, it does not belong here. Keep it under 150 lines.
Updates happen at the gate: when a piece passes the CTO check, Claude proposes edits and the owner
approves in one line. After each model release run `/doctor prompt-audit` (Claude Code 2.1.283 or later) to catch stale rules. -->

## What this is
- Online gamification for events: guests play games and solve puzzles to earn coins, then exchange coins for prizes. Built for one client (TAG).
- Not yet decided: set in chat with ship-spec.
- Not yet decided: set in chat with ship-spec.

## Stack
- Backend: Python, FastAPI, Postgres (SQLAlchemy, Alembic) in `backend/`.
- Frontend: React + TypeScript on Vite, Tailwind with shadcn/Base UI, Recharts, lucide-react, in `frontend/`.
- The allowed packages are the stack list in `ship.json`. A new package or import stops the piece until the owner approves it in one line (then `ship_check.py stack-add`).

## Commands
- Backend: not yet (no code yet; fill in with the first piece).
- Frontend: not yet (no code yet; fill in with the first piece).
- Tests: not yet. Run them before calling a piece done.

## How we build
- Pieces are specced in chat into the project's Notion tracker. `/ship:next` picks up the next Ready one and saves its contract to `contracts/`. Build what it lists and nothing more.
- Before a piece reaches dev, run `/ship:cto-check`. A failed check stops the piece: fix the check first, no exceptions.
- If the check finds something extra: if the client asked for it, the owner approves a contract change in one line; if not, delete it. Claude never edits a contract on its own.
- After pickup the repo holds the contract and the tracker shows a copy only Claude Code writes. The client's verdict closes a piece: `/ship:done` or `/ship:drop`.
- Delete features nobody uses. Git keeps them.
- Any change of direction is flagged in one line: "CHANGE: …".

## Rules the code can't show
- Secrets live in environment files, never in code or git.
- Never put demo data in code; even demo data comes from the API.
- Production changes only through the pipeline, never by hand on the server. Claude never works on a production server in auto mode.
- <Add a rule here only when Claude has broken it twice, or a new teammate would need it on day one.>
