# Contract: Push notifications
Status: on-dev
Base: c81472f106
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be608187b366c8f21438b09e

CHANGE to: none (the spec has no CHANGE line)
Owner's words (TAG): «При смене этапа — push-уведомление всем активным пользователям с фирменным текстом (см. правила, разделы 4.1–4.4)…», from chat spec agreed 2026-11-02 by Manu
Owner's words (TAG): «Каждые ~90 минут приложение рассылает push с коротким квизом на 5 минут (окно закрывается — задание исчезает из ленты).», from chat spec agreed 2026-11-02 by Manu

## What users see

- After a guest's first earned points, the app asks once: «Узнайте первым о квизе и открытии маркета», then the browser's own prompt.
  - "First earned points" means the first task points; the +10 for arriving does not count.
  - "Once" means once per phone: after «Не сейчас» or a browser "Block", the app does not ask again.
- On iPhone, when the app isn't opened from the Home Screen, a short card shows how to add it, in place of the prompt. It can be closed and found again in the profile (/app/profile).
  - In iPhone Safari the card shows when the app opens; the prompt never shows there. Opened from the Home Screen, the app asks after first points like any other phone.
  - The app gets a web app manifest (standalone, name, icons, no fixed start address) and an Apple touch icon, so "Add to Home Screen" opens it as an app that can receive pushes, already signed in as that guest.
- Pushes arrive for: stage start (TAG's text per stage), 5 minutes before a periodic quiz opens, when it opens, and when the market opens.
  - Stage start uses the stage's own banner line (002's «Этапы» message).
  - Tapping a quiz push opens that quiz's task page; any other push opens /app.
- The same text shows as the in-app banner (002's) for anyone with the app open, and on the hall screen (piece 18).
  - One banner, not two: at a stage start the push text and 002's stage banner are the same banner.
  - On /hall the text shows in piece 18's interrupt, through the push field piece 18 adds to GET /api/hall; this piece fills it.
- Admin, on a «Push» tab of /admin/settings (piece 13): the schedule of every push (time, kind, text, state: planned, sent, cancelled, expired) with its counts, a push on/off switch, the Russian text per kind of push, and buttons to move, cancel, edit the text of or send any push now, plus a form to write a one-off message.
- Admin, on /admin/live: opt-ins, sends, deliveries and failures.

## Rules

- Quiz pushes come from quiz windows («Доступно с/до» in 008); the market push from the stage marked «Маркет».
  - Planned pushes are kept in step with their source: when a stage time, a quiz window or the «Маркет» stage changes (form, Excel or «Начать следующий этап сейчас»), its pushes move with it. An admin's move is kept as a shift from the source time and survives the source changing. A switched-off quiz drops its pushes.
- Admins can move, cancel or send any push now, and write a one-off message.
- The stage-start push title is piece 16's banner title (feed.newStage, with «— очки ×N» when the multiplier isn't 1) and its body is the stage's «Этапы» line; the per-kind text settings cover only quiz-before, quiz-open, market and one-off.
- The job runner (piece 12) sends what's due each minute. Each push expires after 10 minutes.
  - The push service is told the 10-minute life (TTL 600), and the job marks as expired, unsent, anything more than 10 minutes past due.
- Keys VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT live in the GitHub dev environment and pass to Cloudflare on deploy.
  - The backend reads them from the environment; .env.example lists them empty. The public key reaches the app inside the existing /api/me answer.
- Subscriptions the push service reports gone are switched off.
- Count opt-ins, sends, deliveries and failures, shown in /admin/live and passed to piece 21.
  - Opt-ins: active subscriptions. Sends: accepted by the push service. Failures: refused or gone. Deliveries: the phone's service worker reports the push arrived.
  - The arrival report (POST /api/push/{id}/received) takes no login, because a service worker can't read the app's stored login. It carries the push id and the subscription id from the push payload, and counts at most once per subscription per push.
- The push handlers go in the app's one service worker (frontend/public/sw.js, shared with piece 14); no second worker.
- Sending uses pywebpush (approved in the spec), several at a time, so one minute's pushes to every guest finish inside that minute.
- This piece builds after pieces 12, 13, 14 and 18 (tracker order). The schedule is registered as a list kind push in 13's generic lists (GET/POST/PUT /api/admin/lists/push); the switch and texts are keys in 13's settings store, written through PUT /api/admin/settings/{key}.

## Settings (piece 13)

- schedule items; texts per event in Russian (Tajik column ready, empty); push on or off: from now on

## What's out

