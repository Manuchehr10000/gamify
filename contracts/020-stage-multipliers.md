# Contract: Stage multipliers
Status: on-dev
Base: 2313a40f60
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be60817aa0e2f5c5b11029f9

CHANGE to: 002, 003, 005, 006, 008
Owner's words (TAG): «Сервер хранит расписание 4 этапов (время начала/конца, список активных заданий, множители, доступность маркета) — редактируется в админке, не в коде.», from chat spec agreed 2026-11-02 by Manu

## What users see

- When a stage's multiplier isn't 1, its cards in /app show «×2» (the stage's multiplier) in a corner, and the day bar shows it next to the stage name.
  - Cards keep showing the task's base points and coins; the corner mark says they are multiplied.
- The stage-change banner says it: «Этап 3 — очки ×2». At ×1 the banner stays as it is today.
  - The push with the same text is sent by piece 19.
- The admin sets each stage's multiplier in the «Этапы» sheet (new column «Множитель») or in the admin's stage form (piece 13).
  - Allowed: 1 to 5 in steps of 0.5; blank in the sheet = 1. Anything else, e.g. 1.3, is refused with «Множитель: от 1 до 5 с шагом 0,5».
  - Export writes the «Множитель» column, so the downloaded file uploads back unchanged.

## Rules

- Each stage has one multiplier, 1 to 5 in steps of 0.5, default 1. Set in the «Этапы» sheet (new column «Множитель») or in the admin.
- It multiplies points only. Coins, and the partner ×1.5 coin rule, stay as they are, so the market isn't emptied early.
- Points paid = base × multiplier, rounded to whole points, halves up (true half-up: 5 × 1.5 = 8, not Python's banker's rounding).
- The stage is the one running when the action began: the claim (piece 14), the QR scan, the link confirmation, or the quiz start.
  - A quiz keeps the multiplier from «Начать». At the finish, the base is its share of the task's points, computed and rounded up as today (piece 008). That base is then multiplied once and rounded half up.
  - The market-purchase task uses the stage running at the purchase.
- The multiplier is stored on each score_events row with the base (columns built by piece 12; this piece sets the multiplier). A rejection takes back exactly what was paid.
  - Rows that are not task awards (bonus, penalty, rows from before this piece) store multiplier 1 and base = their points (piece 12's migration already backfilled base = points on existing rows).
- The moderator bonus is piece 13's bonus percentage setting (default 50%) of the multiplied points, rounded up.
- «— очки ×N» is added to the banner title (feed.newStage); the stage's «Этапы» message line is unchanged.
- Changing a multiplier applies from that moment; past rows and open claims keep theirs.

## Settings (piece 13)

- multiplier per stage: from now on

## What's out

- The admin stage form itself, its save endpoint, its confirmation for a mid-stage change, and the change-log entry (piece 13; this piece only adds the multiplier field and its limits)
- Creating score_events.base_points and score_events.multiplier, and backfilling them (piece 12)
- Sending the stage-change push (piece 19; it uses this piece's banner text)
- Whether the blitz speed bonus is counted on base or multiplied points (piece 17)
- Showing «×N» on the hall screen or the leaderboard (piece 18), or in the moderation queue
- Multiplying coins, or changing the partner ×1.5 coin rule
- Changing how a quiz share is rounded (stays rounded up as in 008)
- Recomputing past awards or open claims when a multiplier changes
- Different multipliers per task or per guest

## How to check it

- When stage 3 has ×1.5 and I do a 5-point task, then I get 8 points and the usual coins.
- When the admin changes ×2 to ×3 after my claim but before my photo arrives, then I'm paid at ×2.
- When a moderator rejects a ×2 task, then exactly the doubled points are taken back.
- When a moderator gives a bonus on a 35-point task at ×2, then I get 35 more points.
- When I enter ×1.3, then it's refused.
- When the current stage has ×2, then its cards show «×2» in a corner and the day bar shows «×2» next to the stage name; at ×1 neither shows. (added)
- When a stage with ×2 starts, then the banner shows «Этап 3 — очки ×2». (added)
- When I start a quiz at ×2 and the admin changes it to ×3 before I finish, then I'm paid my share at ×2. (added)
- When I answer 1 of 3 questions right on a 10-point quiz at ×1, then I get 4 points, as today. (added)
- When I export the file and upload it back unchanged, then the «Этапы» sheet has the «Множитель» column and nothing is reported changed. (added)

## Size

Screens: 0

Endpoints: 0

Tables: 0

## Decisions

- Open item: where the admin edits the multiplier besides Excel → Decision: as a field on piece 13's stage form and the save endpoint piece 13 builds; this piece adds that field. The Excel path uses the existing /api/admin/tasks/import and /api/admin/tasks/export, and the day bar reads the multiplier from the existing /api/feed (StageOut body change), so 0 new endpoints.
- Open item: what holds the new data → Decision: columns only, no new table: stages.multiplier, quiz_attempts.multiplier and claims.multiplier (on piece 14's claims table). score_events.base_points and score_events.multiplier are built by piece 12; this piece only sets score_events.multiplier on task awards.
- Open item: which stage counts for the market-purchase task (not in the spec's list) → Decision: the stage running at the purchase, same as a QR scan.
- Open item: quiz started before a multiplier change → Decision: the multiplier is fixed at «Начать». At the finish, the share is computed as 008 does today (rounded up), then multiplied once and rounded half up. This matches "open claims keep theirs" and leaves ×1 payouts unchanged.
- Open item: base and multiplier on rows that are not task awards → Decision: bonus, penalty and pre-existing rows store multiplier 1 and base = points; piece 12's migration backfills base_points = points on existing rows. Bonus and take-back already read the award's paid points (routers/moderation.py), so 006 needs no new UI.
- Open item: how a half multiplier is written → Decision: Russian decimal comma, «×1,5»; the sheet accepts 1,5 and 1.5.
- Open item: card points at a multiplier → Decision: cards show the base points plus the «×2» corner (the spec's wording), not a recomputed total.
- Open item: push text «Этап 3 — очки ×2» → Decision: this piece builds it into the 002 banner text; piece 19 sends the same text when it is built.
- Open item: refusal text and export column (not in the spec) → Decision: kept, because piece 13's agreed spec requires a refusal that names the field and range and an export that uploads back unchanged.
