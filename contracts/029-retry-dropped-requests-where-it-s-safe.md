# Contract: Retry dropped requests where it's safe
Status: done
Lesson: fact The Worker (deploy/src/index.ts) resends a request the container dropped only for GET/HEAD and the sends in SAFE_SENDS. A new POST goes on that list when repeating it after a success answers with the first result or an "already" answer that reads as done.
Base: 16d0e9f230
Approved: 2026-11-08 by Manu
Tracker: https://app.notion.com/p/412c62b4be6081a1b3eed9e671d0652a

Fixes: on dev a request fails now and then with «Что-то пошло не так. Попробуйте ещё раз.» because the container dropped it («Container suddenly disconnected, try again»), and trying again by hand always works
Owner's words: Seen: 4 times in about 90 minutes. The body was HTTP 500 «Container suddenly disconnected, try again». Guests saw «Что-то пошло не так»: on a staff save, a tasks list read, a task read, and a quiz answer. A manual retry always worked., from backlog, added 2026-11-08

Owner's words: «Approve with your picks» (opening /app, POST /api/feed/next, is left off the retry list), from chat 2026-11-08

## What users see

- Fewer «Что-то пошло не так. Попробуйте ещё раз.» screens. When the container drops a request («Container suddenly disconnected» or «Error proxying request to container»), the Worker sends it once more by itself, only where a repeat gives nothing twice:
  - every read (GET and HEAD). Nothing is awarded or charged twice; a level or badge moment caught in a dropped response is not shown again, as today when a guest retries by hand.
  - these sends, which answer with the first result or an "already" answer when repeated: photo and text claims and their files, quiz start, answer and finish, QR scan and link tasks, consent, the moderator's decision, push subscribe and received, the hall logo logs, rating freeze, and the two upload previews.
- If the first send had gone through, the retry can show the "already" answer: «Уже выполнено» to the guest, «Уже проверено: <own name>» to the moderator. Nothing is awarded, paid or issued twice.
- CHANGE: today the Worker retries any request on «Error proxying request to container». That retry now follows the same list, so a walk-in guest, a stage advance, a push send or a new admin row can never be made twice by it.

## Rules

- Each automatic retry writes one line to the Worker's log with the method, the path and which error it was.
- A send is on the list only if a repeat after a success answers with the first result or an "already" answer that reads as done to the person who sent it.

## What's out

- No retry for sends where a repeat after a success shows an error or does it twice: market buy («Этот приз у вас уже есть»), «Выдано» at the stand (would show a red «Уже выдано в …» to the staff member who just issued it), the hall mode switch (a late retry could overwrite a newer switch), saves and deletes on /admin/settings including the staff save from the test run («Изменено другим администратором — обновите страницу»), the guest's photo delete, the tasks and guests file uploads, partner logo upload, desk walk-in, «Следующий этап» with confirm, push send, adding an admin row, and logins. These still show the error, as today.
- Opening /app and loading more cards (POST /api/feed/next) still shows the error on a dropped request: a retry would skip a batch of cards. It is no longer retried on «Error proxying» either.
- Making those sends safe to repeat needs backend changes to the pieces that own those endpoints: that would be its own piece.
- No change to the instance size in deploy/wrangler.jsonc. If the dev logs show memory pressure or restarts, a bigger instance is a separate CHANGE for the owner.
- No change to the backend, the frontend's error message or the phone's own photo retry (piece 18)
- Production gets this only through the pipeline

## How to check it

- When I use the app on dev while a dev deploy restarts the container, then the gamify-dev Worker log shows a retry line for a GET or one of the listed sends, and that screen doesn't show «Что-то пошло не так». (Or read it from the log after the next drop.)
- When I check the gamify-dev Worker log after a day on dev, then there is never a retry line for POST /api/desk/guests, POST /api/market/{id}/buy, POST /api/stand/{code}/issue, POST /api/feed/next, POST /api/admin/stages/advance, POST /api/admin/push/{id}/send or any PUT or DELETE.
- When I repeat the test run's guest steps on dev (task pages, quizzes, photos), then no «Что-то пошло не так» shows on a task page, a quiz answer or a photo send. Opening /app can still show it on a drop.
- When I answer a quiz, send a photo, scan a QR task and press «Выдано» at /stand/:code, then each works as before.

## Size

Screens: 0

Endpoints: 0 (only deploy/src/index.ts changes)

Tables: 0
