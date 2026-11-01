# Contract: Photo and text tasks
Status: on-dev
Base: 1bf5963f52
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be6081938751d0662aa25986

Client's words (TAG): «Селфи / фото / видео — Открывает камеру устройства или приём загрузки из галереи; предпросмотр перед отправкой — Нет — модерация», from backlog, added 2026-11-01

Client's words (TAG): «Крейзи-действие / творческое — Фото или видео произвольного формата + текстовое поле (для стихов, отзывов) — Нет — модерация, доступен бонус за креатив», from backlog, added 2026-11-01

Client's words (TAG): «Покупка — Фото чека / штрих-кода товара — Нет — модерация», from backlog, added 2026-11-01

Client's words (TAG): «Проектировать в расчёте на нестабильный Wi-Fi/перегруженную LTE-соту: локальное кэширование ленты, отложенная отправка фото/видео с индикатором «отправляется», без потери прогресса при обрыве связи.», from backlog, added 2026-11-01

## What users see

- On a photo task, «Выполнить» opens the camera or the gallery, then a preview with «Отправить» and «Переснять».
- The phone shrinks the photo before sending (longest side 1600 px, JPEG). The card shows «Отправляется…» until the upload finishes.
- If the network drops, the photo stays queued and retries while the app is open, with «Нет связи — отправим, когда появится». Closing the app before it is sent loses the photo.
- Points and coins count as soon as the upload succeeds; the card shows «Выполнено» at once. There is no «на проверке» state.
- On a text task, the guest types an answer (up to 500 characters) and sends it; the same rules apply.
- On a photo+text task, the guest sends a photo and a text together.
- A guest sends one submission per task. Retakes are allowed before sending; after sending it is final.
- In the Excel file, «Выполнение» takes three new values: Фото, Текст, Фото+текст.
- Photos are stored in Postgres, kept out of list queries.

## What's out

- Video
- Moderation, the moderator screen and serving photos back (piece 6)
- Tagging other guests on networking tasks
- Screenshot auto-check
- Sending after the app is closed (background sync)
- The job that deletes photos 30 days after the forum
- Quizzes, levels, leaderboard

## How to check it

- When I open a photo task and take a photo, then I see a preview with «Отправить» and «Переснять».
- When I send a 6 MB phone photo, then the server receives an image with its longest side at most 1600 px.
- When I send it, then I get the task's points and coins and the card shows «Выполнено».
- When I open the same task again, then I can't send a second photo.
- When I turn the network off and send a photo, then I see «Нет связи — отправим, когда появится», and when I turn it back on, the photo goes through and I get the points once.
- When the upload is retried after a timeout that actually reached the server, then I am awarded only once.
- When I send a text of 501 characters, then I can't.
- When a task is set to Фото+текст, then I must add both before «Отправить» works.
- When a partner photo task has 15 points and blank coins, then I get 15 points and 23 coins.
- When I send a photo for a task outside the current stage, then I see «Это задание сейчас недоступно» and get nothing.
- When I upload the Excel file with Фото, Текст and Фото+текст in «Выполнение», then those tasks load and download back unchanged.

## Size

Screens: 1

- the submit flow on /app/tasks/{id}

Endpoints: 2

- POST /api/tasks/{id}/photo
- POST /api/tasks/{id}/text

Tables: 1

- submissions
