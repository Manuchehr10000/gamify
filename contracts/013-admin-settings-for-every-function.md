# Contract: Admin settings for every function
Status: building
Base: 6aca578c62
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081d5ad39ed108f20c3e9

CHANGE to: 001–011 (every Excel sheet and hard-coded value)
Owner's words (TAG): «CRUD по заданиям (тип, текст, баллы, монеты, тег партнёра, этап, лимит на игрока, гео/QR-привязка).» / «CRUD по призам «Партнёрского маркета» (название, партнёр, цена в монетах, остаток).» / «…пороги и список бейджей задаются в админке…, не хардкодятся в коде.», from chat spec agreed 2026-11-02 by Manu

## What users see

- Admins open /admin/settings and edit everything in forms, with no redeploy: stages, tasks, prizes, quiz questions, levels, partners and their logos, staff access (named admin and moderator accounts; the desk PIN and stand PIN), and the game settings the inventory turns into settings.
  - Badges (piece 20), the push schedule and texts (piece 19), and every other setting from pieces 14–22 join the same forms, log and Excel rules when their piece is built. Each of those pieces lists its own under «Settings (piece 13)».
- Lists can add, edit and switch off rows. A row other data uses can't be deleted, only switched off. Examples: a task guests have done, a prize someone bought, a stage with tasks, a partner with tasks or prizes, a quiz with attempts.
- Every field has limits; a value outside them is refused, naming the field and the range.
- Saved changes reach phones and screens within 10 seconds.
- Each setting has one effect rule, shown in the form beside the field:
  - from now on: past results stay
  - recheck past: past activity is checked again (badges)
  - locked while running: refused with the reason, e.g. «Нельзя менять во время блица»
- Changes that hit the live game (end a stage, switch off a running task, change a multiplier mid-stage) ask for confirmation and say what will change before anything is saved.
- If two admins save the same item, the second sees «Изменено другим администратором — обновите страницу» and nothing of theirs is saved.
- Change log («Журнал» tab of /admin/settings, stored in the change_events table):
  - Every change records admin, time, item, field, old value, new value, and source (form or Excel).
  - The log can't be edited or deleted. Admins filter it by item, admin and date, and export it.
- Excel:
  - The existing sheets stay for bulk setup: guest list, «Этапы», «Задания», «Призы», «Вопросы», «Уровни», plus «Бейджи» (piece 20).
  - An upload with any invalid row is refused whole, naming each bad row in Russian. Today a bad row is skipped and the rest apply; that ends.
  - A valid upload first shows a preview: added, changed, and rows that would be hidden because the file no longer has them. Nothing applies until the admin confirms.
  - Export writes the current state in the same format, ready to upload back.

## Rules

