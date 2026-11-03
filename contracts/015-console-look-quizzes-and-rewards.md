# Contract: Console look: quizzes and rewards
Status: building
Base: fa8abec589
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be60813a967af83661ffcda0

CHANGE to: 004, 007, 008, 009, 011 (look only, behaviour stays)
Needs: piece 23
Owner's words: «Make it in the style of Atari 80 gaming console. Admin is desktop and mobile, user is mobile. Mobile is website app. Optimised for iphone and android, all major browsers.», from chat 2026-11-02

Owner's words: «Build it in the app», from chat 2026-11-02

Design: Gamify Console design system · guest screens

## What users see

- /app/quiz/:id, /market, /app/rating, /app/profile and the full-screen level and badge moment on /app have piece 23's Console look, like the guest canvas artboards Quiz, QuizResult, Market, Rating, Profile and LevelUp.
- Copy and data stay as the app has them: the quiz result reads «3 из 5 · +30 баллов, +30 монет» over the quiz text (not the artboard's «Выполнено» / «правильных ответов»), and history rows show no time.
- The quiz shows «Вопрос 1 из N», the question, its 2–4 answers as lettered buttons and a countdown on a screen panel; at 10 seconds or less the timer turns red and says «Мало времени» in words, not only in colour. «Время вышло», «Сначала отметьтесь в зале» (with a lock), «Квиз не найден» and «Этот квиз сейчас недоступен» are one message card each.
- Each prize in the market shows its state: can buy, confirming, buying, not enough coins (a greyed-out «Не хватает 12 монет»), sold out («Закончились»), market closed (locked «Обменять» under «Маркет откроется в 14:30» or «Маркет скоро откроется»), waiting at the stand (QR, «Подойдите к стенду партнёра …» and «Код: …», shown first), received («Получено»), and an error line when a purchase fails. An empty market says «Призы скоро появятся».
- The rating shows the top list with level and badge icons; my own row in the list stands out by colour and the word «Вы»; outside the list I see a card «Вы на 37-м месте · 120 баллов» under it (place and points only, no name, level or badges). It also shows «Итоги зафиксированы» when frozen, «В рейтинге пока никого нет» when empty and «Вас пока нет в рейтинге» when I'm unranked.
- The profile shows my level and «до следующего уровня N баллов», coins (a negative balance in red), points, every badge (earned in colour, the rest greyed with their condition) and my history, where a purchase shows the prize name, «Покупка в маркете» and «−30 монет», as today; an empty history says «Здесь появятся выполненные задания».
- The level and badge moment closes with its «Отлично» button or with Escape.
- Badge tiles tell screen readers «получен» or «не получен», not only by colour.
- The phone rules from piece 23 hold on every screen here.

## What's out

- Guest arrival and tasks (piece 23), staff and hall (piece 25), admin (piece 26)
- Any change to quiz rules, prices, rating order, levels or badge conditions
- Name, level or badges on the «Вы на …-м месте» card (the Rating artboard draws them; the API doesn't send them)
- Badges set by admin (piece 20) and the blitz speed bonus (piece 17): they come after this piece, in the Console look (piece 23's Decisions: order)
- Badge artwork beyond the design system's pixel icons

## How to check it

- When I start a quiz, then I see «Вопрос 1 из N», the question, its 2–4 answers as lettered buttons and the countdown, like the Quiz artboard.
- When the quiz has 10 seconds or less left, then the timer is red and says «Мало времени».
- When time runs out, then I see «Время вышло» and the result «3 из 5» with its points and coins.
- When I open a quiz before checking in, then I see one message card with a lock and «Сначала отметьтесь в зале».
- When I open /market with 48 coins and a 60-coin prize, then its card has a greyed-out «Не хватает 12 монет» that can't be tapped.
- When I buy a prize, then I confirm it in the card and then see its QR and code; when the stand issues it, the card says «Получено».
- When the market is closed, then I see «Маркет откроется в …» and every «Обменять» is locked.
- When I'm 37th in the rating, then I see the top list and under it a card «Вы на 37-м месте · …».
- When the results are frozen, then the rating shows «Итоги зафиксированы» above the list.
- When I open /app/profile, then I see every badge, earned ones in colour and the rest greyed with their condition.
- When I've bought a 30-coin prize, then my history shows «−30 монет» with one minus sign.
- When I level up, then on /app I see the full-screen moment, and «Отлично» or Escape closes it.
- When I'm in the top list, then my row says «Вы».
- When I open each screen here at 320 px wide, then nothing scrolls sideways.

## Size

Screens: 5

- /app/quiz/:id
- /market
- /app/rating
- /app/profile
- level and badge moment (full screen over /app)

Endpoints: 0

Tables: 0

## Decisions

- Settled with approval, 2026-11-03: new language-file keys «Мало времени» (quiz timer), «Вы» (my row in the rating), «получен» and «не получен» (badge tiles, for screen readers). Each says in words what colour alone said before.
- Settled with approval, 2026-11-03: the level and badge moment also closes with Escape, as the design system's moment does.
