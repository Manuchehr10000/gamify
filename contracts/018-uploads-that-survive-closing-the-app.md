# Contract: Uploads that survive closing the app
Status: building
Base: d9b0eea3b8
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081bb8b1cd7373e4289ef

CHANGE to: 005, 006
Owner's words (TAG): «Проектировать в расчёте на нестабильный Wi-Fi/перегруженную LTE-соту: локальное кэширование ленты, отложенная отправка фото/видео с индикатором «отправляется», без потери прогресса при обрыве связи.», from chat spec agreed 2026-11-02 by Manu

## What users see

- A photo or text submission is saved on the phone the moment the guest presses «Отправить». Closing the app no longer loses it; sending resumes when the app reopens.
- On Android, where the browser allows it, sending also finishes after the app is closed. On iPhone it resumes on the next open.
- The guest's card shows where it stands:
  - «Ждёт сети — ещё не засчитано»: not yet reached the server
  - «Загружается»
  - «Ждёт сети»: place held, photo waiting
  - then the states from piece 15 (until piece 15 ships, 005's «Выполнено»)
  - «Лимит исчерпан», «Этап закрыт» or «Время вышло» if it can't count
- Up to 5 submissions can wait on one phone; beyond that, «Дождитесь загрузки предыдущих фото».
- The moderation list (006) shows thumbnails; the full photo opens on tap.

## Rules

- The phone redraws the photo (1600 px, JPEG, as 005), which strips location and camera data, and makes a 400 px thumbnail.
- Sending is two steps. First a small claim with a submission ID made on the phone; the server checks stage, stock and whether the guest already did it, and records the server time. Then the files.
- The claim's server time sets the stage, stock and multiplier.
- If the files don't arrive within the claim time limit (default 60 minutes), the claim lapses and frees its place.
- The same submission ID never pays twice (as 005).
- The phone retries on open, when the network returns and when the app comes back to the screen: after 5 s, 15 s, 30 s, 60 s, then every 5 minutes.
- The phone's copy is deleted once the server confirms.
- The server accepts JPEG only, checked by content: photo up to 1 MB, thumbnail up to 100 KB.

## Settings (piece 13)

- claim time limit: 10–240 min, default 60, from now on
- queue size per phone: 1–10, default 5, from now on

## What's out

- Video
- True background upload on iPhone (the browser doesn't allow it)
- The task limit N, its place counting and the locked check that returns «Лимит исчерпан» (piece 15); this piece only stores claims so piece 15 can count open ones, and shows «Лимит исчерпан» when the server answers with it
- «На проверке», «Выполнено» after a decision, «Временно недоступно» and rotation (piece 15)
- Stage multipliers themselves (piece 16); this piece only records the claim's server time and stage for them to read
- Push notifications (piece 19); its push handler goes into the same service worker later
- Deleting photos after 30 days (piece 22)
- The job runner and the scheduled trigger (piece 12); this piece registers its lapse job in it
- Changing anything in the four moderation buttons or decision rules (006 stays)
- Uploading several photos per task, editing a submission after «Отправить», or cancelling a queued one

## How to check it

On a real iPhone and a cheap Android:

- When I send a photo and close the app mid-upload, then on reopening it finishes and I'm paid once.
- When I send in airplane mode, then the card shows «Ждёт сети — ещё не засчитано»; when the network returns, it counts at that later server time.
- When the claim is in but the photo doesn't arrive within 60 minutes, then the claim lapses, I get nothing, and a files upload for that claim afterwards is refused with no payment.
- When a claim passes 60 minutes, then the next job run marks it lapsed and the run log shows it.
- When I send a photo with GPS data, then the stored photo has none.
- When the same upload arrives twice, then I'm paid once.
- When the network is slowed to weak 3G, then the upload still finishes and the card shows each state in turn.
- (added) When I send a photo on Android and close the app, then it finishes without reopening it, where the browser supports background sync.
- (added) When 5 submissions are already waiting on my phone and I press «Отправить» on a 6th, then I see «Дождитесь загрузки предыдущих фото» and nothing is saved.
- (added) When my claim reaches the server after the stage has ended, then my card shows «Этап закрыт» and I get nothing.
- (added) When a moderator opens /moderate, then each photo shows as a thumbnail and the full photo opens on tap.

## Size

Screens: 0
No new route: the card states live in /app and /app/tasks/:id; no new route.

Endpoints: 2

- POST /api/tasks/{id}/claim
- POST /api/claims/{id}/files

Tables: 1

- claims

## Decisions

- Open item: Build one service worker shared with piece 19 → Decision: extend the existing frontend/public/sw.js with a sync handler (Background Sync API, no package) that reads the queue from IndexedDB; piece 19 adds its push handler to the same file. The guest token is mirrored into IndexedDB because a service worker can't read localStorage.
- Open item: Check Neon storage (see piece 22) → Needs Manu: confirm the Neon plan's storage limit against expected guests × photo tasks × ~0.4 MB average (1 MB cap) plus up to 100 KB per thumbnail, assumed photos stay in Postgres (as 005) meanwhile, with piece 22's 30-day deletion as the cap.
- Open item: where claims live → Decision: a new claims table (phone's submission ID as key, guest, task, text, server time, stage, expires_at, state open/done/lapsed) rather than half-empty rows in submissions, so 006's queue and unique index stay untouched and piece 15 can count open claims directly; the claim ID is written to the existing submissions.upload column.
- Open item: when points and coins are paid → Decision: when the files arrive (a text-only submission: when the claim arrives), not at the claim, so a lapsed claim pays nothing (check 3) and 005's pay-on-arrival and 006's reversal stay as they are.
- Open item: files that arrive after the stage ended → Decision: they still count for the claim's stage, because the claim's server time sets the stage.
- Open item: text-only and photo+text submissions → Decision: the text rides in the claim; text-only counts at once with no files step; photo+text sends its photo and thumbnail in the files step.
- Open item: idempotency across the two steps → Decision: a repeated claim or a repeated files upload with the same submission ID returns the first result, as 005's upload key does today.
- Open item: how lapse is enforced → Decision: a lapse job registered in piece 12's runner marks claims past expires_at as lapsed; expires_at is still checked whenever a claim is read, so a claim between job runs is already treated as lapsed.
- Open item: the old one-step endpoints POST /api/tasks/{id}/photo and POST /api/tasks/{id}/text → Decision: remove them once the app uses the claim flow (delete what nobody uses); git keeps them.
- Open item: the card state before piece 15 → Decision: after the server confirms, the card shows 005's «Выполнено» until piece 15 adds its states.
- Open item: thumbnail storage and serving → Decision: a thumb column on submissions (not a new table), served by the existing GET /api/submissions/{id}/photo with ?thumb=1, so no new endpoint.
- Open item: «stock» in the claim check before piece 15 exists → Decision: claims are recorded with no stock check until piece 15 adds the limit N and the locked place check; the phone already maps the server's limit answer to «Лимит исчерпан».
- Open item: guaranteeing "the stored photo has no GPS" → Decision: besides the phone's redraw, the server drops APP1–APP15 metadata segments with the existing stdlib JPEG marker walker in backend/app/photos.py before storing, so an old cached app version can't store GPS; no image library needed.
- Open item: stack → Decision: no new package; IndexedDB and Background Sync are browser APIs, JPEG checks use backend/app/photos.py.
