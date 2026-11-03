# Contract: Feed card states and rotation
Status: building
Base: ba5a538d29
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081ccbc5cd34ee3fcbae5

CHANGE to: 002, 005, 006
Owner's words (TAG): «Карточка задания содержит: …статус (доступно / на проверке / выполнено / временно недоступно)… Одновременно в ленте не более 10–20 карточек на этапе (конфигурируется в админке) — ротация из полного каталога, с приоритетом заданий с истекающим временным окном (периодические квизы).», from chat spec agreed 2026-11-02 by Manu

## What users see

- Every task card on /app and /app/tasks/{id} shows one of four states:
  - «Доступно»: can be done.
  - «На проверке»: a photo or text submission the moderator hasn't decided yet. Points and coins are already paid (as 006). Replaces 005's instant «Выполнено» for these tasks.
  - «Выполнено»: done; for photo and text tasks, after «Принять» or «Бонус», or when the stage ends with no decision.
  - «Временно недоступно»: the task has reached its limit of N completions.
- A guest who tries to take a full task (claim, QR scan, link, quiz start) gets «Лимит исчерпан». The card becomes available again when places free up or an admin raises N.
- Each stage shows a batch of B cards (default 15) instead of the whole stage list:
  - Tasks with a time window that is open come first.
  - The rest follow 002's order, and each refresh or reopen shows the next ones, wrapping at the end. The place in the list is kept on the server per guest and stage, so it continues after closing and reopening the app.
  - Tasks the guest has done leave their rotation. Their undecided («На проверке») cards for the current stage are pinned above the batch and don't count toward B.
  - Cards with no places left stay in rotation with their label, since they can come back.
- Moderators see no change: each submission is decided once, with 006's four buttons. When a stage ends, the guest's undecided cards show «Выполнено», but they stay in the moderator queue, so the «Топ-20» check still works.

## Rules

- Each task may have a limit N; blank means none.
- Places used = open claims (piece 14) + submissions not rejected with a penalty. For tasks with no submission (QR, link, market, quiz), a place is a guest who did the task; a quiz takes its place when the guest starts it.
- «Отклонить — переснять» keeps the guest's place in the task's limit, so that guest can send again even when the task is full; «Отклонить со штрафом» frees it.
- Claims (and QR, link and quiz-start awards) check and take a place in one locked step, so two guests can't take the last one.
- The batch advances only on a page load of /app (opening the app or a browser reload, including pull-to-refresh). The 1-minute poll, coming back to the screen, and returning from /app/tasks/{id} show the same batch; a card done in between drops out and the batch fills from the next ones.
- Open time-window tasks sit at the top of every batch and count toward B; the rotating part fills the rest (B minus open windows). If open windows alone reach B, only they show.
- The server keeps, per guest and stage, the last task shown; the next batch starts after it in the current order, so tasks done, added or switched off don't skip or repeat others.

## Settings (piece 13)

- limit N per task: from now on
- batch size B per stage: 5–50, default 15, from now on

## What's out

- The claim endpoint, the phone-side queue and its upload states (piece 14); this piece only adds the place check to piece 14's claim
- The settings form machinery, confirmations and change log (piece 13); this piece adds two fields to it and no admin endpoint of its own. It is built only after pieces 13 and 14 are done
- A per-player limit (TAG's «лимит на игрока» in 002): N here is total completions across all guests
- A «Ещё задания» button or tabs by type; the batch advances only on reopen or reload
- Showing past stages' cards in the feed (the feed stays current-stage only, as 002)
- Changing moderation decisions, appeals, or new moderator buttons (stays 006)
- Stage multipliers (piece 16), blitz (piece 17), push (piece 19)
- Video

## How to check it

- When I send a photo, then my card shows «На проверке» with the points already in my total.
- When the moderator presses «Принять», then my card shows «Выполнено».
- When the stage ends with my photo undecided, then my card shows «Выполнено» and the photo is still in the moderator queue.
- When 50 guests claim a task with N = 10 at once, then exactly 10 succeed and the card shows «Временно недоступно» to the rest.
- When a moderator rejects one of those 10 with a penalty, then the task becomes available again; after «переснять», it stays full and that guest can send again.
- When a stage has 40 tasks and B = 15, then three refreshes show 1–15, 16–30, then 31–40 and 1–5; an open quiz window always shows first.
- When I close and reopen the app between refreshes, then the rotation continues where it stopped.
- When a full task is a QR task and I scan its code, then I see «Лимит исчерпан» and get nothing. (added)
- When I have a photo «На проверке» in the current stage, then it is pinned above the batch and the batch still has B cards. (added)
- When the feed polls or I come back from a task's page, then the batch doesn't change. (added)
- When I set B to 4 or 51, then the form refuses it and names the range 5–50. (added)
- When I finish a QR task in my batch and reload, then it is gone from the rotation and the batch still has B cards. (added)
- When an admin raises N on a full task, then its card shows «Доступно» again and a new claim succeeds. (added)
- When an open claim on a full task (N reached) lapses after 60 minutes, then the card shows «Доступно» again and a new claim succeeds. (added)

## Size

Screens: 0

Endpoints: 1

- POST /api/feed/next

Tables: 1

- feed_rotations

## Decisions

- Open item: what counts as a "refresh" when the feed already polls every minute and on return to the screen → Decision: only a page load of /app (open or reload, incl. pull-to-refresh) advances, via POST /api/feed/next called once on load; polls, visibility and returning from a task keep the batch, so cards don't move under the guest's thumb.
- Open item: new endpoint or a flag on GET /api/feed → Decision: a separate POST /api/feed/next, because advancing changes server state and GET must stay safe to poll and cache; GET /api/feed keeps returning the current batch.
- Open item: do open time-window tasks count inside B → Decision: yes, they sit on top and count toward B, so the batch is never larger than the admin set; the 1–15 / 16–30 / 31–40+1–5 numbers in the 40-task check hold with no window open, and with one open it shows first and the rotating part is B minus open windows.
- Open item: what a "place" is for tasks with no submission (QR, link, market, quiz) → Decision: the guest's completion is the place, taken in the same locked step as the award, since the spec's state is a "limit of N completions"; a quiz takes it at start so nobody is cut off mid-timer.
- Open item: how the retake card shows its held place → Decision: it shows «Доступно» with 006's «Фото не подошло — отправьте ещё раз», is pinned above the batch with the undecided ones, and its claim passes even at N.
- Open item: label for a penalty-rejected card (task closed, place freed) → Decision: it shows 006's warning in place of a state label and leaves the rotation like a done task; no fifth state.
- Open item: where a past stage's undecided card shows «Выполнено», since the feed shows only the current stage → Decision: on /app/tasks/{id} and in the phone's cached feed; the state is worked out from the task's stage, not stored.
- Open item: where N and B are edited → Decision: in piece 13's task and stage forms, plus a «Лимит» column in «Задания» and a «Карточек в ленте» column in «Этапы», since piece 13 keeps Excel for bulk setup in the same format.
- Open item: storage → Decision: N as a nullable column on tasks, B as a column on stages (default 15), the per-guest cursor in a new feed_rotations table (guest, stage, last task shown).
- Open item: order with piece 14, whose claim "checks stock" → Decision: pieces 13 and 14 ship first (neither is built yet); this piece adds the limit check and the row lock inside 14's claim, so 14 needs no limit of its own.
