# Contract: Console look: guest arrival and tasks
Status: on-dev
Base: fb34fa6901
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be6081a88e28f744515bf9d0

CHANGE to: 001, 002, 003, 005, 008, 009 (look only, behaviour stays)
Needs: piece 12. Built before 13–22 (Order 12.1).
Owner's words: «Make it in the style of Atari 80 gaming console. Admin is desktop and mobile, user is mobile. Mobile is website app. Optimised for iphone and android, all major browsers.», from chat 2026-11-02

Owner's words: «Build it in the app», from chat 2026-11-02

Owner's words: «decide yourself» (order, icons, row placement below), from chat 2026-11-03

Design: Gamify Console design system · guest screens

## What users see

- The guest screens in this piece have the Console look: a dark ribbed-plastic background, the red, orange and amber stripe under the screen title, square buttons with hard shadows, and numbers on glowing screen panels.
- Text uses Press Start 2P for titles, Pixelify Sans for numbers, Exo 2 for reading text and JetBrains Mono for codes, all with Cyrillic. The font files ship with the app (not Google Fonts), so they also show when /app is opened with no network.
- /app/welcome: first the full privacy text with «OK» in the welcome card, then the greeting with the arrival points and «К заданиям». No extra caption under the greeting (the Welcome artboard's caption is not built).
- /app: the stage-change banner, the wallet with level and «до следующего уровня N баллов», the market and rating rows where they are today (under the wallet, above the tasks), the stage bar, the task cards, «Игра начнётся в …» / «Игра завершена» and the empty-stage text.
- /app/tasks/:id keeps every way of doing a task, in the Console look: the QR and market hints as strips (with «В маркет»), the link button with «Я зарегистрировался» and «Подтвердить», quiz «Начать», «Сначала отметьтесь в зале» as a locked strip and «Выполнено — посмотреть результат», the disabled «Выполнить — скоро», the text box with its 0 / 500 counter, and the retake and penalty notes as coloured strips.
- On a photo task the photo I picked shows in the photo frame, the frame shows «Загрузка…» while the photo is prepared, and «Не получилось открыть фото. Выберите другое.» is a red strip. There is no empty frame before a pick, and no «Снимите фото прямо сейчас…» strip (both are only on the Task artboard).
- After scanning a task QR (/q/:code), confirming a link task or sending a photo or text, the result is one result card: big «+N баллов» and «+N монет», or «Уже выполнено» / «Это задание сейчас недоступно» / «QR-код не найден», then «К заданиям».
- Icons on these screens are the design system's pixel icons (drawn in the app, no new package) in place of lucide-react, always beside a word. Screens not yet in the Console look keep lucide until their piece.
- Loading is the pixel spinner with «Загрузка…»; every empty, error or not-found state is one message card; inline problems (offline, upload refused) are a coloured strip with an icon.
- On iPhone Safari and Android Chrome, from 320 to 448 px wide: every tap target is at least 48 px, typing in a field doesn't zoom the page, nothing sits under the notch or the home bar, and nothing scrolls sideways.
- The phone's browser bar and the page behind the screen are the dark ground, also when the page is pulled past its end; the tab shows a pixel icon.
- Keyboard focus shows a thick ring around the control.
- With reduced motion turned on in the phone settings, nothing glows, flickers or slides.
- All text keeps a contrast of at least 4.5:1.
- Staff, admin, quiz, market, rating and profile screens keep today's look until pieces 24–26: the Console fonts, colours and shell apply only to /app/welcome, /app, /app/tasks/:id and /q/:code.

## What's out

- The other screens: quizzes and rewards (piece 24), staff and hall (piece 25), admin (piece 26)
- Any change to what a screen does, its data or its endpoints
- The «На проверке», «Не отправлено» and «Скоро» chips on task cards
- What pieces 14–17 and 19 add to the feed, the stage bar or the task page (upload states, card states and the per-task limit, multipliers, speed bonus, push prompt): those pieces come after this one and build their additions in the Console look
- A light theme for guests
- A page for unknown addresses: they stay blank as today

## How to check it

- When I open my badge link for the first time, then I see the privacy text and «OK» in the welcome card, and after «OK» the greeting with my arrival points.
- When I open /app on an iPhone, then I see the wallet, the market and rating rows, the stage bar and the task cards with their type tags, in that order.
- When I tap a text field on an iPhone, then the page doesn't zoom in.
- When I open /app on an iPhone with a notch, then the wallet at the top and the last card at the bottom are clear of the notch and the home bar.
- When I pull /app past its top in iPhone Safari, then I see dark ground, not white, and the browser bar is dark.
- When I open /app/welcome, /app, /app/tasks/:id and /q/:code at 320 px wide, then nothing scrolls sideways and every button can be tapped.
- When I open the feed in Android Chrome, iPhone Safari, and desktop Chrome, Safari, Firefox and Edge, then each shows the pixel title font, Cyrillic text in Exo 2, the pixel numbers and the stripe, with nothing overlapping.
- When I scan a task QR I haven't done, then I see the result card with the points and coins in pixel numbers and «К заданиям»; when I scan it again, I see «Уже выполнено».
- When a photo upload is refused (for example, too large), then I see a red strip with an icon and the reason, and I can pick another photo and send it.
- When I open a task that doesn't exist, then I see one message card with a way back to the tasks.
- When I open /app once, then turn the network off and reload, then the titles, numbers and text still show in the Console fonts, not system fonts.
- When I open /app and look at the network panel, then no font is loaded from fonts.googleapis.com or fonts.gstatic.com.
- When I turn on reduced motion, then nothing glows, flickers or slides.
- When I check the text colours on these screens with a contrast checker, then every pair is at least 4.5:1.
- When I open /desk, /admin/live and /market after this piece, then they look exactly as before.

## Size

Screens: 4

- /app/welcome
- /app
- /app/tasks/:id
- /q/:code

Endpoints: 0

Tables: 0

## Decisions

- Decided 2026-11-03 (Manu: «decide yourself»): order is piece 12, then 23–26 (Order 12.1–12.4), then 13–22, then 27, so 13–22 are built in the Console look and nothing is re-skinned twice. Order only counts among Ready pieces: until 23–26 are approved, the next pickup is still 13.
- Decided 2026-11-03: the design system's pixel icons in place of lucide-react. Piece 26 removes lucide-react once no screen uses it.
- Decided by Manu, chat 2026-11-03 («agree», with piece 27): font files shipped with the app, not Google Fonts.
- Decided 2026-11-03: the market and rating rows stay above the tasks, as today (this piece changes look, not layout). Moving them below the list is its own backlog row.
- New language-file keys: none. These screens use only words already in ru.json.
- Later: the skin selector is piece 27 (Skin choice for the event).
