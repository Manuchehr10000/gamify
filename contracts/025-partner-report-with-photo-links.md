# Contract: Partner report with photo links
Status: on-dev
Base: a38bb0e8ad
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081fda9add91977790015

CHANGE to: 010
Owner's words (TAG): «Экспорт отчёта по каждому партнёру… Получает после форума отчёт по своим заданиям: количество выполнений, уникальные участники, ссылки на пользовательский контент с тегом бренда.», from chat spec agreed 2026-11-02 by Manu

## What users see

- On /admin/live, beside «Скачать отчёт по партнёрам» (the CSV stays), an admin picks a partner and downloads one Excel file (.xlsx) for them, in Russian.
- Sheet «Сводка» (first sheet): totals in plain numbers:
  - per task: completions, unique guests, and rejected in a separate column
  - the partner's prizes: bought and given out at stands (004)
  - logo time on the hall screen: times shown and total seconds, beside the partner's package (piece 18)
  - forum-wide push reach: opt-ins and deliveries (piece 19)
- Sheet «Детали»: one row per task per stage per hour, with completions, unique guests and rejected.
- Sheet «Фото»: a link to each accepted photo (accepted or accepted with a bonus) of that partner's tasks, with the task and the time sent. No guest names.
- The first sheet says: «Ссылки на фото работают до [дата удаления]».
- Before the ranking is frozen (007), the first sheet is marked «Предварительные данные».
- Opening a photo link in any browser shows the photo, with no login; after the deletion date it shows nothing.

## Rules

- Only accepted and undecided submissions count as results; rejected ones (sent back for a retake or rejected with a penalty) are counted separately, as in 010.
- Completions and unique guests use the same count as /admin/live (010), so the totals match.
- Photo links are unguessable (a random token per submission, not its ID) and stop working on the deletion date, checked on every open. The date is the photo deletion date key this piece registers in piece 13's settings store; when it is not set, one shared helper gives the default: the local date (UTC+5) of the last stage's end + 30 days. Piece 22 reuses the same key and helper. This piece does its own check and does not wait for piece 22's deletion job.
- Counts follow the partner link at the moment the file is made: tasks and prizes are taken by their current partner (piece 12).
- Text cells that start with = + - @ are written as text, never as formulas (as 010's CSV).
- Only admins can download a report; the photo link is the only part open without a login.

## Settings (piece 13)

- photo deletion date: date or blank (blank = last stage's end, local date UTC+5, + 30 days via the shared helper), from now on

## What's out

- Guest names or contacts (leads), in the file or behind a photo link
- A login for partners
- Bulk photo download (zip or similar)
- Undecided or rejected photos in «Фото» or behind a photo link (until Manu decides otherwise; see Decisions)
- Photos of other partners' tasks or of non-partner tasks
- Emailing or sending the file to partners; the admin downloads and forwards it by hand
- Charts in the file
- Push reach per partner (only forum-wide numbers exist, piece 19)
- Deleting photos, the deletion job, the 7-day banner and locking the date once the banner shows (piece 22)
- Recording logo show times on /hall (piece 18) and counting push opt-ins/deliveries (piece 19); this piece only reads them
- History of which partner a task belonged to before a move; the file follows today's link only
- Changes to the existing CSV export

## How to check it

- When I download a partner's file, then it opens in Excel with Cyrillic intact and three sheets.
- When a moderator rejects one of their photos, then it leaves «Фото» and moves to the rejected column.
- When I move a task to another partner and remake both files, then the task's numbers move with it.
- When I open a photo link, then the photo shows; after the deletion date, it doesn't.
- When I compare the totals with /admin/live, then they match.
- (added) When I make a file before the ranking is frozen, then its first sheet says «Предварительные данные»; after freezing, it doesn't.
- (added) When I open the first sheet, then it says «Ссылки на фото работают до» with the deletion date.
- (added) When I look at «Сводка», then I see the partner's prizes bought and given out, logo shows and seconds beside the package, and the forum's push opt-ins and deliveries.
- (added) When I search the file for a guest's name, then nothing is found.
- (added) When a photo is still waiting for a moderator, then it is not in «Фото» and has no working link.
- (added) When I call the report endpoint without the admin password, then the server refuses it.

## Size

Screens: 0

Endpoints: 2

- GET /api/admin/partners/{partner_id}/report
- GET /api/photos/{token}

Tables: 0

## Decisions

- Open item: which photos «Фото» lists (the spec says "each accepted photo", but its rejection check implies a listed photo can later be rejected, and decisions are final in 006) → Needs Manu: should undecided photos be listed and linked publicly for partners? Assumed accepted and bonus only meanwhile, because unmoderated guest photos must not reach partners through a no-login link. The rejection check holds either way: a rejected photo is never listed and counts in the rejected column.
- Open item: what "rejected" covers → Decision: submissions with status retake or penalty, each sent-back retake counted once, matching 010's exclusion.
- Open item: how links are made unguessable → Decision: a random token column added to submissions (backfilled for existing photos), so no new table and no new secret to manage. The endpoint returns the photo only if the token matches, the submission is accepted or bonus, and today is before the deletion date.
- Open item: where the deletion date comes from → Decision: this piece registers the photo deletion date key in piece 13's settings store, with one shared helper giving the default when it is not set: the local date (UTC+5) of the last stage's end + 30 days. Photo links and the first sheet use it. Piece 22 (built after this piece) reuses the key and helper and only adds the lock once the 7-day banner shows, the banner and the deletion job.
- Open item: the partner picker's list → Decision: the picker uses GET /api/admin/lists/partners from piece 13; this piece adds no partner list endpoint.
- Open item: "per task per stage per hour" → Decision: a task belongs to one stage, so each row is a task and an hour of completion in forum local time (stages.EVENT_TZ), with the stage named on each row; hours with nothing are left out.
- Open item: «Предварительные данные» trigger → Decision: shown while rating.frozen() is false (007's freeze).
- Open item: package for Excel → Decision: openpyxl, already approved and in ship.json's stack; no other package needed.
- Open item: logo time and push reach before pieces 18/19 record anything → Decision: cells show 0; this piece adds no logging of its own.
- Open item: photo link base address → Decision: built from PUBLIC_BASE_URL, served at /api/photos/{token} with no-store caching on a router without the admin dependency, so the Worker in deploy/ needs no change.