- Requires piece 12 (partners table, staff accounts with hashed PINs/passwords, named admins) to be done first. This piece adds no tables for those.
- First step, before building: list every value in 001–011 that is hard-coded, set by environment, or set only in Excel, with a proposed effect rule for each. Bring the list back to the spec chat. The build starts from the list Manu confirms (a draft is in Decisions).
- Every admin endpoint checks the admin role on the server (piece 12's staff access).

## What's out

- An undo button (the log shows the old value)
- Scheduling a setting change for later (only pushes have a schedule, piece 19)
- Different settings per hall screen; several events at once
- The badge list form and the «Бейджи» sheet (piece 20), the push schedule and texts form (piece 19), and each setting from pieces 14–22: those pieces add them, reusing this piece's lists, settings, log and Excel rules where they fit, and count their own size
- Editing guests one by one in a form (the guest list stays CSV upload/export)
- Technical limits staying in code: photo size limits, text length, poll intervals, the event time zone, advisory lock ids
- «Проверить баланс», the partners table, the staff accounts table and staff roles (piece 12); logo display on /hall (piece 18)
- SVG logos

## How to check it

- When I change a task's points in the form, then phones show the new value within 10 seconds, and the log shows the old and new value under my name.
- When I enter a value outside its limits, then the form refuses it and names the field and the range.
- When the blitz is open and I edit its questions, then I see «Нельзя менять во время блица».
- When I upload a file with one bad row in a hundred, then the whole file is refused and that row is named.
- When I upload a file missing a task I added in a form, then the preview lists that task as «будет скрыто» and nothing changes until I confirm.
- When I export and upload the same file, then the preview shows no changes.
- When two tabs save the same task, then the second is refused.
- When I try to delete a task guests have done, then I can only switch it off.
- (added) When I switch off a task that is open in the current stage, then I am asked to confirm and told what will change, and nothing changes if I cancel.
- (added) When I upload a partner logo in the form, then its thumbnail shows in the partners list.
- (added) When I filter the log by one admin and export it, then the file holds only that admin's changes.
- (added) When I switch off a moderator account, then that moderator's next action is refused.

## Size

Screens: 1

- /admin/settings

Endpoints: 13

- GET /api/admin/lists/{kind}
- POST /api/admin/lists/{kind}
- PUT /api/admin/lists/{kind}/{id}
- DELETE /api/admin/lists/{kind}/{id}
- GET /api/admin/settings
- PUT /api/admin/settings/{key}
- POST /api/admin/partners/{id}/logo
- GET /api/partners/{id}/logo
- GET /api/admin/log
- GET /api/admin/log/export
- POST /api/admin/tasks/import/preview
- POST /api/admin/guests/import/preview
- GET /api/version

Tables: 2

- settings
- change_events

## Decisions

- Open item: the inventory of hard-coded, environment and Excel-only values (spec's first step) → Decision: draft for the chat:
  - become settings, «from now on»: login points (+10, badge.py ARRIVAL_POINTS); partner coin multiplier (×1.5, task_file.rule_coins); moderator bonus (+50%, moderation.py); ranking size (20, rating.py TOP); moderation queue's top-guest priority (20, moderation.py TOP); hall top (10, rating.py HALL_TOP); «active guest» window (15 min, live.py ACTIVE_WINDOW).
  - become form lists: stages, tasks, prizes, questions, levels, partners, admin/moderator accounts, desk and stand PINs (env moves to DB in piece 12).
  - stay in code: photo limits, text max 500 (feed.py), poll intervals, time zone UTC+5 (stages.py), feed package order.
  - go to piece 20: badge thresholds 5/5/3.
  - piece 12's open question: score_events already carries coins (market.py buy, moderation.py bonus).
→ Needs Manu: confirm the inventory in the spec chat before build; this draft is assumed meanwhile.
- Open item: how to cover «every setting from pieces 12–22» before 14–22 exist → Decision: build a generic list/setting registry behind {kind} and {key} endpoints, which later pieces can register their kinds and keys into.
- Open item: one screen or many → Decision: one route /admin/settings with tabs (one per list, «Настройки», «Журнал»); the Excel preview lives in the existing /admin/tasks and /admin/guests pages.
- Open item: concurrent edits → Decision: a version column on every edited table and on each setting row (columns only). A save sends the version it read; a stale version is refused with «Изменено другим администратором — обновите страницу».
- Open item: where settings live → Decision: one settings table (key, value, limits, effect rule); later pieces add keys there instead of new tables or environment values.
- Open item: 10-second propagation → Decision: each save bumps one config version (a row in settings), served by a cheap GET /api/version. Feed, task, market and hall poll it every 10 s and reload when it moves. The fallback, cutting the feed poll from 30 s to 10 s, would triple feed load.
- Open item: what «the blitz is open» means before piece 17 → Decision: a quiz's questions are locked while its «Доступно с/до» window is open, or while any attempt is still within its timer (abandoned attempts never set finished_at, so «unfinished» would lock forever). Locked edits show «Нельзя менять во время блица». Piece 17 reuses the same lock.
- Open item: effect rule for levels → Decision: recheck past (a guest's level already follows current points, as in 009); level-up moments already shown are not replayed.
- Open item: effect rule for task points/coins, prize price, partner package → Decision: from now on. Awards and purchases already made keep their values. Prize quantity can't go below what is already bought.
- Open item: confirmation before live changes → Decision: the same PUT/DELETE (and the existing POST /api/admin/stages/advance) returns the impact («увидят N гостей», «этап закончится сейчас») until resent with confirm, so no extra endpoint.
- Open item: what «every change» covers in the log → Decision: list and setting edits, switch-offs, Excel applies, and the existing stage advance and ranking freeze actions, all written to change_events.
- Open item: applying an Excel upload after preview → Decision: the preview endpoints validate and diff only. Confirm resends the file to the existing POST /api/admin/tasks/import or /api/admin/guests/import, which now applies whole or not at all.
- Open item: guest list under «refused whole» and preview → Decision: the CSV guest upload is refused whole on any bad row and previews added/changed. → Needs Manu: confirm guests missing from a re-uploaded list are never hidden (they may already have points), assumed never hidden meanwhile.
- Open item: staff access in forms → Decision: admins add, rename, reset the PIN/password of, and switch off admin and moderator accounts, and reset the shared desk and stand PINs (stored hashed, piece 12). The last active admin can't be switched off. Switching off deletes that account's rows in sessions, which ends its sessions.
- Open item: where logos are stored → Decision: in Postgres as bytes on the piece-12 partner row (as photos are today), served by GET /api/partners/{id}/logo for the form thumbnail and piece 18. PNG/JPEG only, up to 1 MB, sent with nosniff; SVG refused, since it can carry script.
- Open item: log export format → Decision: .xlsx via openpyxl (already in stack); form validation with react-hook-form and zod (in stack); no new package.
