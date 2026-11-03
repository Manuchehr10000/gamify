# Contract: Badges set by admin
Status: on-dev
Base: bec9977d2b
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081caafd1caaf939ba66c

CHANGE to: 011
Owner's words (TAG): «…пороги и список бейджей задаются в админке…, не хардкодятся в коде.», from chat spec agreed 2026-11-02 by Manu

Client's words (TAG): «Бейджи за категории: «Фотоохотник» (5 фото-заданий), «Нетворкер» (обе селфи-цепочки с друзьями), «Эрудит» (5 квизов подряд без ошибок), «Друг бренда» (3 задания одного партнёра), «Дух форума» (одно крейзи-задание с бонусом от модератора).», from rules 3.3

## What users see

- Guests: nothing changes. The full-screen moment («Новый бейдж: …»), the shelf in /app/profile (earned in colour, others greyed with their condition) and the icons beside names in /app/rating and /hall stay as 011, now for whatever badges the admin has set.
- Hall screen: when a guest earns a badge marked «на экран», /hall shows it through piece 18's full-screen interrupt, e.g. «Иван П. — бейдж «Эрудит»».
- Admin: badges are set in a new «Бейджи» sheet of the Excel file (upload, preview and download as the other sheets) or in a «Бейджи» tab of /admin/settings, built on piece 13's generic list form (add, edit, switch off). Each badge has: ID, «Название», «Тип правила», the numbers the rule needs, optional filters, «Монеты» (default 0), «На экран» (да/нет), on/off.
- Admins build badges from six rule types:
  - «Задания»: N tasks done, filtered by task type and/or partner. «Любой один партнёр» means N tasks of the same partner.
  - «Все задания типа»: every task of a type.
  - «Квизы подряд»: N quizzes in a row, each with no mistakes. A quiz with a mistake resets the count.
  - «Бонусы»: N moderator bonuses, optionally on one task type.
  - «Первые N»: among the first N guests to do a given task.
  - «Место»: in the top N when the ranking is frozen.
- TAG's five badges come pre-filled:
  - «Фотоохотник» = Задания, type Фото/Фото+текст, 5
  - «Нетворкер» = Все задания типа Нетворкинг
  - «Эрудит» = Квизы подряд, 5
  - «Друг бренда» = Задания, any one partner, 3
  - «Дух форума» = Бонусы, type Крейзи, 1
- A badge row (sheet or form) with an unknown rule type or missing numbers is refused with the reason, naming the row or field.

## Rules

