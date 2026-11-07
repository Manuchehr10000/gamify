# Test run on dev: results so far (2026-11-07)

Dev: https://gamify-dev.manuchehr-407.workers.dev. `/api/version` = 11, skin «Стимпанк». Last Deploy on `dev` is green (028).

The first table is from before the admin sign-in; everything after "After admin sign-in" ran with the owner signed in.

**Main findings (most important first):**
1. Dev's backend container drops requests now and then: HTTP 500 «Container suddenly disconnected, try again». Guests then see «Что-то пошло не так». I hit it 4 times in about 90 minutes.
2. A1: the admin lock card says «Список гостей», not «Администратор». The local 016 fix isn't deployed.
3. Result cards disagree at a multiplier: QR, link and photo show base points; quizzes show multiplied points.
4. The tasks file silently changed a partner's package (Нур Диджитал Нас поддерживают → MF Партнёр); the preview never mentions partner changes.
5. A future-stage task page shows an active «Выполнить»; «Этап закрыт» only comes back after the guest picks a photo.
6. Multi-day stages show times without dates («18:00–18:00», «до 18:00»), and «Закроется через 3757 мин».
7. Minor: «Журнал» shows packages as raw codes (general/supporters); settings number fields have no label tied to them; /admin/settings lists stay tables on phones.

| Step | Result | Notes |
|---|---|---|
| A1 Admin sign-in | **Partial / 1 fail** | Wrong password → «Неверный PIN-код или пароль» ✓. «Войти» disabled while empty ✓. **Fail:** the lock card heading on /admin/tasks is «Список гостей», not «Администратор». The local uncommitted 016 fix isn't deployed. Correct password not run (needs owner). |
| A2 401 without token | Pass (API) | `/api/admin/live`, `/api/admin/settings`, `/api/admin/partners/99999/report` with no or a bogus token → 401 `not_logged_in`. |
| A3–A16, A18–A21 | Not run | Needs admin. |
| A17 Hall | Partial | /hall at 1920×1080: «Эфир» mode, Top-10, no scroll ✓. `POST /api/hall/mode` without a token → 401 ✓. Mode buttons need admin. |
| B1 Signed-out unknown address | Pass | `/` and `/nothing-here` → /app with «Бейдж не найден — подойдите к стойке регистрации». History replaced. |
| B2 Arrival by badge link | Pass (repeat arrival) | Guest A (already arrived): `#token` removed, «Здравствуйте, Фаррух!», «+10 за то, что пришли на форум», wallet stays 10. Changed code → /app/welcome?error=badge + badge message ✓. First-arrival consent not run (would use a new guest). |
| B4 Signed-in home address | Pass | `/` and `/nothing-here` → /app feed. |
| B9 Try | Partial | /q/ with no code → /app ✓. Scan while signed out → badge message ✓. |
| B16 Try | Pass | /app/quiz/99999 → «Квиз не найден». |
| B19 Rating | Partial | Rating lists 3 guests, own row «Вы» ✓. Freeze etc. need admin. |
| B20 Try | Pass | /market without guest token → badge message. Signed in: «Маркет скоро откроется» (no stages). |
| B23 Edge cases | Partial | /app/tasks/999999 → «Задание не найдено» + «К заданиям» ✓. /app, /app/rating, /app/profile, /market, /app/welcome, /app/quiz at 320 px: no sideways scroll ✓. Only the skin's own fonts load, nothing from fonts.googleapis.com / gstatic ✓. |
| C2 Photo link | Partial | `/api/photos/abc` → 404 `photo_not_found` ✓. |
| C4 Jobs | Pass (dev part) | `POST /api/jobs/run` → 404 on dev ✓. |
| Everything else | Not run | Needs admin (and staff PINs set in «Доступ»). |

## After admin sign-in

