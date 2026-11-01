# Contract: Live counts for TAG
Status: on-dev
Base: cc125cb485
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be6081518ec1f5622e9540d4

Client's words (TAG): «Живой дашборд: активные игроки сейчас, выполнения по типам заданий, топ по спонсорам, здоровье очереди модерации (сколько заданий ждёт проверки и сколько это ждёт по времени).», from backlog, added 2026-11-01

Client's words (TAG): «Экспорт отчёта по каждому партнёру (см. 2, роль «Партнёр»). — Получает после форума отчёт по своим заданиям: количество выполнений, уникальные участники, ссылки на пользовательский контент с тегом бренда.», from backlog, added 2026-11-01

## What users see

- /admin/live, behind the admin password, refreshes every 30 seconds without a reload and shows:
  - guests logged in, and guests active in the last 15 minutes (earned points, sent a submission or bought something)
  - completions by task type, and by stage
  - completions and unique guests per partner, partners sorted by completions
  - moderation: how many wait, and the age of the oldest
  - market: prizes bought, given out at stands, and left
- «Скачать отчёт по партнёрам» gives a CSV (UTF-8, opens in Excel with Cyrillic intact): one row per partner task with partner, package, task, completions, unique guests. Rejected submissions don't count.

## What's out

- Charts (numbers and tables only)
- Links to guests' photos in the report
- A login for partners themselves
- History over time; anything beyond the current numbers

## How to check it

- When 3 guests log in and 2 do a task, then /admin/live shows 3 logged in and 2 active within 30 seconds.
- When a guest completes a partner task, then that partner's completions go up by 1 within 30 seconds.
- When 4 photos wait for moderation and the oldest was sent 6 minutes ago, then I see 4 waiting and about 6 minutes.
- When I download the partner report and open it in Excel, then names show in Cyrillic and each partner task has its completions and unique guests.
- When a moderator rejects a partner photo, then the report and the page no longer count it.
- When I open /admin/live or the report without the password, then I see only the login prompt.

## Size

Screens: 1

- /admin/live

Endpoints: 2

- GET /api/admin/live
- GET /api/admin/partners/export

Tables: 0
