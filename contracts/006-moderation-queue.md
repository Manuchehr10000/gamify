# Contract: Moderation queue
Status: on-dev
Base: 08dd5d4982
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be60811ea50ceeff02bc975a

Client's words (TAG): «Веб-интерфейс (для планшета), список заданий «на проверке» очередью, с медиа-превью.», from backlog, added 2026-11-01

Client's words (TAG): «Кнопки: «Принять», «Принять + бонус за креатив (+50%)», «Отклонить со штрафом», «Отклонить без штрафа» (для технических ошибок не по вине игрока).», from backlog, added 2026-11-01

Client's words (TAG): «Простая ролевая защита (логин/пароль или PIN на устройство модератора), чтобы не путать 2–3 модераторов между собой в логах.», from backlog, added 2026-11-01

Client's words (TAG): «Модератор видит новую отправку в очереди не позднее чем через 10 секунд после отправки игроком.», from backlog, added 2026-11-01

Client's words (TAG): «Бонус за креатив: модератор может начислить до +50% к базовым баллам за особенно яркое исполнение. Штраф: явный спам (10+ одинаковых фото подряд), оскорбительный контент, фальшивые фото не с площадки — минус все баллы за задание и предупреждение в приложении «в фирменном» тоне (без извинений, по делу, с инструкцией, что делать правильно).», from rules 7.1, added 2026-11-01

## What users see

- A moderator opens /moderate on a tablet and enters their own PIN. Their name shows at the top; every decision is logged with their name and the time.
- Moderator names and PINs come from an environment setting; until TAG sends names, they are «Модератор 1–3».
- The queue shows unchecked photo and text submissions, newest first: photo, text, task name, points, and the guest's first name and last initial. A new submission appears within 10 seconds, with no reload.
- Points are already counted (post-moderation), so the four buttons do this:
  - «Принять»: marks it checked; nothing changes for the guest.
  - «Бонус +50%»: adds half the task's base points again, rounded up. Coins don't change.
  - «Отклонить — переснять» (no penalty, for technical faults): takes the points and coins back and reopens the task; the guest sees «Фото не подошло — отправьте ещё раз» and can send again.
  - «Отклонить со штрафом» (spam, offensive, fake): takes the points and coins back; the task stays closed; the guest sees a short warning with what to do right.
- Coins may go below zero after a rejection. A guest with negative coins can't buy in the market until they earn them back.
- A «Топ-20» filter shows only unchecked submissions from the current top 20 by points, for the check before the ceremony.
- The queue header shows how many are waiting and the age of the oldest.
- Each submission is decided once; a second moderator opening the same item sees it's already done.

## What's out

- Changing a decision after it's made; appeals; free-text comments to the guest
- Blocking a duplicate photo sent to another task
- Video
- The leaderboard screen and the hall screen (piece 7)
- Moderation of QR, link, market and quiz tasks
- The job that deletes photos 30 days after the forum

## How to check it

- When I open /moderate without a PIN, then I see only the PIN prompt; with a wrong PIN, I stay there.
- When I enter Moderator 2's PIN, then I see «Модератор 2» at the top, and my decisions are logged under that name.
- When a guest sends a photo, then it appears in my queue within 10 seconds, without a reload.
- When I press «Принять», then it leaves the queue and the guest's totals don't change.
- When I press «Бонус +50%» on a 35-point task, then the guest gets 18 more points and no more coins.
- When I press «Отклонить — переснять», then the guest loses that task's points and coins, sees «Фото не подошло — отправьте ещё раз», and can send a new photo that counts.
- When I press «Отклонить со штрафом», then the guest loses that task's points and coins, sees the warning, and can't send that task again.
- When a guest who spent the coins from a photo is rejected, then their coin balance goes negative and the market buttons stay locked until it is above the price again.
- When two moderators decide the same submission at the same moment, then only the first decision counts.
- When I switch on «Топ-20», then I see only unchecked submissions from guests now in the top 20 by points.

## Size

Screens: 1

- /moderate

Endpoints: 4

- POST /api/moderator/login
- GET /api/moderation/queue
- GET /api/submissions/{id}/photo
- POST /api/submissions/{id}/decision

Tables: 0
