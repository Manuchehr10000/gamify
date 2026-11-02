# Contract: Badges
Status: done
Base: 01fb362e29
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be60813ab10cc0bf08bfc4dc

Client's words (TAG): «Бейджи за категории: «Фотоохотник» (5 фото-заданий), «Нетворкер» (обе селфи-цепочки с друзьями), «Эрудит» (5 квизов подряд без ошибок), «Друг бренда» (3 задания одного партнёра), «Дух форума» (одно крейзи-задание с бонусом от модератора).», from rules 3.3, added 2026-11-01

## What users see

- Five badges, each earned once:
  - «Фотоохотник»: 5 photo tasks done (Фото or Фото+текст)
  - «Нетворкер»: every task of type Нетворкинг in the file done
  - «Эрудит»: 5 quizzes finished with a full score
  - «Друг бренда»: 3 tasks of one partner done
  - «Дух форума»: a Крейзи task that got a moderator bonus
- Earning a badge shows the same full-screen moment as a level, once: «Новый бейдж: Фотоохотник».
- Badges show in /app/profile (earned in colour, others greyed with their condition) and as small icons beside the name in /app/rating and /hall.
- A badge follows what is done now: a moderator's rejection that breaks a condition removes it, with no moment. Earning it again shows the moment again.
- Rejected submissions never count towards a badge.
- Badge names and conditions' texts are in the language file.

## What's out

- Editing badges or their conditions in the admin or Excel (TAG's «задаются в админке» is not met: conditions are fixed in code)
- «подряд без ошибок» for Эрудит: replaced by 5 quizzes with a full score
- Points or coins for badges
- Custom badge artwork beyond lucide icons

## How to check it

- When I finish my 5th photo task, then I see «Новый бейдж: Фотоохотник» once, and not again after a reload.
- When a moderator rejects one of those 5 photos, then the badge disappears from my profile and the ranking.
- When I finish 5 quizzes with a full score, then I get «Эрудит»; a quiz with one wrong answer doesn't count.
- When I do 3 tasks of the same partner, then I get «Друг бренда»; 3 tasks of 3 different partners don't count.
- When a moderator gives my Крейзи photo a bonus, then I get «Дух форума».
- When I do every Нетворкинг task, then I get «Нетворкер».
- When I level up and earn a badge from the same task, then I see both moments, one after the other.
- When I open /app/profile, then I see all five badges, earned ones in colour and the rest greyed with their condition.

## Size

Screens: 0

Endpoints: 0

Tables: 1

- badge_awards
