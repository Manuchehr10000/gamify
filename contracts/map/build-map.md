# Build map: gamify

Map of: dev at 16d0e9f23080, 2026-11-08
Counts: 24 tables · 61 endpoints · 18 screens
Counted from: FastAPI routes and Alembic or SQL migrations in backend/, React Router routes in frontend/, by the size check's own code (D15). Code it can't read isn't on this map.
Claude Code rebuilds this file at every /mg-ship-kit:done. Never edit it by hand, here or in Notion.

## Tables

- badge_awards: id (key), guest_id → guests, badge, created_at, seen, announce, shown_at
- badges: id (key), partner_id → partners, task_id → tasks, code, name, rule, count, kinds, +6 more
- change_events: id (key), created_at, staff_name, kind, item_id, item, field, old_value, +2 more
- claims: id, guest_id, task_id, text, multiplier
- feed_rotations: guest_id (key) → guests, stage_id (key) → stages, after_task_id → tasks, last_task_id → tasks
- guests: id (key), code, reg_id, first_name, last_name, phone, company, consented_at, +7 more
- hall_state: id (key), mode, staff_name, changed_at
- job_runs: id (key), job, started_at, finished_at, result, error, detail
- levels: id (key), name, min_points
- logo_shows: id (key), partner_id → partners, started_at, seconds, created_at
- partners: id (key), name, package, active, logo
- prizes: id (key), partner_id → partners, code, name, price, quantity, position, active
- push_messages: id (key), task_id → tasks, kind, source, source_at, shift_seconds, at, title, +12 more
- push_subscriptions: id (key), guest_id → guests, key, endpoint, p256dh, auth, active, created_at
- questions: id (key), task_id → tasks, number, text, option1, option2, option3, option4, +1 more
- quiz_attempts: id (key), guest_id → guests, task_id → tasks, stage_id → stages, started_at, finished_at, answers, correct, +3 more
- redemptions: id (key), guest_id → guests, prize_id → prizes, code, issued_at, created_at
- score_events: id (key), guest_id → guests, stage_id → stages, reverses_id → score_events, reason, points, created_at, coins, +3 more
- sessions: id (key), guest_id → guests, staff_id → staff, token_hash, role, created_at, staff_name
- settings: key (key), value, min_value, max_value, version, text_value
- staff: id (key), name, role, secret_hash, created_at, active
- stages: id (key), number, name, starts_at, ends_at, message, market, active, +2 more
- submissions: id (key), guest_id → guests, task_id → tasks, photo, text, created_at, status, moderator, +4 more
- tasks: id (key), stage_id → stages, requires_task_id → tasks, partner_id → partners, code, type, text, points, +15 more

## Endpoints

- backend/app/routers/admin.py: GET /api/admin/guests/export, POST /api/admin/guests/import, POST /api/admin/guests/import/preview
- backend/app/routers/admin_settings.py: DELETE /api/admin/lists/{kind}/{row_id}, GET /api/admin/lists/{kind}, GET /api/admin/log, GET /api/admin/log/export, GET /api/admin/settings, POST /api/admin/lists/{kind}, POST /api/admin/partners/{partner_id}/logo, PUT /api/admin/lists/{kind}/{row_id}, PUT /api/admin/settings/{key}
- backend/app/routers/admin_tasks.py: GET /api/admin/stages, GET /api/admin/tasks/export, GET /api/admin/tasks/qr, POST /api/admin/stages/advance, POST /api/admin/tasks/import, POST /api/admin/tasks/import/preview
- backend/app/routers/badge.py: GET /api/me, GET /b/{code}, POST /api/consent
- backend/app/routers/claims.py: DELETE /api/submissions/{submission_id}/photo, POST /api/claims/{claim_id}/files, POST /api/tasks/{task_id}/claim
- backend/app/routers/desk.py: GET /api/desk/guests/, POST /api/desk/guests/
- backend/app/routers/feed.py: GET /api/feed, GET /api/tasks/{task_id}, POST /api/feed/next, POST /api/scan, POST /api/tasks/{task_id}/complete
- backend/app/routers/jobs.py: POST /api/jobs/run
- backend/app/routers/live.py: GET /api/admin/balance-check, GET /api/admin/live, GET /api/admin/partners/export, GET /api/admin/partners/{partner_id}/report, GET /api/admin/photo-deletion
- backend/app/routers/market.py: GET /api/market/, POST /api/market/{prize_id}/buy
- backend/app/routers/moderation.py: GET /api/moderation/queue, GET /api/submissions/{submission_id}/photo, POST /api/moderator/login, POST /api/submissions/{submission_id}/decision
- backend/app/routers/profile.py: GET /api/profile
- backend/app/routers/public.py: GET /api/partners/{partner_id}/logo, GET /api/photos/{token}, GET /api/version
- backend/app/routers/push.py: POST /api/admin/push/{push_id}/send, POST /api/push/subscribe, POST /api/push/{push_id}/received
- backend/app/routers/quiz.py: POST /api/quiz/{task_id}/answer, POST /api/quiz/{task_id}/finish, POST /api/quiz/{task_id}/start
- backend/app/routers/rating.py: GET /api/hall, GET /api/rating, POST /api/admin/rating/freeze, POST /api/hall/logo-shows, POST /api/hall/mode
- backend/app/routers/staff.py: POST /api/staff/login
- backend/app/routers/stand.py: GET /api/stand/{code}, POST /api/stand/{code}/issue

## Screens

- frontend/src/App.tsx: *, /admin/guests, /admin/live, /admin/settings, /admin/tasks, /admin/tasks/qr, /app, /app/profile, /app/quiz/:id, /app/rating, /app/tasks/:id, /app/welcome, /desk, /hall, /market, /moderate, /q/:code, /stand/:code

## Decisions and gaps

Written by Claude, not counted: the only part of this map that can be wrong.

- Every change to points or coins goes through `app/ledger.py`: score_events is append-only, the guest's stored totals move in the same transaction, and a retake adds a reversal row (reverses_id) instead of deleting the award.
- A task counts as done when the guest has a standing award for its reason (`task:{id}`, no reversal pointing at it); feed, badges, moderation, quiz and reports all key on these reason strings.
- Photos and their 400 px thumbnails are stored as bytes in Postgres (submissions.photo / thumb), not in object storage; the phone redraws them to 1600 px and the server only strips metadata (no image library).
- Staff accounts live hashed in the staff table, seeded once from DESK_PIN, ADMIN_PASSWORD, STAND_PIN and MODERATORS when the table is empty; after that those env values are ignored, and a PIN or password alone identifies the account.
- Background work runs from a Cloudflare cron every minute calling POST /api/jobs/run with JOBS_SECRET; `app/jobs.py` runs each job in turn under a Postgres advisory lock and logs it in job_runs. The cron also keeps the container awake all day.
- Each environment runs one basic container instance (max_instances 1 in deploy/wrangler.jsonc), so the backend assumes a single instance.
- Event times use a fixed UTC+5 zone (`stages.EVENT_TZ`), not a setting.
- Gap: the frontend has no tests; only the backend has a pytest suite.
- Gap: backend/.env.example holds a real-looking VAPID_PRIVATE_KEY value instead of a placeholder (flagged by the setup history scan).
