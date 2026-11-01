# Contract: Levels and profile
Status: on-dev
Base: e9e23b5bc8
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be608140b225e62287662dfa

Client's words (TAG): «5 уровней по накопленным баллам и система бейджей за категории — пороги и список бейджей задаются в админке (стартовые значения — в документе «Правила игрофикации», раздел 3.3), не хардкодятся в коде.», from backlog, added 2026-11-01

Client's words (TAG): «…при получении бейджа/уровня, отдельный полноэкранный момент — единственная «шумная» анимация в приложении…», from backlog, added 2026-11-01

Client's words (TAG): «Экран профиля: уровень, баллы, монеты, бейджи, история выполненных заданий.», from backlog, added 2026-11-01

Client's words (TAG): «5 уровней по накопленным баллам: Новичок форума (0) → Участник (50) → Актив (150) → Эксперт форума (300) → Легенда MF (500+). Уровень и бейджи видны в профиле и в общем лидерборде рядом с именем…», from rules 3.3, added 2026-11-01

## What users see

- The feed's top bar shows the guest's level name and «до следующего уровня N баллов» (nothing after the top level).
- When a guest crosses a threshold, the app shows a full-screen «Новый уровень: Актив» once, with one button to close it. It is the only full-screen animation in the app.
- The level follows current points: if a moderator's rejection drops the guest below a threshold, the lower level shows, with no moment.
- /app/profile shows level, points, coins (negative if a rejection took spent coins) and a history of done tasks, newest first: task, points and coins earned, and moderator outcomes («+18 бонус», «отклонено»). Market purchases show as spent coins.
- /app/rating and /hall show the level beside each name.
- The Excel file gets a «Уровни» sheet: Название, Баллов от. The empty template comes pre-filled with TAG's five levels. Downloading gives it back.

## What's out

- Badges (piece 11)
- Sound; the small «+N» animation beyond what exists
- Editing the name or photo in the profile
- Points or coins for reaching a level

## How to check it

- When I have 140 points, then the bar shows «Участник» and «до следующего уровня 10 баллов».
- When a task takes me from 140 to 165 points, then I see the full-screen «Новый уровень: Актив» once, and not again after a reload.
- When a moderator rejects a photo and I drop back to 140, then I see «Участник», and climbing past 150 again shows the moment again.
- When I open /app/profile, then I see my level, points, coins and every done task with what it earned, including bonuses, rejections and purchases.
- When I open /app/rating or /hall, then each name has its level beside it.
- When I upload the file with «Уровни» changed to 0/40/120/250/400, then levels follow the new thresholds without a deploy.
- When I upload a «Уровни» sheet with no 0 threshold or thresholds out of order, then it fails with the reason and the old levels stay.

## Size

Screens: 1

- /app/profile

Endpoints: 1

- GET /api/profile

Tables: 1

- levels