- Personal pushes (rejections, badges)
- Tajik push texts: the column exists and stays empty; guests get Russian
- Pushes in iPhone Safari without adding to the Home Screen (the browser doesn't allow it); the guide card is the answer
- Asking again after a guest says no; a «turn notifications off» switch in the app (the phone's own settings do that)
- Pushes to staff (moderators, desk, stands, admins)
- Pushes for blitz, stage end, or anything not listed above
- The hall screen's slide frame and 15-second full-screen interrupt, and the push field in GET /api/hall (piece 18 builds them; this piece fills the field with the text)
- The partner report itself (piece 21 reads the counts)
- The settings forms framework, generic lists and change log (piece 13); this piece adds its push list kind and settings keys into them
- The job runner itself (piece 12); this piece registers one job
- Per-phone delivery history (counts are per push, not per device)
- A new login method for the Home Screen app (the guide carries the existing login; see Decisions)

## How to check it

- When a guest earns their first points, then the app asks for permission; not before.
- When I open the app in iPhone Safari, then I see the Home Screen guide, not the prompt.
- When a quiz window opens at 14:00, then pushes arrive at about 13:55 and 14:00 on an Android phone with the app closed.
- When an admin moves the quiz by 15 minutes, then both pushes move with it.
- When a phone is off for 15 minutes across a push, then the push doesn't arrive late.
- When a push is sent, then the banner shows in open apps and on /hall.
- When stage 2 starts at ×2, then phones get «Этап 2 — очки ×2» with stage 2's line from the «Этапы» sheet. (added)
- When the first stage marked «Маркет» starts, then a market push arrives. (added)
- When I add the app to the iPhone Home Screen, open it from there and earn my first points, then I am still signed in, I get the prompt and pushes arrive. (added)
- When I close the iPhone guide card, then I can open it again from /app/profile. (added)
- When an admin cancels a planned push, then it never arrives; when he presses send now, then it arrives within a minute. (added)
- When an admin edits a planned push's text, then the push arrives with the new text. (added)
- When an admin writes a one-off message for 15:30, then it arrives at about 15:30. (added)
- When an admin switches pushes off, then nothing is sent until he switches them on again, and the banner still shows in open apps. (added)
- When a guest's browser has dropped its subscription, then the next send marks it off and later sends skip it. (added)
- When pushes have gone out, then /admin/live shows opt-ins, sends, deliveries and failures. (added)
- When a push is sent while /hall is in «Авто», then its text fills the hall screen for 15 seconds. (added)

## Size

Screens: 0

Endpoints: 3

- POST /api/push/subscribe
- POST /api/push/{id}/received
- POST /api/admin/push/{id}/send

Tables: 2

- push_subscriptions
- push_messages

## Decisions

- Open item: Confirm the backend is Python, for pywebpush. → Decision: confirmed, the backend is Python 3.12 FastAPI. ship_check reads only the package names in requirements*.txt and matches imports by top-level module, so adding just pywebpush to requirements.txt (its own dependencies requests, py-vapid and http-ece come with it, unlisted) passes after ship_check.py stack-add pywebpush. → Needs Manu: confirm pywebpush (recorded as approved in the spec) so stack-add runs at pickup, assumed approved meanwhile. In-stack fallback if ever needed: a VAPID token with pyjwt (ES256) + cryptography, the aes128gcm payload with cryptography, and the POST with httpx (moved from requirements-dev to requirements). About a day's extra work, so not recommended.
- Open item: Share the service worker with piece 14. → Decision: add push, notificationclick and the arrival report to the existing frontend/public/sw.js (002's offline cache, which piece 14 extends); whichever of 14/19 lands second builds on the other's version of the same file. The worker registers in production builds only, so push is checked on dev, not on npm run dev.
- Decision (no open item): "first earned points" = first task points (a task: score event), not the +10 arrival, else the prompt would fire at login and break "not before".
- Decision (no open item): on iPhone the guide shows when the app opens in Safari (not standalone), per the agreed check "When I open the app in iPhone Safari, then I see the Home Screen guide". On every other phone, and inside the Home Screen app, the prompt waits for first points.
- Decision (no open item): the Home Screen app has its own storage, separate from Safari, so the guest's stored login would be missing. While the guide shows, the address carries the login in the same #token fragment the badge redirect already uses, and the manifest sets no fixed start address, so the Home Screen link opens signed in; the existing /app/welcome reads it. No new endpoint. → Needs Manu: if testing on a real iPhone shows the Home Screen app still opens signed out, a re-login path inside the app is needed (a contract change). Assumed the fragment works meanwhile.
- Decision (no open item): a web app manifest and a PNG Apple touch icon are added in frontend/public (not counted as screens), made from the app's current favicon; without them iPhone pushes can't work. → Needs Manu: TAG's own icon for the Home Screen, assumed the current favicon meanwhile.
- Decision (no open item): open apps get the push text from a push field (the latest push still inside its 10-minute life) that this piece adds to the existing GET /api/feed answer. /hall gets it from the push field piece 18 owns in GET /api/hall (null until this piece fills it); this piece only fills it. No new endpoint, and it works for guests who never opted in.
- Decision (no open item): "deliveries" are counted from the service worker's arrival report (POST /api/push/{id}/received, no login, once per subscription), because the push service only confirms acceptance. Counts are stored on each push row, so there is no per-device table.
- Decision (no open item): one table push_messages holds the schedule (source key such as stage, quiz-before, quiz-open, market or one-off; time; admin shift; text in Russian; Tajik column; state; counts). It is regenerated from its sources on each change and each job run, leaving admin shifts, text edits and cancellations alone.
- Decision (no open item): at the start of the first «Маркет» stage both the stage push and the market push are sent, the stage push first, since the spec lists both.
- Decision (no open item): the admin controls are a «Push» tab of 13's /admin/settings, not a page of their own. push_messages is registered as list kind push in 13's generic lists, so the schedule is read, a one-off message added, and a push moved, cancelled or its text edited through GET/POST/PUT /api/admin/lists/push. Only "send now" needs this piece's own POST /api/admin/push/{id}/send.
- Decision (no open item): the push on/off switch and the per-kind texts are keys in piece 13's settings store, written through 13's PUT /api/admin/settings/{key}. No extra table or endpoint for them.
- Decision (no open item): the public VAPID key goes in the existing /api/me answer, so there is no key endpoint. There is no unsubscribe endpoint either: the push service's "gone" answer switches subscriptions off.
- Decision (no open item): this piece also changes the answers of 002's /api/feed and 010's /api/admin/live, though the spec names no CHANGE line (the GET /api/hall push field belongs to piece 18). → Needs Manu: approve adding "CHANGE to: 002, 010" in one line, assumed approved meanwhile since the spec requires these effects.
