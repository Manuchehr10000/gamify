# Contract: Console look: admin pages
Status: building
Base: d34794d21b
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081bc8952dfe40dc2ed70

CHANGE to: 001, 002, 003, 007, 010 (look only, behaviour stays, apart from the menu below)
Needs: pieces 23 and 25
Owner's words: «Make it in the style of Atari 80 gaming console. Admin is desktop and mobile, user is mobile. Mobile is website app. Optimised for iphone and android, all major browsers.», from chat 2026-11-02

Owner's words: «Build it in the app», from chat 2026-11-02

Design: Gamify Console design system · admin screens

## What users see

- /admin/live, /admin/tasks, /admin/tasks/qr and /admin/guests use the light Label look, like the admin canvas artboards.
- CHANGE: the admin pages get a shared menu listing every admin page («Живые цифры», «Задания и этапы», «Список гостей», «QR-коды заданий» today): from 768 px wide a side menu with woodgrain trim, below 768 px a top bar that scrolls sideways. The menu replaces the QR sheet's «Назад» link; the «QR-коды для печати» link on /admin/tasks stays.
- Tables are real tables on a desktop and become stacked cards on a phone.
- /admin/live: seven screen-panel readouts (Гостей вошло, Активны за 15 минут, Ждут проверки, Самая старая ждёт, Призов куплено, Выдано на стендах, Осталось), with the oldest wait in minutes as today and no warning colour; «Выполнения по типам заданий» and «Выполнения по этапам» with Выполнений only; «Партнёры» with Выполнений and Уникальных участников; «Скачать отчёт по партнёрам».
- Upload results show a green strip with the counts. Failed rows show as a red strip on /admin/tasks and as a «Не загружены строки:» table (Строка, Причина) on /admin/guests. A file with missing columns or sheets shows a red strip with today's message.
- On /admin/tasks the next-stage confirm asks inside the stage card («Начать следующий этап прямо сейчас? …» with «Отмена» / «Подтвердить»); freezing and unfreezing the rating ask the same way.
- The QR sheet and the top 10 print cleanly: no buttons, no menu, no background, one card per cut-out.
- The browser bar is light.
- After this piece no screen uses lucide-react icons, so it is removed from the frontend's packages and the stack list (decided with piece 23's icons, 2026-11-03).
- Keyboard focus shows a thick ring around every control, and the phone rules from piece 23 (48 px taps, no zoom on fields, still under reduced motion) hold here too.

## What's out

- The admin login card (piece 25)
- A «Выйти» button and the «Администратор» name in the menu (the artboards show them; the app has no logout today)
- A «Уникальных участников» column for types and stages (the Live artboard shows one; the app has no such number)
- Admin settings (piece 13), badges set by admin (piece 20) and the partner report with photo links (piece 21): they come after this piece, in the Console look (piece 23's Decisions: order). Any admin page that exists when this piece is built gets a menu item and this look.
- Any other change to what the admin pages do, upload or download

## How to check it

- When I open /admin/live on a laptop, then I see the side menu, the seven readouts and the three tables like the Live artboard, without the extra column.
- When I tap «Список гостей» in the menu on /admin/live, then I see /admin/guests without logging in again.
- When I open /admin/live on a phone, then the menu is a top bar and each table row is a card.
- When I upload a tasks file with two bad rows, then I see a green strip with the counts and a red strip naming both rows.
- When I upload a guest list with two bad rows, then I see a green strip with the counts and a two-row «Не загружены строки:» table.
- When I press «Начать следующий этап сейчас», then the card asks me to confirm in place, and «Отмена» leaves the stage unchanged.
- When I print /admin/tasks/qr, then the page shows only the QR cards, with no buttons or menu.
- When I print the top 10 from /admin/tasks, then no buttons or menu print.
- When I tab through /admin/tasks with the keyboard, then I always see which control is focused.
- When I open each admin page at 320 px wide, then nothing on the page scrolls sideways except the menu bar, and every table row is a card.

## Size

Screens: 4

- /admin/live
- /admin/tasks
- /admin/tasks/qr
- /admin/guests

Endpoints: 0

Tables: 0

## Decisions

- Settled with approval, 2026-11-03: the shared admin menu (flagged CHANGE above) is in.
- Settled with approval, 2026-11-03: new language-file keys «Разделы» (the menu's name for screen readers) and «(сейчас идёт)» (the current stage, for screen readers).
- Settled with approval, 2026-11-03: the oldest wait gets no warning colour, as today. A warning is its own backlog row.
