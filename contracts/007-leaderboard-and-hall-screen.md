# Contract: Leaderboard and hall screen
Status: building
Base: b7c9a3761c
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be608180b660f45ab5121d38

Client's words (TAG): «Общий рейтинг (топ-N + позиция самого игрока, даже если он не в топе — «Ты на 214-м месте»).», from backlog, added 2026-11-01

Client's words (TAG): «В последние 30 минут этапа 4 — отдельный режим «эфир»: полноэкранный топ-10 с автообновлением, предназначен для трансляции на большом экране в зале (см. 3.9).», from backlog, added 2026-11-01

Client's words (TAG): «Отдельный URL/режим приложения без авторизации, только для чтения — топ-10 лидерборда, обновление раз в 10–15 секунд, брендирование форума и партнёров, для вывода через HDMI/проектор на экран в зале.», from backlog, added 2026-11-01

Client's words (TAG): «Главные призы (по рейтингу баллов, вручаются на закрытии): 1 место — Главный приз — ноутбук; 2 место — ноутбук / эквивалент; 3 место — ноутбук / эквивалент», from rules 8.1, added 2026-11-01

Owner's addition: staff, volunteers and moderators stay out of the ranking («В рейтинге: нет» in the guest list), from backlog, added 2026-11-01

Owner's addition: freeze the ranking before the ceremony, with a printable top 10 for the host, from backlog, added 2026-11-01

## What users see

- From the feed, a guest opens /app/rating: the top 20 by points, each with first name, last initial and points.
- Below the top 20, the guest sees their own row: «Вы на N-м месте · X баллов». Inside the top 20, their row is highlighted instead.
- Ties go to whoever reached the score first.
- /hall needs no login and is read-only: the top 10 in large type with the forum name, for a projector over HDMI. It refreshes every 10 seconds without a reload and keeps the last view if the network drops. It is on all day; TAG decides when to show it.
- The guest list file takes a new column «В рейтинге». Guests marked «нет» play and earn as normal but never appear in the ranking, the hall screen or the top-20 moderation filter. Download gives the column back.
- /admin/tasks shows a «Зафиксировать рейтинг» button. Once pressed, /app/rating and /hall show the frozen places with «Итоги зафиксированы», whatever changes after. The admin sees a printable top 10 with full name, company and points for the host. «Снять фиксацию» undoes it.

## What's out

- Company and friends filters
- The «Поделиться» story card
- Levels and badges beside names (piece 9)
- Partner logos on the hall screen (forum name only)
- A separate «эфир» mode that switches on by itself in the last 30 minutes
- Prize names or places beyond the top 10 on the printable list

## How to check it

- When three guests have 120, 90 and 90 points and the second reached 90 first, then /app/rating shows them in that order.
- When I am in 34th place, then I see the top 20 and «Вы на 34-м месте» with my points.
- When I open /hall on a laptop with no login, then I see the top 10, and when a guest earns points, the screen updates within 10–15 seconds without a reload.
- When I turn off the laptop's network for a minute, then /hall keeps showing the last top 10 and recovers on its own.
- When the guest list marks a volunteer «В рейтинге: нет» and they earn the most points, then they appear nowhere in the ranking, and they can still play and buy in the market.
- When I press «Зафиксировать рейтинг» and a moderator then rejects a top-3 guest's photo, then /hall and /app/rating still show the frozen places.
- When I press «Снять фиксацию», then both screens show live places again.
- When I freeze the ranking, then I can print a top 10 with full names, companies and points.
- When I press the freeze button without the admin password, then nothing happens and I see only the login prompt.

## Size

Screens: 2

- /app/rating
- /hall

Endpoints: 3

- GET /api/rating
- GET /api/hall
- POST /api/admin/rating/freeze

Tables: 0