- As 011, every badge follows what's true now: a rejection that breaks a condition removes the badge.
- Optional coins per badge (default 0), paid and taken back through score_events via piece 12's ledger helper (action badge, reason badge:{id}, points 0, multiplier 1), so badge coins never move the ranking or levels. Taking back writes a reversal row (action badge, reverses_id pointing at the badge:{id} award, coins back), and can leave coins below zero, as a moderator's penalty does today. Re-earning writes a new award, allowed by the helper's "one open award per reason" check.
- Adding, changing or switching off a badge checks all past activity at once.
- Badges are worked out when something changes (a task done, a moderator's decision, a quiz finished or settled, a freeze or unfreeze, a «Бейджи» or «Задания» upload, a badge or task changed in the form), not when the guest next opens the feed: coins and the hall announcement happen at that moment. The guest's full-screen moment still shows once, on their next load.
- A badge's greyed condition in /app/profile is written from its rule (e.g. «5 заданий: Фото, Фото+текст»); the rule-type wording is in the language file, the badge name comes from the admin.
- Rejected submissions never count, as 011.
- Badge announcements on /hall follow piece 18's push rule: they interrupt only in «Авто» and «Только логотипы», never in «Эфир» or «Пауза»; a push waiting at the same time goes first; «Место» badges from a freeze are not announced.

## Settings (piece 13)

- the badge list: recheck past

## What's out

- New admin screens: the «Бейджи» form is a tab of piece 13's /admin/settings, registered as the badges kind in piece 13's list registry, and follows its conventions (change log, conflict message, confirmation).
- Own badge endpoints: the form uses piece 13's generic /api/admin/lists/{kind}.
- Partners table and partner IDs: piece 12 (the partner filter matches tasks by piece 12's partner ID).
- Hall slide cycle and the full-screen interrupt display: piece 18 (this piece only feeds badge announcements into it).
- Push notifications for badges.
- Stage multipliers on badge coins: badge rows always carry multiplier 1.
- Custom badge artwork, uploaded icons or picking an icon per badge: each rule type has one default lucide icon; TAG's five keep 011's icons.
- Hall announcements for badges gained by an admin's recheck (adding, changing or switching off a badge): those award quietly, so a list change never floods the screen.
- Announcing guests with «В рейтинге: нет».
- Rule types beyond the six; combining rules (AND/OR) in one badge.
- Deleting a badge guests hold: it can only be switched off (piece 13's rule); switching it off removes it from everyone and takes its coins back.

## How to check it

- When I finish 4 perfect quizzes, one with a mistake, then 5 perfect ones, then I get «Эрудит» only after the last five.
- When I do 3 tasks of one partner, then I get «Друг бренда»; 3 tasks of 3 partners don't count.
- When a moderator rejects one of my 5 photos, then «Фотоохотник» disappears.
- When the admin lowers «Фотоохотник» to 3, then every guest with 3 photo tasks gets it at once.
- When the ranking is frozen, then the top N get the «Место» badge.
- When a badge has 20 coins and is removed, then the 20 coins are taken back.
- When a badge has 20 coins and I earn it, then my coins go up by 20 at once, with no multiplier, and my points and place don't change. (added)
- When I earn a badge marked «на экран», then /hall shows my first name, last initial and the badge full screen. (added)
- When a badge is «Первые N» with N = 3 on a task, then the first 3 guests to do it get the badge and the 4th doesn't; if one of the 3 is rejected, the 4th gets it. (added)
- When I upload a «Бейджи» sheet with a row of unknown type or a missing number, then the upload names that row and the reason, and the old badges stay. (added)
- When I add a badge in the «Бейджи» form, then guests who already meet it get it at once. (added)
- When I download the file after the migration, then the «Бейджи» sheet holds TAG's five badges, ready to upload back unchanged. (added)
- When /hall is in «Эфир» and a guest earns an «на экран» badge, then the screen is not interrupted. (added)

## Size

Screens: 0

Endpoints: 0

Tables: 1

- badges

## Decisions

- Open item: who builds the admin form for badges → Decision: piece 13 is always built first, so this piece registers badges as a kind in piece 13's list registry; the form becomes a «Бейджи» tab of /admin/settings and uses piece 13's /api/admin/lists/{kind}, with no badge endpoints of its own.
- Open item: how the hall announcement is shown → Decision: through piece 18's existing full-screen interrupt (15 s, like a push); recent «на экран» awards ride the existing hall response one at a time, and any older than 60 seconds are dropped so a backlog never builds.
- Open item: «Место» when the ranking is unfrozen → Decision: the badge follows what's true now, so unfreezing removes it and takes its coins back; freezing again awards it again.
- Open item: «Квизы подряд» order and timeouts → Decision: quizzes count in the order they finished; a quiz ended by its timer with any unanswered or wrong question counts as a mistake and resets; once N perfect in a row is reached the badge stays (finished quizzes can't be rejected).
- Open item: «Первые N» after a rejection → Decision: worked out from awards that still stand, by the time they were earned, so a rejected guest drops out and the next one moves in.
- Open item: icons for admin-made badges → Decision: one default lucide icon per rule type, with no icon column (the spec doesn't ask for one); TAG's five keep 011's icons.
- Open item: names and condition texts move out of the language file → Decision: the name comes from the admin's row; the greyed condition is generated from the rule using rule-type wording kept in the language file.
- Open item: taking back coins already spent → Decision: coins may go below zero, mirroring the moderator penalty in moderation.py; the market already refuses purchases without enough coins.
- Open item: badge ID length → Decision: at most 26 characters, checked on upload and in the form, so badge:{id} fits score_events.reason (String(32)).
- Open item: how TAG's five are pre-filled → Decision: the migration inserts them as rows of badges, keeping 011's codes (photo_hunter, …) so existing badge_awards carry over; this is the client's real configuration, not demo data.
- Open item: a bad «Бейджи» row → Decision: follows piece 13's existing rule: the whole file is refused, naming every bad row, so a recheck never runs against half a list.
- Open item: a badge missing from an uploaded sheet → Decision: piece 13's preview lists it as «будет скрыто»; on confirm it is switched off, which removes it from everyone and takes its coins back.
- Open item: when badges are worked out → Decision: eagerly at every change listed in Rules, with badge_awards recording what the guest holds plus a "seen" mark for the moment (column changes only), because coins and announcements can't wait for a feed load.
- Open item: hall announcements from an admin recheck → Decision: none; only badges a guest earns by their own action are announced (not «Место» badges from a freeze), so changing a threshold mid-event doesn't flood the screen.
