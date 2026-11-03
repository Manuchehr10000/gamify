# Contract: Blitz speed bonus
Status: building
Base: 6b46ec3157
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081beb962df62860cf61a

CHANGE to: 008
Owner's words (TAG): «Финальный блиц-квиз (5 вопросов, 60 секунд) даёт непропорционально много баллов за скорость — шанс резко подняться в рейтинге за 1 минуту.», from chat spec agreed 2026-11-02 by Manu

## What users see

- The blitz works like any timed quiz in 008: each guest starts it themselves, within its window, on /app/quiz/{id}.
- For each correct answer, the guest gets a speed bonus in points on top of 008's points. Fast answers earn much more.
- At the end: «4 из 5 · +40 баллов, +40 монет · +55 за скорость». The bonus counts in the rating, /app/profile and /hall like any other points.
- In the Excel file, the «Задания» sheet gets «Блиц» (да/пусто), «Бонус за скорость» (max per question), «Без потерь, сек» (grace window) and «Время бонуса, сек». Blank numbers mean 20 / 3 / 12. Downloading gives them back.
- In piece 13's task form, admins see the same four fields: «Блиц», «Бонус за скорость», «Без потерь, сек» and «Время бонуса, сек».

## Rules

- A quiz is a blitz when the «Задания» sheet (or piece 13's task form) marks it «Блиц» = да. «Блиц» on a task that isn't «Квиз» refuses the whole upload, naming the row and the reason (piece 13's rule); nothing is applied.
- Blitz numbers must be whole and not negative, with «Без потерь, сек» less than «Время бонуса, сек»; otherwise the whole upload is refused, naming the row and the reason, and nothing is applied. The task form refuses the same values with the same reason.
- The server records when it first sent each question to that guest (kept on the attempt, per question). Answer time = when the server receives the answer, minus that moment. The phone's clock plays no part. A reload returns the same question with its first moment unchanged.
- Bonus per correct answer: full within the grace window (default 3 s), then falling in a straight line to zero at the bonus time (default 12 s). Per-question bonuses are summed unrounded, then rounded once, halves up.
- The bonus is points only; coins follow 008's rule. It is paid when the quiz ends (all answered, timer out, «finish», or settled after the screen was closed), in the same transaction as 008's payment, as its own score_events row (reason «speed:{task id}», action 'speed', coins 0), written through piece 12's ledger helper, so it is paid once and shown apart.
- The stage multiplier (piece 16) applies to the bonus: the stage running when the quiz started, stored on the bonus row like any other.
- Wrong answers: no bonus, no penalty. Unanswered questions when time runs out: no bonus.
- Ties in the ranking follow 007: whoever reached the score first (the bonus row's time counts like any other points change).
- Blitz settings are locked while it is running, using piece 13's lock and its definition: while its window is open, or while any guest's attempt on it is still within its timer. This piece extends that lock to «Блиц», «Бонус за скорость», «Без потерь, сек» and «Время бонуса, сек». An upload that changes any of them on a running blitz is refused whole with «Нельзя менять во время блица», naming the row; nothing is applied and the blitz stays playable with its stored settings. The task form refuses the same change with the same message.

## Settings (piece 13)

- «Блиц» flag, maximum bonus per question (default 20), grace window (default 3 s), bonus time (default 12 s): this piece adds them to piece 13's task form; locked while running (piece 13's lock, extended to these four fields)

## What's out

- Everyone playing the same question at the same moment
- A live blitz show on the hall screen (piece 18 owns the hall screen)
- Showing the bonus per question during the quiz: it would reveal which answers were right, which 008 forbids; only the end line shows it
- A separate per-question countdown on the phone; 008's quiz countdown stays the only timer
- Locking a running blitz's questions, timer or points (piece 13)
- A coins bonus for speed
- Push announcing the blitz (piece 19)

## How to check it

- When I answer correctly 2 s after a question appears, then I get the full bonus.
- When I answer correctly at 7.5 s, with grace 3 s and bonus time 12 s, then I get half the bonus.
- When I answer correctly after 12 s, then I get no bonus but 008's points.
- When my phone clock is 5 minutes wrong, then my bonus is the same.
- When I reload mid-blitz, then the time for the current question keeps counting from when the server first sent it.
- When the blitz window is open and an admin edits its bonus, then the change is refused.
- When 1.5 × the expected guests answer within the same 10 seconds, then 95% get a reply within 1 second and none fail.
- (added) When I finish a 5-question, 50-point, 50-coin blitz with 4 right in a stage with multiplier 1, then I see «4 из 5 · +40 баллов, +40 монет · +N за скорость», and my rating points grow by 40 + N while my coins grow by 40 only.
- (added) When I upload a blitz row with the three numbers blank and download the file, then it shows «Блиц» = да and 20 / 3 / 12.
- (added) When an admin uploads a file changing a running blitz's bonus while guests are mid-blitz, then the upload is refused with «Нельзя менять во время блица» naming that row, nothing is applied, and the blitz stays playable with its old settings.
- (added) When I upload a blitz row with «Без потерь, сек» 12 and «Время бонуса, сек» 12, then the whole upload is refused, naming that row and the reason.
- (added) When an admin opens a quiz in piece 13's task form while it is not running, then they can set «Блиц» and the three numbers, and downloading the file gives the same values back.

## Size

Screens: 0
Endpoints: 0
Tables: 0

## Decisions

- Open item (drafted; the spec lists none): where the blitz numbers live → Decision: as four columns on tasks, set in the «Задания» sheet (blank = defaults) and downloaded back, and in piece 13's task form, where this piece adds the four fields, because piece 13 is built first and only provides the registry; each later piece adds its own fields. No new table.
- Open item (drafted): what "locked while running" means → Decision: reuse piece 13's lock and its definition (window open, or any attempt still within its timer) and extend it to the four blitz fields, not "any unfinished attempt", because piece 13 rejects that: abandoned attempts would lock forever. An attempt finishing after the window closes is still within its timer, so the settings payment reads cannot change under it.
- Open item (drafted): bad blitz numbers → Decision: the whole upload is refused naming the row and the reason (grace must be below bonus time, whole and not negative), per piece 13's importer and following 008's bad_timer style, so the bonus formula never divides by zero.
- Open item (drafted): rounding of the bonus → Decision: sum per-question bonuses unrounded, round once halves up, then piece 16's multiplier with its own halves-up rounding; matches piece 16 and keeps «half the bonus» exact (10 of 20).
- Open item (drafted): record send time for every quiz or only blitzes → Decision: every quiz (one JSONB column on quiz_attempts, set if absent when a question is first returned); simpler, harmless, and lets any quiz become a blitz later without a migration.
- Open item (drafted): how the bonus is stored → Decision: a separate score_events row «speed:{task id}» (action 'speed', coins 0), not folded into 008's row, so the end line, piece 16's per-row multiplier, piece 21's report and 007's tie rule all work unchanged; it is written through piece 12's ledger helper, whose open-award check under the guest's row lock makes it pay once.
- Open item (drafted): no new endpoints or screens → Decision: 008's POST /api/quiz/{id}/start, /answer and /finish return the bonus in the existing result; the end line is on /app/quiz/{id}; the four form fields go through piece 13's existing task form and its endpoints.
- Open item: "expected guests" for the load check → Needs Manu: TAG's expected guest count, assumed 300 (so 450 answers in 10 s) meanwhile; the existing per-attempt lock is per guest, so guests don't wait on each other.
