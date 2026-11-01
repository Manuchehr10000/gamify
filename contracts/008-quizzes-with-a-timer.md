# Contract: Quizzes with a timer
Status: on-dev
Base: c002a8f53f
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be6081c38072e3be147aa811

Client's words (TAG): «Квиз — Один или несколько вопросов с вариантами ответа; периодический квиз — с обратным отсчётом окна (5 мин) — Да», from backlog, added 2026-11-01

Client's words (TAG): «Каждые ~90 минут приложение рассылает push с коротким квизом на 5 минут (окно закрывается — задание исчезает из ленты).», from rules 7.2, added 2026-11-01

Client's words (TAG): «Финальный блиц-квиз (5 вопросов, 60 секунд) даёт непропорционально много баллов за скорость — шанс резко подняться в рейтинге за 1 минуту.», from rules 4.4, added 2026-11-01

Client's words (TAG): «Задания привязаны к реальному контенту программы (вопросы по мастер-классу засчитываются только после чек-ина в зал — защита от «угадывания не глядя»).», from rules 4.2, added 2026-11-01

## What users see

- On a quiz card, «Начать» opens /app/quiz/{id}: one question at a time, with 2–4 options in shuffled order.
- A quiz with a timer shows a countdown. The server keeps the start time, so a reload doesn't reset it. When time runs out, the quiz ends and unanswered questions count as wrong.
- A quiz with «Доступно с/до» shows «Закроется через N мин» on its card and leaves the feed when the window closes. A quiz started before the close may be finished within its timer.
- One attempt per quiz. An unfinished quiz can be reopened and continued while its timer and window last.
- At the end the guest sees «3 из 5 · +30 баллов, +30 монет». Points and coins are paid in proportion to correct answers, rounded up; the partner ×1.5 rule for coins still applies. Correct answers are not shown.
- A quiz with «Требует» filled shows «Сначала отметьтесь в зале» until the guest has done that QR task, then opens.
- In the Excel file: «Выполнение» takes «Квиз»; the «Задания» sheet gets «Таймер, сек» and «Требует» (the ID of a QR task); a new «Вопросы» sheet has: ID задания, № вопроса, Вопрос, Вариант 1–4, Правильный (1–4). Downloading gives them back.
- A quiz task with no questions in the sheet fails on upload with the reason.

## What's out

- Push for the periodic quiz; «квиз открыт» on the hall screen
- A speed bonus beyond the timer
- Showing correct answers after the quiz
- Image questions; more than one correct option
- Retakes

## How to check it

- When I upload a file with a 5-question quiz, then its card opens one question at a time with the options in shuffled order.
- When I answer 3 of 5 right on a 50-point quiz, then I see «3 из 5» and get 30 points and 30 coins, and I don't see which answers were right.
- When a partner quiz has 25 points and blank coins and I answer 2 of 2, then I get 25 points and 38 coins.
- When I start the 60-second blitz and reload after 30 seconds, then the countdown shows about 30 seconds left, not 60.
- When the timer ends with 2 questions unanswered, then the quiz closes and those count as wrong.
- When I open a finished quiz again, then I see my result and can't answer again.
- When a window quiz closes, then its card leaves the feed within 1 minute.
- When a masterclass quiz has «Требует» set and I haven't scanned that hall's QR, then I see «Сначала отметьтесь в зале»; after scanning, it opens.
- When I send an answer after the timer has ended, then the server ignores it.
- When I upload a quiz task with no questions, or a question with the correct option outside 1–4, then that row fails with the reason and the others load.

## Size

Screens: 1

- /app/quiz/{id}

Endpoints: 3

- POST /api/quiz/{id}/start
- POST /api/quiz/{id}/answer
- POST /api/quiz/{id}/finish

Tables: 2

- questions
- quiz_attempts