| Step | Result | Notes |
|---|---|---|
| A1 | Pass (except heading) | All admin pages open without a second login. /admin/settings has the 11 tabs, «Задания» open by default. |
| A3 Staff | Pass (2 checks skipped) | 3-char PIN, empty PIN, duplicate PIN and second desk give the exact messages. New moderator signs in. After a PIN change the old PIN gets 401 and the new one works. Switched off: the session ends and sign-in is refused. «Журнал» shows «••••». **Skipped:** «Удалить» on the desk and the last admin (a failed refusal would delete real dev accounts). **Intermittent:** one second-desk save returned HTTP 500 and the UI showed «Что-то пошло не так»; 5 retries gave the correct 400. **Dev change:** there was no «Стенды партнёров» account, so I added one. New test PINs were set for the moderator «Тест Модератор», the desk and the stand (not written here). |
| A4 Partners | Pass | Added «Памир Медиа» (Генеральный). Renamed `chinor-print` → «Чинор Принт» (Нас поддерживают). Duplicate name, SVG, GIF and >1 MB give the exact messages. Logo upload shows a thumbnail, and «Журнал» logs «Логотип»: загружен (I used a generated PNG, not the kit file). **Minor:** «Журнал» shows packages as raw codes (`general` → `supporters`). |
| A5 Settings | Pass (two-tab conflict not run) | 5000 and 10.5 → «допустимо от 0 до 1000». 10 → «Сохранено». Photo date 3 days ahead → the 7-day message. Arrival = 10, partner multiplier = 1.5 (as the kit needs). **Minor a11y:** settings number inputs have no label tied to them. |
| A6 Skin | Pass | «Сохранить» is disabled for the current skin. The dialog text matches. Cancel changes nothing (version stays). OK → `/api/version` skin=console, and an open tab switched fonts within 10 s with no reload. Dev is now on «Консоль». |
| A7 Push | Pass | Switch is on, the hint matches, an empty text → «от 1 до 200 символов». |
| A8 Tasks file | Pass | The preview lists 3 stages, 25 tasks and 3 prizes. «Отмена» changes nothing. «Применить» → «Добавлено заданий: 25 … Этапы: добавлено 3 … Призы: добавлено 3». Re-uploading the export → «Файл совпадает…», «Применить» disabled. A8-01 → «В файле нет: Этапы, Задания». The file created «Сомон Аналитикс» (Хедлайнер). **Findings:** (1) the file changed «Нур Диджитал» from Нас поддерживают → MF Партнёр, and the preview never mentioned it; (2) the stage card shows the 4-day stage 1 as «18:00–18:00», with no dates. A8-02…26 were not re-run on dev (the kit says they passed the same importer). |

| A9 Multiplier | Pass (API) | 1.3 and 6 → `bad_multiplier` («Множитель: от 1 до 5 с шагом 0,5»). «Карточек в ленте» 3 → out_of_range 5–50. End before start → `end_before_start`. Stage 1 is now ×2. |
| A10 Next stage | Pass | Question «Начать следующий этап прямо сейчас? … сейчас 1, станет 2». «Отмена» changes nothing. |
| A11 Blitz setup | Pass (API) | QZ-BLITZ: blitz=да, 20/3/12. Blitz on a photo task → `quiz_only`. 12/12 → `bad_speed_window`. The lock during a running blitz comes in B17. |
| A12 Badges | Pass (API) | Missing «Число», missing «Тип задания» for «Все задания типа», missing task for «Первые N», partner + «Любой один партнёр», unknown kind → all refused with the right codes. Set up: Фотоохотник count 1, any partner (the dev pollution is cleared); Эрудит quiz streak 2; new «Первое селфи» (Первые N=1, PH-SELFIE), «Чемпион» (Место 1), «Старт» (Задания 1, 20 coins, on screen). The confirm-dialog wording wasn't checked (set via API). |
| A13 List editing | Pass (API) | Points 20000 → out_of_range 0–10000. Switching off QR-HALL → `required_by`. Second save with an old version → `stale`. Deleting the 0-point level → `zero_level`. |
| A15 Guest list | Pass | The same guests.csv → «Изменений нет», «Применить» disabled. No-ID file → «В файле нет столбцов: ID регистрации». Bad rows → red strip plus rows 3 «нет ID регистрации», 4 «нет имени», 5 «этот ID регистрации уже есть выше в файле». |
| A16 QR sheet | Pass | 4 cards, «QR-ENTRY · этап 1» etc. The hint names the dev host. |
| A17 Hall | Pass | live/logos/pause/auto all switch (/api/hall reports the mode). A bad mode → 422. A guest token → 401. The auto cycle shows Топ-10 → «Партнёры форума» (3 logos) → «До открытия маркета 86:38:22». Logo settings: General size 3 on every slide, MF size 2 every 2nd, Supporters size 1 every 3rd. |
| A2, A18, A19 | Pass | /admin/live: the header actions, the partner drop-down (report button disabled until one is picked), 7 tiles (3 / 0 / 0 / — / 0 / 0 / 54), push card at 0, «Пока ничего не выполнено», stage table with 0s. «Проверить баланс» → «Расхождений нет». A guest token on /api/admin/live → 401. |
| A20 Change log | Pass | change-log.xlsx downloads (200, xlsx). A date filter in the future → empty. |
| A21 Phone | Pass | /admin/live, /admin/tasks, /admin/guests and /admin/settings at 320 px: no sideways scroll. **Note:** /admin/settings lists stay tables, not cards. |
| A14 | Pass (setting) | Multiplier is 1.5; the coins are checked on the guest side (PH-PARTNER 23). |

