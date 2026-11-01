# Contract: QR and link tasks
Status: on-dev
Base: 0692918a6c
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be608141928fc50a2e3e1677

Client's words (TAG): «Действие (чек-ин) — Сканирование QR-точки на площадке (стенд, мастер-класс, зона) или подтверждение действия одной кнопкой — Да, если по QR», from backlog, added 2026-11-01

Client's words (TAG): «Территориальное — QR-код или геозона (GPS/Bluetooth-маячок) физически на площадке — Да», from backlog, added 2026-11-01

Client's words (TAG): «Регистрация — Открытие внешней ссылки + подтверждение галочкой — Да, с проверкой возврата в приложение», from backlog, added 2026-11-01

## What users see

- A guest points the phone camera at a task's QR code at the venue; the app opens on /q/{code} with «+N баллов, +N монет» and the task name.
- Scanning the same QR again shows «Уже выполнено», with no second award.
- Scanning a QR whose task isn't on now (another stage, or its time window closed) shows «Это задание сейчас недоступно».
- A wrong or broken QR shows «QR-код не найден».
- On a link task, «Выполнить» opens the link in a new tab; back in the app, the guest ticks «Я зарегистрировался», confirms, and gets the points. The tick shows only after the link was opened.
- Done tasks show «Выполнено» in the feed and on the task page.
- The top of the feed shows the guest's total points and coins.
- In the Excel file, the admin sets «Выполнение» to QR or Ссылка (and fills «Ссылка» for link tasks); other tasks keep the «Выполнить — скоро» button.
- On /admin/tasks/qr the admin sees one large printable QR per QR task, with its ID and text; the codes don't change when the file is re-uploaded.

## What's out

- Quizzes, photo and text tasks, moderation, the «на проверке» state
- "Confirm with one button" without a QR
- Geolocation and beacons
- Doing a task more than once (e.g. per speaker); limits per guest
- Stage multipliers, levels, badges, leaderboard, market
- The big animation and sound (only the plain «+N» screen)
- Logging in from a QR scan: a guest who isn't logged in sees the badge message

## How to check it

- When I scan a QR task's code on my phone during its stage, then I see «+15 баллов, +15 монет» and the card says «Выполнено».
- When I scan it a second time, then I see «Уже выполнено» and my totals don't change.
- When I scan the QR of a stage 3 task during stage 2, then I see «Это задание сейчас недоступно».
- When I change one character in a QR link, then I see «QR-код не найден».
- When I open a link task and come back, then I can tick «Я зарегистрировался» and get its points once.
- When a partner QR task has 15 points and blank coins, then I get 15 points and 23 coins.
- When I open /admin/tasks/qr, then I see a printable QR for each QR task, and after re-uploading the file the codes are the same.
- When I open /admin/tasks/qr without the password, then I see only the login prompt.

## Size

Screens: 2
- /q/{code}
- /admin/tasks/qr

Endpoints: 3
- POST /api/scan
- POST /api/tasks/{id}/complete
- GET /api/admin/tasks/qr

Tables: 0
