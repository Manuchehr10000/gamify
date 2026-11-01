# Contract: Prize market
Status: done
Base: f5d005deb6
Approved: 2026-11-01 by Manu
Tracker: https://app.notion.com/p/40bc62b4be6081ba9c05c76a43a67af0

Client's words (TAG): «Экран «Партнёрский маркет»: список призов от партнёров с ценой в монетах и остатком количества; обмен — одна кнопка, подтверждение, инструкция «подойдите к стенду партнёра X, покажите этот экран», QR/код погашения, чтобы стенд отметил выдачу и не выдал приз повторно по тому же коду.», from backlog, added 2026-11-01

Client's words (TAG): «Открывается с начала этапа 3 (конфигурируется по времени в админке).», from backlog, added 2026-11-01

Client's words (TAG): «CRUD по призам «Партнёрского маркета» (название, партнёр, цена в монетах, остаток).», from backlog, added 2026-11-01

Client's words (TAG): «Действие — Обменять баллы на монеты в «Партнёрском маркете» — 15», from backlog, added 2026-11-01

## What users see

- From the feed, a guest opens /market: each prize shows its name, partner, price in coins and «осталось N».
- Before the market opens, the list shows but the buttons are locked, with «Маркет откроется в 14:00» (the start time of the first stage marked «Маркет» in the file).
- Once it's open, the guest taps «Обменять», confirms, and the coins are taken from their total.
- After the exchange, the prize shows «Подойдите к стенду партнёра X, покажите этот экран», with a QR and a short code. This stays in /market until the prize is handed over.
- A guest can buy each prize once. A bought prize shows «Получено» after hand-over.
- With too few coins, the button reads «Не хватает N монет». With none left, the prize shows «Закончились».
- Stand staff scan the guest's QR with their phone camera. /stand/{code} asks for the stand PIN once, then shows the prize, the partner and the guest's first name, with a «Выдано» button.
- Scanning a code that was already given shows «Уже выдано» and the time. A wrong code shows «Код не найден».
- The admin adds a «Призы» sheet to the Excel file: ID, name, partner, price in coins, quantity. They mark «Маркет» = да on the stage where the market opens. Downloading the file gives these back.
- A task with «Выполнение» = Маркет is completed by the guest's first purchase: its points and coins are added and the card shows «Выполнено».

## What's out

- One PIN per partner; checking that a stand only gives out its own prizes
- Partner reports and counts per partner
- Cancelling a purchase, refunds, and expiry of prizes nobody picked up
- Prize photos; an admin screen for editing prizes (the Excel file only)
- The push message when the market opens; the profile and purchase history screens
- The three main prizes (laptops, by ranking): those belong to the leaderboard
- Spending points: only coins are spent

## How to check it

- When I upload the file with a «Призы» sheet of 3 prizes, then /market shows all 3 with price and «осталось N».
- When I open /market during stage 2, then I see the list with locked buttons and «Маркет откроется в 14:00».
- When I tap «Обменять» during stage 3 with enough coins and confirm, then my coins go down by the price and I see the stand instruction with a QR and a code.
- When I try to buy the same prize again, then I can't.
- When I have 20 coins and a prize costs 30, then the button reads «Не хватает 10 монет».
- When two guests buy the last item at the same moment, then one gets it, the other sees «Закончились», and their coins are not taken.
- When stand staff scan my QR and enter the PIN, then they see my prize and first name, and after «Выдано» my screen shows «Получено».
- When they scan the same QR again, then they see «Уже выдано» with the time.
- When I open /stand/{code} without the PIN, then I see only the PIN prompt.
- When the market task is set to «Маркет» and I make my first purchase, then I get its 15 points and coins once, and the card shows «Выполнено».
- When the admin uploads the file again with a changed quantity, then purchases already made stay valid and «осталось» updates.

## Size

Screens: 2

- /market
- /stand/{code}

Endpoints: 4

- GET /api/market
- POST /api/market/{id}/buy
- GET /api/stand/{code}
- POST /api/stand/{code}/issue

Tables: 2

- prizes
- redemptions