## Part B (guest, staff)

| Step | Result | Notes |
|---|---|---|
| B5 Feed | Pass | Wallet, «Партнёрский маркет», «Рейтинг», stage bar with «×2», cards with ×2. Order: window quiz → Памир (General) → Сомон (Headliner) → Нур (MF) → Чинор (Supporters). PH-PARTNER 23 coins, QZ-PARTNER 38. **Minor:** «Закроется через 3757 мин»; the stage bar says «до 18:00» on a 4-day stage, with no date. |
| B8 Rotation | Pass | 4 loads: 71+51–55, 71+56–59, 71+60–64, 71+67–72. The window quiz stays pinned and counts toward the 5. |
| B9 QR | Pass | «+15 баллов», «+15 монет» (wallet +30 at ×2: the known base-vs-multiplied open question). Second scan «Уже выполнено». QR-LIMIT after guest B → «Лимит исчерпан», task page «Временно недоступно». Raising «Лимит» to 2 → the page shows the scan strip and A's scan pays. QR-PAST → «Это задание сейчас недоступно». Bad code → «QR-код не найден». |
| B10 Link | Pass | The tick and «Подтвердить» appear only after «Выполнить» (link https://mktb.pro). «Подтвердить» is disabled until ticked. Result «+5 баллов», «+5 монет». NET-SOON → disabled «Выполнить — скоро». |
| B11 Photo | Pass / 1 finding | Non-image → «Не получилось открыть фото. Выберите другое.» «Загрузка…» → preview with «Отправить»/«Переснять» → «+10 баллов», «+10 монет», state «На проверке». **Finding:** stage-2 task PH-AFTER opens with an active «Выполнить». «Этап закрыт» (`stage_closed`) only comes back after the guest has picked a photo. |
| B12 Moderation | Pass | Desk PIN → 401. Header with the moderator's name, «Ждут проверки 8», «Самая старая ждёт 3 мин», newest first, «Нигина Р.», «отправлено в HH:MM». «Принять»: totals unchanged. «Бонус +50%» on the 35-pt photo at ×2: +35 points, coins unchanged. «Бонус +50%» on Крейзи → «Дух форума» badge. «переснять» on DOOH: −30/−15, task back to available/retake. «штраф» on PH-LIMIT: −20/−10, state penalty, and the limited slot frees for guest A. Two moderators at once: the second gets `already` with the first one's name, and totals change once. |
| B13 Withdraw | Pass | The question text matches, «Отмена» keeps the photo, «Подтвердить» → «Фото удалено — задание снято», −20/−10. The photo badges were removed quietly. |
| B18 Moments | Pass (part) | After crossing 50 points: «Новый уровень: Участник», then «Новый бейдж: Фотоохотник», «Первое селфи», «Старт», each with «Отлично». Escape closes them, and none show again after a reload. |

| B2 First arrival | Pass | Walk-in link: consent text exact, «OK» → «Здравствуйте, Тестовый!», «+10 за то, что пришли на форум», wallet 10. |
| B3 Desk | Pass | Moderator PIN at /desk refused. Desk PIN → search and «Добавить гостя». 1 letter → nothing. «Нигина», «нигина рахимова», «рахимова НИГИНА» → one row «Рахимова Нигина», «Банк «Сарвари» · 992901000002». «992901» → all guests sorted by last name. Nonsense → «Никого не нашли». Empty walk-in → browser validation blocks (Имя, Телефон required). Walk-in «Тестовый Гость» → QR card «Наведите камеру телефона на код». Found at the desk and in guests.csv with an empty «ID регистрации». |
| B6 Stage change | Pass (stage 2) | «Подтвердить» → within ~3 s the open feed showed «Новый этап: День: маркет открыт — очки ×2» plus the stage message. The stage card now reads 03:46–19:00. Stage 3 / «Игра завершена» not run (it would close the market on dev). |
| B7 Multiplier | Pass | At ×2: LINK 5 → wallet +10; 1 of 3 on the 10-pt quiz → «+8 баллов, +4 монеты»; bonus on a 35-pt photo → +35. The multiplier was set back to 1 on stage 1. **Finding:** result cards disagree. QR/link/photo cards show base points («+15 баллов» while the wallet gets 30), but quiz results show multiplied points («3 из 5 · +60 баллов»). |
| B14 Text, photo+text | Pass | Spaces only → «Отправить» disabled. maxLength 500, counter «N / 500», font 16 px (no iOS zoom). Text → «+10 баллов, +15 монет». Photo+text: no «Отправить» until a photo is chosen; then «Загружается» → «+20 баллов, +20 монет» (~15 s upload). |
| B15 Offline | Not run | The browser pane can't switch the network offline. |
| B16 Quizzes | Pass | «Квиз», «Осталось 00:57», «Вопрос 1 из 5», A–D. 3 of 5 → «3 из 5 · +60 баллов, +30 монет» (×2), task page «Выполнено — посмотреть результат». After a reload the time continues and the answer order is the same. «Мало времени» at 00:06, then «Время вышло» with the score. Partner quiz «2 из 2 · +50 баллов, +38 монет». QZ-HALL before the check-in: «Сначала отметьтесь в зале», no «Начать»; after scanning QR-HALL «Начать» appears; 3 of 3. Two perfect quizzes in a row → «Эрудит». One answer hit «Что-то пошло не так» (container drop); a reload recovered it. |
| B17 Blitz | Pass | «4 из 5 · +80 баллов, +40 монет · +84 за скорость» (×2; Q5 was answered late at ~6.5 s, so 20+10+0+12 base). Profile row p80 / c40 / bonus 84. A11 lock: saving QZ-BLITZ during the run → 409 `quiz_running` («Нельзя менять во время блица»). |
| B18 Badges | Pass | Levels and badge moments in order, once. Withdrawal removed the photo badges quietly. «Чемпион» (Место 1) was given on freeze. |
| B19 Rating | Pass | «Вы» row; «Итоги зафиксированы» on the guest page and /hall (frozen=true). Admin table Место / ФИО / Компания / Баллы. Unfreeze works. MF-012 (В рейтинге = нет, 25 pts) is on neither /app/rating nor /hall, while a 10-pt guest is. |
| B20 Market, stand | Pass | 242 coins, «осталось», «Не хватает 658 монет». Confirm «Обменять 30 монет на «Блокнот форума»?». After buying: QR + «Код: EZRGF6» and «Подойдите к стенду партнёра Чинор Принт…». The «Маркет» task paid once (+10 coins). Last-item race: one 200, the other 409 `sold_out` with coins kept. Stand: wrong PIN message, «Гость: Фаррух», «Выдано» → «Приз выдан», reopen «Уже выдано в 03:48», unknown code 404, second issue `already`. Guest: «Получено», profile rows −30 / −40. |
| B21 Push | Partial | The schedule has the generated rows (stage, market, quiz_before/open); the stage push is titled «… — очки ×2». A non-one-off → `one_off_only`; editing a sent push → `push_done`; deleting a stage push → `source_push`. A one-off «Отправить сейчас» → sent (0 subscribers); /hall in auto carries it. Phone opt-in, delivery and the iPhone guide not run (needs real devices). |
| B22 Live after activity | Pass | Signed in 5, active 2 (correct for the 15-min window), bought 2, issued 1, left 52; partner table and stage table filled. |
| B23 Edge, staff layout | Pass | /desk, /stand, /moderate at 320 px: no sideways scroll. /moderate grid: 2 columns at 768 px, 3 at 1100 px. |

## Part C

| Step | Result | Notes |
|---|---|---|
| C1 Partner reports | Pass | partners.csv: semicolon separated, Cyrillic intact, header «Партнёр;Пакет;Задание;Выполнений;Уникальных участников». Памир report (saved as partner-3.xlsx) has sheets «Сводка» (with «Предварительные данные…», «Ссылки на фото работают до 10.12.2026», tasks/prizes/logo shows 4×35 s/push), «Детали» (per hour), «Фото» (only the accepted photo, link /api/photos/…, no guest names). Partner 99999 → 404 `partner_not_found`. |
| C2 Photo link | Pass (no real GPS file) | The link opens without login as image/jpeg with no EXIF segment. A 4000×3000 photo sent through the UI is stored as 1600×1200. The server refuses a raw >1600 px upload with `photo_too_large`, so resizing happens on the phone. The kit's 6 MB GPS photo was not used (too large to inject). |
| C3 Balance | Pass | «Расхождений нет» after awards, bonuses, retake, penalty, withdrawal and purchases. |
| C4 | Pass (dev part) | /api/jobs/run → 404 on dev. |

**Infra finding:** dev sometimes answers HTTP 500 with the body «Container suddenly disconnected, try again» (Cloudflare container). I hit it 3 times in about an hour (staff save, a tasks list read, a task read). The app then shows «Что-то пошло не так».

## Notes on dev state
- Dev was used before: partners «chinor-print» and «Нур Диджитал» already exist, and seeded badge «Фотоохотник» was edited to «5 заданий партнёра chinor-print». A4 must create «Памир Медиа» and «Чинор Принт» by exact name, or the tasks file will create new partners next to «chinor-print».
- Hall mode on dev is «Эфир» (live), left from an earlier run.
- Guests MF-001…MF-012 are already imported. 3 have arrived (10 points each).

## What this run changed on dev (state left behind)
- Skin is «Консоль» (it was «Стимпанк»).
- tasks.xlsx applied (3 stages, 25 tasks, 3 prizes). **Stage 2 «День: маркет открыт» is running now** (started by hand), so the market is open and stage-1 tasks are closed.
- Partners: «chinor-print» was renamed to «Чинор Принт» (Нас поддерживают), «Памир Медиа» added with a generated logo, «Сомон Аналитикс» created by the file, «Нур Диджитал» moved to MF Партнёр by the file.
- Staff: new moderator «Тест Модератор», new «Стенды партнёров» account; desk PIN changed. The PINs are test values; ask me or reset them in «Доступ».
- Badges: Фотоохотник → 1 with any partner, Эрудит → 2, added «Первое селфи», «Чемпион», «Старт» (20 coins, on screen).
- QR-LIMIT «Лимит» = 2. Hall mode = Авто. Walk-in guest «Тестовый Гость» created. Guests A, B, MF-003, MF-012 and the walk-in have activity; 2 photos still wait in moderation.
- One-off push «Тест QA» sent (0 subscribers).

## Skipped or not possible here
- A3 delete refusals for the desk account and the last admin (blocked: a wrong outcome would delete real dev accounts).
- A5 two-tab conflict in the UI (the API `stale` check passed in A13).
- A8-02…A8-26 negative files on dev (only A8-01 run).
- B15 offline, B21 phone push, iPhone notch, reduced motion, B6 stage 3.
- C2 with the real 6 MB GPS photo; C4 job runs (local only).

## How uploads were done
The browser pane has no file picker, and the page can't fetch from localhost. Kit files are injected into the page's file inputs (small files as embedded data; the >1 MB logo is generated in the page). The 6 MB GPS photo (C2) is too large for this. A downscaled copy that keeps its GPS EXIF can stand in for the EXIF/1600 px check.
