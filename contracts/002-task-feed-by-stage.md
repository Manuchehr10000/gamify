# Contract: Task feed by stage
Status: on-dev
Base: a9c170e316
Approved: 2026-10-27 by Manu
Tracker: https://app.notion.com/p/406c62b4be60810f969ac92d21770fbb

Client's words (TAG): «Главный экран — вертикальная лента карточек-заданий, отфильтрованных по текущему активному этапу (сервер отдаёт этап по времени; см. 3.7). Карточка задания содержит: тип (иконка), текст, награду (баллы + монеты), статус (доступно / на проверке / выполнено / временно недоступно), бейдж партнёра при наличии тега ★. Одновременно в ленте не более 10–20 карточек на этапе (конфигурируется в админке) — ротация из полного каталога, с приоритетом заданий с истекающим временным окном (периодические квизы).», from backlog, added 2026-10-27

Client's words (TAG): «Сервер хранит расписание 4 этапов (время начала/конца, список активных заданий, множители, доступность маркета) — редактируется в админке, не в коде. При смене этапа — push-уведомление всем активным пользователям с фирменным текстом (см. правила, разделы 4.1–4.4) и визуальное обновление статус-бара в приложении (индикатор прогресса дня из 4 сегментов).», from backlog, added 2026-10-27

Client's words (TAG): «CRUD по заданиям (тип, текст, баллы, монеты, тег партнёра, этап, лимит на игрока, гео/QR-привязка).», from backlog, added 2026-10-27

## What users see

- After the welcome screen, a guest lands on /app: a list of cards for the current stage only.
- Each card shows the type icon and label, the task text, points and coins, a ★ partner badge with the partner's name for partner tasks, and "Выполнено" once done.
- Cards are ordered: tasks with a time window first, then partner tasks by package (General, Headliner, MF Partner, Supporters), then the rest.
- At the top: a 4-part day bar with the current stage name and its end time.
- Tapping a card opens /app/tasks/{id} with the full text and reward; the "Выполнить" button shows "скоро" until piece 3.
- Before stage 1 starts, the guest sees «Игра начнётся в 09:00»; after stage 4 ends, «Игра завершена».
- When the stage changes, the feed and the bar update within 1 minute, with no reload, and a short banner shows the new stage name and its line from the rules.
- If the network drops, the last feed stays on screen with a line «Нет связи — показаны последние данные».
- On /admin/tasks (same admin password) the admin uploads the Excel file with the «Этапы» and «Задания» sheets and sees what was added, changed, hidden, and which rows failed, and why.
- The admin downloads the current file at any time; with nothing uploaded yet, it comes out as an empty template with the right columns.
- /admin/tasks shows the current stage and a «Начать следующий этап сейчас» button.

## What's out

- Doing tasks: quizzes, photos, QR, text (piece 3); quiz questions sheet (piece 3)
- Awarding points for tasks (pieces 3–4)
- Card rotation and the 10–20 cap; tabs by type
- "На проверке" and "временно недоступно" card states; crowd control
- Push notifications
- Market opening by stage (piece 7)
- Partner logos on cards (name only); a separate partners table
- Editing tasks one by one in forms (re-upload instead)
- Tajik texts

## How to check it

- When I upload a file with 4 stages and TAG's 42 tasks, then I see "42 added" and any failed rows with the reason.
- When I upload a row with an unknown stage or missing points, then that row fails with the reason and the others still load.
- When a partner task has 15 points and an empty coins cell, then its card shows 15 points and 23 coins.
- When I change one task's text, remove another from the file and upload again, then the first card shows the new text, the second is gone from the feed, and nothing else changes.
- When I download the file, then I get both sheets with what is loaded now, ready to edit and upload again.
- When the clock is inside stage 2, then the feed shows only stage 2 tasks, in the stated order, and the bar shows segment 2 of 4.
- When I press «Начать следующий этап сейчас», then within 1 minute every open phone shows stage 3's tasks, the new bar and the banner, with no reload.
- When the clock is before stage 1 or after stage 4, then I see «Игра начнётся в …» or «Игра завершена».
- When I turn off the network and reload /app, then I still see the last feed and the no-network line.
- When I enter stage times in Dushanbe time, then stages start at those local times, not 5 hours off.
- When I tap a card, then I see its full text, reward, and a "скоро" button.
- When I open /admin/tasks without the password, then I see only the login prompt.

## Size

Screens: 3
- /app
- /app/tasks/{id}
- /admin/tasks

Endpoints: 6
- GET /api/feed
- GET /api/tasks/{id}
- GET /api/admin/stages
- POST /api/admin/stages/advance
- POST /api/admin/tasks/import
- GET /api/admin/tasks/export

Tables: 2
- stages
- tasks
