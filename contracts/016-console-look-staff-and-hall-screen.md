# Contract: Console look: staff and hall screen
Status: on-dev
Base: 4c2625fb42
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be60813b8966ed6676ecd0a2

CHANGE to: 001, 004, 006, 007, 009, 011 (look only, behaviour stays)
Needs: piece 23
Owner's words: «Make it in the style of Atari 80 gaming console. Admin is desktop and mobile, user is mobile. Mobile is website app. Optimised for iphone and android, all major browsers.», from chat 2026-11-02

Owner's words: «Build it in the app», from chat 2026-11-02

Design: Gamify Console design system · staff and hall screens

## What users see

- /desk, /stand/:code and /moderate use the light Label version of the look (cream plastic, the same stripe and type), built for a phone held standing up, like the staff canvas artboards.
- The PIN and password login card is the same on every staff and admin page: the role title, «PIN-код» (or «Пароль» on /admin/guests) and «Войти», with «Неверный PIN-код или пароль» under the field after a wrong try. No line above the card (the artboard's «ФОРУМ · ПЕРСОНАЛ» is not built).
- At the desk: search results as tappable rows, «Никого не нашли» when nothing matches, the guest's QR on a card, and the walk-in form.
- At the stand: the partner, the prize and «Гость: …», then a full-width «Выдано» button; after it «Приз выдан» in green, or «Уже выдано в 14:32» in red if it was given before, each with an icon and the words. An unknown code shows one message card «Код не найден».
- In moderation: a header with my name, as today (the artboard's «МОДЕРАЦИЯ» line is not built), two screen panels «Ждут проверки» (the count) and «Самая старая ждёт» («N мин», or «меньше минуты» under a minute; left out when nothing waits), and the «Топ-20» box. Then the cards in 1, 2 or 3 columns by width; the penalty button is red and spelled out; a card someone else already checked shows «Уже проверено: …» as a strip; an empty queue shows «Очередь пуста».
- /hall is the dark board in a woodgrain frame: «Форум», «Топ-10» and huge pixel numbers, like the Hall artboards but without the clock. «Итоги зафиксированы» and «Нет связи — показан последний рейтинг» show under the stripe.
- The browser bar is light on the staff pages and dark on /hall.
- The phone rules from piece 23 hold on /desk, /stand/:code and /moderate.

## What's out

- Admin pages (piece 26), apart from the shared login card
- A clock on /hall (the app has none; the artboard's 14:30 is not built)
- A warning colour on «Самая старая ждёт»: the panel keeps the plain look at any age (the artboard's amber «14 мин» is not built)
- Piece 18's «Эфир» and logo slides: see piece 23's Open items: order
- Any change to what the staff pages do

## How to check it

- When I log in at /desk with the PIN on a phone, then I see the search like the Desk artboards.
- When I search «Кари», then I see matching guests as rows, and tapping one shows their QR on a card; when nobody matches, I see «Никого не нашли».
- When I open a prize code at /stand that was already issued, then I see «Уже выдано в …» in red with an icon.
- When I open /stand with a code that doesn't exist, then I see one card «Код не найден».
- When I enter Moderator 2's PIN at /moderate, then I see «Модератор 2» in the header next to «Ждут проверки» on a screen panel.
- When I open /moderate at 1024 px wide or more, then I see three columns of cards; from 768 px, two; on a phone, one.
- When I open /hall on a 1920×1080 screen, then all ten names, levels and points show on one screen without scrolling, in the pixel number font, like the Hall artboard.
- When the network drops, then /hall keeps the last top 10 and shows «Нет связи — показан последний рейтинг».
- When I open /admin/guests, then I see the same login card with «Пароль».
- When I open /desk, /stand/:code and /moderate at 320 px wide, then nothing scrolls sideways.

## Size

Screens: 4

- /desk
- /stand/:code
- /moderate
- /hall

Endpoints: 0

Tables: 0

## Decisions

- Settled by the order decided in piece 23 (2026-11-03): piece 18 comes after this one, so it builds its «Эфир» and logo slides in the dark hall look itself.
- New language-file keys: none.
