# Manual test scenario: Event Gamification

You test the dev deploy, https://gamify-dev.manuchehr-407.workers.dev, in this order: **first as admin, then as a guest**. Where the guest flow needs a staff role (desk, moderator, stand, hall screen), a **↔ Switch to <role>** step tells you what to do there. After it, a **back to guest** line says what the guest should now see.

Every step title ends with its contract number in brackets, for example [013]. UI labels are quoted exactly as the app shows them, in «…».

---

## Before you start

### Where you test
- **Everything runs on the dev deploy: https://gamify-dev.manuchehr-407.workers.dev** (below: `<DEV>`). Nothing runs locally.
- The app and the API share this address: `<DEV>/app`, `<DEV>/admin/...`, `<DEV>/api/...`, and badge links `<DEV>/b/<code>`.
- Before you start, check that the last Deploy job on `dev` in GitHub Actions is green, and that `<DEV>/api/version` answers.
- It is a production build, so push notifications and background photo upload work here (iPhone push needs the app added to the home screen).
- The data lives in the shared dev database on Neon. Your uploads (tasks file, guest list, settings) replace what is there for everyone who uses dev.

### Secrets
- They are set as GitHub environment secrets of `dev` (`ADMIN_PASSWORD`, `DESK_PIN`, `STAND_PIN`, `MODERATORS`, `JOBS_SECRET`, `VAPID_*`). Never write them in this file.
- The staff PINs and the admin password were read **once**, on the first start. After that they live hashed in the database: the live values may differ from the GitHub secrets if someone changed them in /admin/settings → «Доступ».
- If you only know the admin password: sign in as admin (A1) and set the desk, stand and moderator PINs in «Доступ» (A3).

### Devices
- A laptop for the admin (one browser profile).
- A phone, or a second browser profile or incognito window, for the guest. Use a second guest (another profile) for the limit, rating and race checks.
- More profiles or windows for /desk, /moderate, /stand and /hall (ideally /hall on a 1920x1080 screen).
- Badge and desk QR codes point at `<DEV>`, so a real phone can scan them directly.
- Staff pages have no logout button. To see the login card again, clear the site's localStorage (`admin_token`, `desk_token`, `moderator_token`, `stand_token`, `guest_token`).

### What dev can't do
- You can't edit the database by hand from the browser, and the job runner is not reachable from outside: `POST <DEV>/api/jobs/run` answers 404 on purpose. The jobs (lapsed photo claims, push sending, photo deletion) run by themselves every minute.
- So the checks marked **(local only)** below (edited balances in C3, forcing the photo-deletion job in C4) are skipped on dev.
- Migration 0019 seeds five badges: Фотоохотник, Нетворкер, Эрудит, Друг бренда, Дух форума. If dev was used before, they may have been edited.

### Files to prepare
- Logos: PNG or JPEG under 1 MB, plus one file over 1 MB and one .svg or .gif.
- The tasks .xlsx (you download the template in A8). Stage times are Dushanbe time (UTC+5), for example 13.12.2026 09:00. Put the current stage around now.
  - In the current stage:
    - three QR tasks: a plain one (B9), one with «Лимит» 1 (B9 Try), and a "hall check-in" one used only as the «Требует» of the gated quiz (B16);
    - one link task («Ссылка»);
    - at least 5 «Фото» tasks (B11, B12, B13 and B15 each use up one per guest: a guest can send each task only once), one «Текст», one «Фото+текст»;
    - one partner «Фото» task with 15 «Баллы» and blank «Монеты» (C1 and C2 need an accepted partner photo);
    - optional: one task with empty «Выполнение» (B10 Try);
    - at least 12 tasks in total, and «Карточек в ленте» = 5.
  - In the next stage: at least one «Фото» task (B11 Try «Этап закрыт»).
  - Quizzes («Выполнение» = Квиз): a 5-question quiz, 50 «Баллы», blank «Монеты», «Таймер, сек» 60; a partner quiz, 25 points, blank coins, 2 questions; a quiz with «Требует» = the ID of the hall check-in QR task; a quiz whose «Доступно с/до» window closes soon; a blitz («Блиц» = да, 5 questions, 50 points, 50 coins, timer 60, bonus fields blank).
  - «Вопросы» sheet with all questions. Write down the correct answers.
  - «Призы»: one expensive prize, one with «Количество» 1, one cheap prize.
  - A stage with «Маркет» = да, and at least one task in the next stage.
  - Optional: a task with «Выполнение» = Маркет.
- A guest list CSV with «ID регистрации», «Фамилия», «Имя», «Телефон», «Компания», «В рейтинге». Include one guest with «В рейтинге» = нет.

---

## Part A — Admin

> Tip: /admin/settings is not in the admin menu. Type the address by hand. It has no link back to the other admin pages.
> Order note: the stage, multiplier, blitz and badge steps need stages and tasks to exist, so the tasks file upload (A8) comes before them.

### A1. Admin sign-in [012, 016]
1. Open <DEV>/admin/tasks in a fresh browser profile.
2. You see the lock card «Администратор» with the field «Пароль» and the button «Войти».
3. Type a wrong password and press «Войти».
4. Type the admin password (the `ADMIN_PASSWORD` secret of `dev`, unless changed in «Доступ») and press «Войти».
5. Open /admin/guests, /admin/tasks/qr, /admin/live and /admin/settings in the same browser.

Expect:
- The page «Задания и этапы» opens. The menu shows «Живые цифры», «Задания и этапы», «Список гостей» and «QR-коды заданий».
- The other admin pages open without a second login.
- /admin/settings shows «Настройки игры» with the tabs «Этапы», «Задания», «Призы», «Вопросы», «Уровни», «Партнёры», «Доступ», «Push», «Бейджи», «Настройки», «Журнал». «Задания» is open by default.
- The card heading is «Администратор» on every admin page; the /admin/guests menu item and page title stay «Список гостей». [016, changed 2026-11-07]

Try:
- Wrong password: «Неверный PIN-код или пароль» under the field.
- «Войти» is disabled while the field is empty.
- The desk PIN typed here is refused with the same message.

### A2. Admin login on /admin/live [010, 016]
1. Clear `admin_token`, open /admin/live, and log in.

Expect:
- Title «Живые цифры» with «Живые цифры» highlighted in the menu. Header actions: «Скачать отчёт по партнёрам», the drop-down «Выберите партнёра», and «Отчёт партнёра (Excel)» (disabled until a partner is picked).
- A card «Экран в зале», 7 tiles, a card «Push-уведомления», three tables, and the balance card.

Try:
- `GET /api/admin/live` without an Authorization header, or with a guest or moderator token: 401 `{"detail":"not_logged_in"}`.

### A3. Staff accounts: «Доступ» [012, 013]
1. /admin/settings → «Доступ». Columns: «Имя», «Роль», «Включён». Rows: «Администратор», «Стойка регистрации», «Стенды партнёров», plus any seeded moderators.
2. Press «Добавить». Fill «Имя *», pick «Роль *» = «Модератор», type a 4-digit «PIN или пароль», leave «Включён» ticked, press «Сохранить». Write the PIN down: you need it in Part B.
3. In another browser, open /moderate and log in with that PIN.
4. Back in «Доступ», press «Изменить» on that moderator. Change the PIN and press «Сохранить».
5. Press «Изменить» again, untick «Включён», press «Сохранить». In the moderator browser, reload.
6. Switch the moderator back on, and set the PIN you will use in Part B.
7. If you don't know the desk or stand PIN, set new ones here with «Изменить».

Expect:
- The new row appears. When editing, «Роль» is disabled and the PIN field hints «Пусто — не менять». A blank PIN keeps the old one.
- After the PIN change, the new PIN works at /moderate and the old one gives «Неверный PIN-код или пароль».
- After switching off, the moderator's next action gets 401 and the login card comes back.
- «Журнал» shows the changes. A PIN change shows as «••••», never the value.

Try:
- A 3-character PIN: «PIN или пароль»: от 4 до 72 символов.
- A new moderator without a PIN: «PIN или пароль»: заполните поле.
- A PIN another moderator already has: «PIN или пароль»: такой PIN или пароль уже у другого сотрудника.
- Add a second «Стойка регистрации» or «Стенды партнёров»: «Такой общий доступ уже есть — смените его PIN».
- «Удалить» on the desk or stand account: «Общий доступ не удаляется — смените его PIN».
- Switch off or delete the only active admin: «Нельзя выключить последнего администратора».
- Delete an account that has change-log entries: «Эту запись уже используют — её можно только выключить».

### A4. Partners and logos: «Партнёры» [022, 025]
1. /admin/settings → «Партнёры». Columns: «Логотип», «Название», «Пакет партнёра», «Включён».
2. Press «Добавить», fill «Название *», pick «Пакет партнёра» = «Генеральный партнёр», press «Сохранить». Add a second one with «Нас поддерживают».
3. Press «Изменить» on each, press «Загрузить логотип (PNG или JPEG, до 1 МБ)», pick a PNG or JPEG.

Expect:
- The thumbnail shows in «Логотип».
- «Журнал» shows «Логотип»: загружен.
- (The logos on /hall are checked in A17.)

Try:
- An SVG or GIF: «Логотип — только PNG или JPEG».
- A file over 1 MB: «Логотип больше 1 МБ».
- A duplicate name: «Название»: такое значение уже есть.
- (After A8) delete a partner that has tasks, prizes or badges: «Эту запись уже используют — её можно только выключить».

### A5. Game settings: «Настройки» [013]
1. /admin/settings → «Настройки». Each row has a label, a number field, «Сохранить» and a hint «min–max · <effect>».
2. Change «Баллы за приход» (0–1000) and press «Сохранить». Set it back to 10 for Part B.
3. Look through the other rows: «Бонус модератора, % от баллов», «Мест в рейтинге гостей», «Топ гостей для проверки в модерации», «Мест на экране зала», «Активный гость»: минут после действия, «Сколько минут ждать фото после заявки», «Сколько отправок может ждать на одном телефоне», the «Экран в зале: …» rows, the «Логотип …» rows, «Множитель монет партнёрских заданий», and «Дата удаления фото: до неё работают ссылки в отчёте партнёра».

Expect:
- «Сохранено» next to the row. «Журнал» logs «Настройки», the setting name, and the old and new values.
- The hint under number rows: «Действует с этого момента: прошлые результаты остаются». The photo date hint: «Пусто — конец последнего этапа + 30 дней · …».

Try:
- «Баллы за приход» = 5000: «Баллы за приход»: допустимо от 0 до 1000.
- A fraction in an integer setting: the same out-of-range message.
- Save the same setting from two tabs: the second shows «Изменено другим администратором — обновите страницу».
- A photo date less than 7 days ahead: «Дата удаления фото — не раньше чем через 7 дней: администраторы должны успеть увидеть предупреждение».

### A6. Skin: «Оформление» [027]
1. In «Настройки», find «Оформление»: four radio cards with previews, «Консоль» (chosen), «Стимпанк», «Космос», «Таджикский орнамент».
2. Pick «Стимпанк», press «Сохранить», then press Cancel in the dialog.
3. Press «Сохранить» again and press OK.
4. With /hall and /admin/live open (and a guest /app later), wait 10 seconds. Then open «Журнал».
5. Switch back to «Консоль» (or keep a skin for Part B, your choice).

Expect:
- Dialog: «Это изменит идущую игру:», «• Оформление сменится на всех экранах: у гостей, на стойках и в зале», «Сохранить?». It asks even when no game is running.
- Cancel changes nothing.
- After OK, open pages switch within 10 s without a reload: guests and the hall go dark brass, staff and admin pages go light parchment.
- Reloading /app opens straight in the new skin, with no Console flash. With the network off it still shows the new skin.
- «Журнал»: «Оформление», Было «Консоль», Стало «Стимпанк», with the admin's name.

Try:
- «Сохранить» is disabled while the chosen skin equals the saved one.
- «Таджикский орнамент»: Tajik words such as «Тоҷикӣ, ҳамаи ҷойҳо, қоидаҳо, ғолиб» show in the skin's font, not a fallback.
- In each of the four skins, /app/welcome, /app and /market at 320 px and /hall at 1920 px: nothing overlaps or scrolls sideways.

### A7. Push switch and texts: «Push» [023]
1. /admin/settings → «Push».
2. See «Отправлять push-уведомления» with the hint «Выключено: на телефоны ничего не уходит, баннер в приложении и на экране зала остаётся». Make sure it is ticked. (It saves on click, without asking.)
3. Under «Тексты push (на русском)», edit «Текст push за 5 минут до квиза», «Текст push при открытии квиза», «Текст push при открытии маркета», «Заголовок разового сообщения (если не указан)», then press «Сохранить».
4. Look at «Расписание» (columns «Время», «Вид», «Заголовок», «Текст», «Состояние»). Sending is tested in B21.

Expect:
- After A8 the schedule has rows generated for stages, quizzes and the market. Kinds: «Начало этапа», «Маркет открыт», «За 5 минут до квиза», «Квиз открыт», «Разовое сообщение». States: «запланировано», «отправлено», «отменено», «истекло».

Try:
- An empty text: «<label>»: от 1 до 200 символов.

### A8. Upload the tasks file and prizes: «Задания и этапы» [012, 013, 017]
1. On /admin/tasks, press «Скачать файл заданий» to get tasks.xlsx.
2. Fill it in as listed in "Files to prepare". Sheets: «Этапы» (Номер, Название, Начало, Конец, Сообщение при смене этапа, Маркет, Карточек в ленте, Множитель), «Задания» (ID, Этап, Тип, Текст, Баллы, Монеты, Партнёр, Пакет партнёра, Доступно с, Доступно до, Выполнение, Ссылка, Таймер, сек, Требует, Лимит, Блиц, Бонус за скорость, Без потерь, сек, Время бонуса, сек), «Вопросы», «Призы», «Уровни», «Бейджи».
3. Press «Выбрать файл», pick it, press «Проверить файл».
4. Read the card «Что изменит файл» (lines like «Задания» · T1 Текст — добавится / изменится / будет скрыто). Press «Отмена» and check nothing changed.
5. Press «Проверить файл» again, then «Применить».
6. Download the file again and upload it unchanged.

Expect:
- Green strip: «Файл применён», «Добавлено заданий: N», «Изменено: N», «Скрыто (нет в файле): N», and where relevant «Этапы: добавлено X, изменено Y», «Призы: добавлено …, изменено …, скрыто …», «Уровни обновлены», «Бейджи: добавлено …, изменено …, выключено …».
- The stage card shows «Сейчас идёт» with the current stage (or «Игра ещё не началась», «Игра завершена», «Расписание этапов не загружено»).
- A new name in «Партнёр» creates a partner in «Партнёры». A QR task gets a QR code.
- Re-uploading the downloaded file: «Файл совпадает с тем, что загружено: изменений нет», and «Применить» is disabled.
- «Журнал» shows the rows with source «Excel».
- A task missing from a later upload is hidden from the feed. A missing stage is NOT switched off.

Try (each refuses the whole file; the red strip «Файл не загружен целиком — исправьте строки:» lists the rows):
- A non-xlsx file, or no «Этапы»/«Задания»: «В файле нет: Этапы, Задания».
- A missing required column: e.g. «В файле нет: Задания: Баллы».
- No points: «Задания», строка 5: нет баллов.
- Unknown type: неизвестный тип задания.
- Stage not in «Этапы»: нет такого этапа на листе «Этапы».
- Duplicate ID: этот ID уже есть выше в файле.
- Bad time: не понятно время начала (пример: 13.12.2026 09:00). End before start: конец раньше начала.
- «Маркет» = maybe: в столбце «Маркет» напишите «да» или оставьте пусто.
- «Ссылка» with no link: для «Ссылка» нужна ссылка в столбце «Ссылка». With ftp://: ссылка должна начинаться с http:// или https://.
- A quiz without questions: у квиза нет вопросов на листе «Вопросы».
- Bad «Требует»: в «Требует» укажите ID задания с выполнением «QR» из этого файла.
- Two packages for one partner: у этого партнёра в строке выше другой пакет, а у партнёра может быть только один.
- Unknown package: неизвестный пакет партнёра (Генеральный партнёр, Хедлайнер, MF Партнёр, Нас поддерживают).
- «Карточек в ленте» = 4: «Карточек в ленте» должно быть целым числом от 5 до 50 или пусто.
- «Уровни» not starting at 0: первый уровень должен начинаться с 0 баллов. Not increasing: «Баллов от» должно расти сверху вниз, без повторов.
- (After a guest buys a prize in B20) prize quantity below sold: количество меньше, чем уже куплено.
- «Бейджи» with an unknown «Тип правила»: неизвестный тип правила (Задания, Все задания типа, Квизы подряд, Бонусы, Первые N, Место). A rule with no «Число»: нет числа для этого правила. The old badges stay.
- A question whose «Правильный (1–4)» points to an empty option: «Правильный (1–4)» должен быть номером заполненного варианта. One option only: нужно от 2 до 4 вариантов, заполненных подряд начиная с «Вариант 1».

### A9. Stage multiplier [020]
1. /admin/settings → «Этапы». Press «Изменить» on the running stage, type 2 in «Множитель», press «Сохранить». Confirm the dialog if one appears. (Or set it in the file and upload.)
2. Leave ×2 (or set ×1.5) on the running stage until B7 is done. B7 ends with setting it back to 1.

Expect:
- The «Этапы» list shows «Множитель» ×2.
- Guest side (checked in B7): cards show «×2», the stage bar shows «×2» next to the stage name (screen-reader label «Очки ×2»).

Try:
- 1.3 or 6: «Множитель: от 1 до 5 с шагом 0,5».
- «Конец» before «Начало»: «Конец»: конец раньше начала.
- «Карточек в ленте» = 3: «Карточек в ленте»: допустимо от 5 до 50.
- Delete a stage that has tasks: «Эту запись уже используют — её можно только выключить».

### A10. Start the next stage now [002, 020]
**Don't press «Подтвердить» now:** it ends the current stage, and every task check in Part B needs that stage. Only check the question and «Отмена» here. The real advance happens in B20 step 1.
1. On /admin/tasks, in the stage card, press «Начать следующий этап сейчас». Read the question, press «Отмена».
2. (In B20, not now:) press it again, then «Подтвердить».

Expect:
- Question: «Начать следующий этап прямо сейчас? Все гости увидят его задания в течение минуты. этап сменится: сейчас X, станет Y».
- «Отмена» changes nothing. «Подтвердить» ends the current stage and starts the next. «Сейчас идёт» updates and «Журнал» logs the times.

Try:
- On the last stage, after the end, or with no schedule, the button is disabled.

### A11. Blitz setup and lock [021]
1. Check the blitz quiz in «Задания»: «Блиц» = да; blank bonus fields mean 20, 3 and 12.
2. Later, while the blitz is running (B17), try changing «Блиц», «Бонус за скорость», «Без потерь, сек», «Время бонуса, сек» or a question in the form, or re-upload the file with a changed value.

Expect:
- Under those fields the form always shows the hint «Нельзя менять во время блица». Saving a change while the blitz runs is refused with the red message «Нельзя менять во время блица». Outside a running blitz the change saves.
- After uploading the blitz row with the three bonus numbers blank, «Скачать файл заданий» shows «Блиц» = да and 20 / 3 / 12.

Try:
- «Блиц» on a non-quiz. File: «Блиц» — только для квиза («Выполнение» = Квиз). Form: «Блиц»: только для квиза.
- «Без потерь, сек» 12 with «Время бонуса, сек» 12: «Без потерь, сек» должно быть меньше, чем «Время бонуса, сек».
- Editing during the blitz in the file: Нельзя менять во время блица / идёт блиц: вопросы этого квиза сейчас менять нельзя.

### A12. Badges: «Бейджи» [024]
1. /admin/settings → «Бейджи». Five seeded badges with columns ID, Название, Тип правила, Число, Тип задания, Монеты, На экран, Включён.
2. «Изменить» on «Фотоохотник», change «Число» from 5 to 1, «Сохранить». If a dialog appears, read it and press OK.
3. «Добавить»: ID, «Название», «Тип правила» = Задания, «Число» = 1, «Монеты» = 20, tick «На экран», «Сохранить».
4. For B18, make a quick badge too, e.g. «Эрудит» = «Квизы подряд», «Число» 2.
5. «Добавить» a badge with «Тип правила» = «Место», «Число» = 1 (B19). «Добавить» a «Первые N» badge with «Число» = 1 and «Задание» = a photo task (B18). None of the five seeded badges uses these rules.

Expect:
- Hint: «Тип задания» — через запятую, как в файле: … «Первые N» — ещё и задание. Recheck fields say «Прошлые результаты пересчитываются».
- Dialog line: «бейдж <ID>: получат N, потеряют M (монеты за него начислятся или вернутся)».
- A badge left out of an uploaded «Бейджи» sheet is switched off for everyone and its coins are returned.

Try:
- «Задания» without «Число»: «Число»: заполните поле.
- «Все задания типа» without a type: «Тип задания»: заполните поле.
- «Первые N» without a task: «Задание»: заполните поле.
- A partner plus «Любой один партнёр»: «Выберите партнёра или «Любой один партнёр», не оба».
- Unknown kind: «Тип задания»: неизвестный тип задания или выполнение.

### A13. Form editing of lists [013]
1. «Задания»: «Изменить» on a task, change «Баллы», «Сохранить».
2. Untick «Включено» on a task that is open now, «Сохранить». Read the dialog, Cancel, then repeat and press OK. Switch it back on afterwards.
3. «Удалить» on a task guests have done (after Part B, or skip).
4. Open the same task in two tabs, save in the first, then in the second.

Expect:
- Guests see the new points within 10 s.
- Dialog: «• задание <ID> пропадёт с телефонов гостей (уже выполнили: N)».
- Blank «Монеты» shows «Пусто — по правилу (баллы, у партнёра × множитель)».

Try:
- «Баллы» = 20000: «Баллы»: допустимо от 0 до 10000.
- Delete a used row: «Удалить «T1»? Это нельзя отменить.», then «Эту запись уже используют — её можно только выключить».
- Second tab: «Изменено другим администратором — обновите страницу».
- Switch off a QR task a quiz requires: «Это QR-задание открывает включённый квиз («Требует») — сначала смените квиз».
- Delete the 0-points level: «Уровень от 0 баллов нужен всегда».
- Switch off a prize while the market is open (after B20 step 1): dialog line «• приз «…» пропадёт из маркета». Before the market opens it saves without asking.

### A14. Partner coin multiplier with live-game confirm [013]
1. While a stage runs, in «Настройки» change «Множитель монет партнёрских заданий» (1–5, step 0.1), «Сохранить». Cancel, then repeat with OK. Set it back to 1.5 for Part B.

Expect:
- Dialog: «Это изменит идущую игру:», «• монеты партнёрских заданий по правилу пересчитаются: N шт.», «• идёт этап: изменение сразу коснётся игры», «Сохранить?». Cancel saves nothing.
- After OK, partner tasks with blank «Монеты» show new coins in /app within 10 s. Paid coins stay.

### A15. Guest list import: «Список гостей» [001]
1. /admin/guests: «Выбрать файл», pick the CSV (UTF-8 or Windows-1251; separator `;`, `,` or tab), press «Проверить список».
2. Read «Что изменит список» (lines «<ID> <Имя Фамилия> — добавится / изменится», note «Гости, которых нет в файле, остаются: у них уже могут быть баллы.»). Press «Применить».
3. Press «Скачать список со ссылками». Keep guests.csv: Part B uses its links.
4. Upload the same file again.

Expect:
- «Добавлено гостей: N» (and «Изменено: N» when something changed).
- guests.csv has the same columns plus «Ссылка» = <DEV>/b/<code>. Re-uploading never changes a link.
- Same file again: «Изменений нет», «Применить» disabled.
- «Журнал»: «Гости» · «Список гостей» · «Загрузка списка», e.g. «добавлено 3, изменено 0», source «Excel».

Try:
- No «ID регистрации» or «Имя»/«ФИО»: «В файле нет столбцов: ID регистрации, Имя».
- A bad row: red strip «Файл не загружен целиком — исправьте строки:» and table «Не загружены строки:» (Строка, Причина), with «нет ID регистрации», «нет имени» or «этот ID регистрации уже есть выше в файле». Nothing applied.

### A16. Task QR sheet [003]
1. /admin/tasks → «QR-коды для печати» (or menu «QR-коды заданий»).
2. Check the hint «Распечатайте и разместите на площадке. Коды ведут на <host> — печатайте с того сайта, где пройдёт игра.».
3. Press «Печать» and look at the preview. Keep the codes for B8.

Expect:
- One card per active QR task, sorted by stage, captioned «<ID> · этап <N>». The QR points to <this origin>/q/<qr_code>.
- The print shows only the QR cards.
- Re-uploading the tasks file keeps the codes.

Try:
- With no QR tasks: «Нет заданий с выполнением «QR». Укажите «QR» в столбце «Выполнение» и загрузите файл.», and «Печать» disabled.

### A17. Hall screen [022]
1. Open /hall (no login) on a second screen, mode «Авто». Watch for 30 s.
2. On /admin/live, card «Экран в зале»: four buttons «Авто», «Эфир сейчас», «Только логотипы», «Пауза» and the hint «Переключение доходит до экрана в зале за 10 секунд.»
3. Press «Эфир сейчас», then «Только логотипы», then «Пауза» (wait 30+ s), then «Авто».
4. Change «Экран в зале: секунд на слайд» (4–30) in «Настройки» and watch.

Expect:
- «Авто»: header «Форум», slides change every N seconds (default 8): «Топ-10» («Рейтинг скоро появится» when empty), «Партнёры форума» logos, and a countdown («До квиза» / «До открытия маркета» / «До начала этапа», mm:ss) when something is ahead.
- The General partner logo is bigger and on every logo slide; Supporters is small and on every 3rd logo slide.
- «Эфир сейчас»: red dot «Эфир» and the full-screen «Топ-10» only, within 10 s.
- «Только логотипы»: only logo slides.
- «Пауза»: the current slide holds.
- «Авто»: the cycle resumes. The pressed button is filled.
- With /hall in «Авто», set «Экран в зале: «Эфир» за столько минут до конца последнего этапа» (5–120) so that window starts now. /hall switches by itself to the red-dot «Эфир» and the full-screen «Топ-10» (default: 30 minutes before the end). After the end it stays there until another button is pressed. Set the value back afterwards.
- A push or an «На экран» badge never interrupts «Эфир» (pressed or by the clock) or «Пауза». This is checked in B18 and B21.

Try:
- Pull the network for 2 minutes: «Нет связи — показан последний рейтинг», the screen keeps cycling and recovers.
- `POST /api/hall/mode` without a token, or with a guest, desk or stand token: 401. A mode other than auto/live/logos/pause: 422.

### A18. Live counts baseline [010]
1. On /admin/live, write down the tiles: «Гостей вошло», «Активны за 15 минут», «Ждут проверки», «Самая старая ждёт», «Призов куплено», «Выдано на стендах», «Осталось».
2. Look at the tables «Выполнения по типам заданий», «Выполнения по этапам», «Партнёры», and the card «Push-уведомления» («Подписаны», «Отправлено», «Доставлено», «Ошибок»).

Expect:
- With no activity: «Пока ничего не выполнено» in the tables (the stage table lists every active stage with 0). «Самая старая ждёт» = «—».
- You re-check these numbers in B22.

Try:
- Stop the backend: red «Что-то пошло не так. Попробуйте ещё раз.», which clears on the next good poll.

### A19. Balance check (first pass) [— (piece 12)]
1. Bottom card on /admin/live, hint «Гости, у которых записанные баллы или монеты не равны сумме их начислений. Ничего не исправляет.». Press «Проверить баланс».

Expect:
- «Расхождений нет». Nothing is changed. The card shows even while the numbers load.

Try:
- Before any guest arrives: /admin/tasks → «Зафиксировать рейтинг» → «Подтвердить»: «Фиксировать нечего: в рейтинге пока никого нет.»

### A20. Change log: «Журнал» [013]
1. /admin/settings → «Журнал». Filter by «Раздел», «Запись», «Администратор», «С даты», «По дату», press «Показать».
2. Press «Скачать журнал (.xlsx)».

Expect:
- Columns «Время», «Администратор», «Раздел», «Запись», «Поле», «Было», «Стало», «Источник» (форма / Excel), newest first, up to 500 rows. No edit or delete controls.
- change-log.xlsx has a sheet «Журнал» with the same filter and all matching rows.

Try:
- A filter with no matches: «Пока пусто».

### A21. Admin pages on a phone and keyboard [017]
1. Open /admin/live at 320 px width.
2. Tab through /admin/tasks with the keyboard.

Expect:
- The menu is a top bar that scrolls sideways on its own. Every table row becomes a card. Nothing else scrolls sideways.
- The focused control is always visible.

> The partner report is checked after the guest activity, in C1.

---

## Part B — Guest

Use guest A's link from guests.csv. Keep the admin browser open.

### B1. Unknown address before sign-in [028]
1. In a fresh guest browser, open <DEV>/. Press Back.
2. Open /nothing-here.

Expect:
- / becomes /app with «Бейдж не найден — подойдите к стойке регистрации», in the event's skin. Back does not land on an empty page.
- /nothing-here becomes /app.

### B2. Arrival by badge link [001, 014]
1. Open guest A's link <DEV>/b/<code> (from guests.csv).
2. Read the consent text «Ваше имя и первая буква фамилии будут видны в рейтинге. Модераторы видят ваши фото. Фото удаляются через 30 дней после форума.» and press «OK».
3. Press «К заданиям».

Expect:
- The address becomes /app/welcome (the #token disappears).
- «Здравствуйте, <Имя>!» and «+10 за то, что пришли на форум», then «К заданиям».
- /app opens and the wallet shows 10 points.

Try:
- Open the same link again: no consent, the greeting and the +10 line show again, but the wallet does NOT grow.
- Open it in a second browser: same guest, no consent, no second +10.
- Change one character of the code: /app/welcome?error=badge with «Бейдж не найден — подойдите к стойке регистрации».

### B3. ↔ Switch to desk: find a guest and add a walk-in [001, 016]
1. Open /desk. Card «Стойка регистрации», «PIN-код», «Войти». Try a wrong PIN, then the desk PIN.
2. In «Имя, фамилия или телефон» type 1 letter (nothing happens), then 2+ letters of guest B's name, or 3+ phone digits.
3. Tap guest B's row. The QR card shows the name, the company and «Наведите камеру телефона на код». Press «Назад».
4. Press «Добавить гостя». Press «Создать QR» with «Имя» or «Телефон» empty, then fill «Имя», «Фамилия», «Телефон», «Компания» and press «Создать QR».

Expect:
- Wrong PIN: «Неверный PIN-код или пароль». After login: the search field and «Добавить гостя». A reload stays logged in.
- Up to 20 matches, sorted by last name, any word order, case-insensitive. Rows show «Фамилия Имя» and «Компания · телефон».
- Empty required fields: the browser's own validation blocks the submit.
- The walk-in is found in the desk search. It also appears, with an empty «ID регистрации», in guests.csv downloaded with «Скачать список со ссылками» on /admin/guests (that page has no on-screen list).

Try:
- A nonsense query: «Никого не нашли».
- The moderator or stand PIN at /desk is refused.
- Over-long values (first name over 100 characters): «Что-то пошло не так. Попробуйте ещё раз.»

**Back to guest:** scan the walk-in QR (or open guest B's link) in a second guest browser. Expect the consent text, «OK», then the greeting with the arrival points. Scanning again on another device gives no second award.

### B4. Home address when signed in [028]
1. As guest A, open / and /nothing-here.

Expect:
- Both land in the feed at /app.

### B5. The feed [002, 014, 019]
1. On /app, look at the screen from the top.

Expect:
- The wallet (level and «до следующего уровня N баллов» if levels are loaded; points and coins; tapping it opens /app/profile), the rows «Партнёрский маркет» and «Рейтинг», the stage bar (segments = stages, current highlighted, name, «до HH:MM»), then the cards.
- Each card: a type tag (e.g. «Действие», «Селфи», «Регистрация», «Квиз»); ★ and the partner name for partner tasks; «до HH:MM» for an open window («Закроется через N мин» for a quiz); the text; the reward («15 баллов», «23 монеты»); one chip: «Доступно», «На проверке», «Выполнено» or «Временно недоступно».
- Order: open window tasks first (closing soonest on top), then partner tasks by package (Генеральный партнёр, Хедлайнер, MF Партнёр, Нас поддерживают), then the rest.
- A partner task with 15 points and blank coins shows 23 coins.

### B6. Stage change and game states [002, 020]
1. Before the game (if you have a stage in the future): «Игра начнётся в HH:MM». With no stages: «Игра скоро начнётся».
2. Skip the stage advance for now. It is done in B20 step 1, because it ends the current stage and all task checks (B7–B19) must be finished first. The "Expect" below is checked then.

Expect (at B20 step 1):
- Within about 10–30 s the feed switches. A banner «Новый этап: {name}» with the stage message; it closes with × or after 8 s. With a multiplier: «Новый этап: {name} — очки ×2».
- A stage without tasks: «Задания этого этапа скоро появятся». After the last stage: «Игра завершена».
- Stage times are Dushanbe local time, not 5 hours off.

### B7. Stage multiplier as seen by the guest [020]
(With ×2 or ×1.5 set in A9.)

Steps (some need the moderator from B12; you can come back to them after B12):
1. Look at the feed. Do a task.
2. ↔ moderator, at ×2: «Отклонить — переснять» on one photo, «Бонус +50%» on a 35-point task.
3. Claim a photo task (or start a quiz) at ×2. ↔ admin: change the stage to ×3 before you finish. Finish.
4. Set the multiplier back to 1 in «Этапы».

Expect:
- Cards of that stage show «×2» in a corner and the stage bar shows «×2» next to the stage name (screen-reader label «Очки ×2»).
- A 5-point task in a ×1.5 stage pays 8 points; coins unchanged.
- The result card shows the base points while the wallet gets the multiplied points (see Open questions).
- «Отклонить — переснять» takes back exactly the doubled points. «Бонус +50%» on a 35-point task at ×2 gives +35.
- The claim or quiz started at ×2 is paid at ×2.
- At ×1, 1 of 3 right on a 10-point quiz gives 4 points.

### B8. Card rotation [019]
1. With «Карточек в ленте» = 5 and 12 plain tasks: reload /app three times.
2. Tap a card, come back with «К заданиям», wait for a 30 s poll.
3. Close the tab, reopen /app.

Expect:
- Each reload shows the next 5 cards after the last card shown, wrapping to the start of the list. (For exact batches 1–5, 6–10, 11–12 + 1–3, use a fresh guest whose first direct load of /app is this step, in a stage with exactly 12 tasks and no window tasks.)
- Coming back from a task and polls do NOT change the batch. Reopening continues where it stopped.
- Open window tasks are always on top and count toward the 5. «На проверке» and retake cards are pinned above and don't count.
- A finished task leaves the rotation; the batch still has 5 cards.

### B9. QR task [003, 014]
1. Open a QR task card. Strip: «Найдите QR-код этого задания на площадке и отсканируйте его камерой телефона».
2. Scan its code from the A16 sheet (or open /q/<code>).
3. Scan it again.

Expect:
- Result card: «+15 баллов», «+15 монет», the task text, «К заданиям». The wallet grows; the task page shows «Выполнено».
- Second scan: «Уже выполнено», totals unchanged.

Try:
- A QR of another stage or closed window: «Это задание сейчас недоступно».
- A changed code: «QR-код не найден».
- The «Лимит» 1 QR task, done first by guest B: «Лимит исчерпан», and its card shows «Временно недоступно».
- Then ↔ admin: raise its «Лимит» to 2. The card shows «Доступно» again and a new scan succeeds. (Same for a limited photo task after ↔ moderator «Отклонить со штрафом» on the holder's submission. After «переснять» it stays full.)
- Scan while signed out: «Бейдж не найден — подойдите к стойке регистрации».
- /q/ with no code goes to /app.

### B10. Link task [003]
1. Open a «Ссылка» task, tap «Выполнить» (the link opens in a new tab).
2. Come back, tick «Я зарегистрировался», tap «Подтвердить».

Expect:
- The tick and «Подтвердить» appear only after «Выполнить» on this phone. «Подтвердить» is disabled until ticked.
- Result card with «+N баллов», «+N монет»; then «Выполнено».

Try:
- Outside its stage: «Это задание сейчас недоступно». Full task: the page shows «Временно недоступно» and no «Выполнить».
- A task with empty «Выполнение»: disabled «Выполнить — скоро».

### B11. Photo task [005, 018, 019]
1. Open a «Фото» task, tap «Выполнить», pick a photo. The frame shows «Загрузка…», then the preview. Try «Переснять», then «Отправить».
2. Tap «К заданиям».

Expect:
- Result card «+N баллов» / «+N монет»; the wallet grows at once.
- The card and the task page show «На проверке». The page has «Удалить фото».
- When the stage ends (B20) with a photo still undecided, the card shows «Выполнено» and the photo is still in /moderate.

Try:
- A non-image file: «Не получилось открыть фото. Выберите другое.»
- The next-stage photo task (open /app/tasks/{id}): «Этап закрыт». After the window: «Время вышло». Full task: the page shows «Временно недоступно» and no photo picker.

### B12. ↔ Switch to moderator: queue and decisions [006]
1. Open /moderate. Card «Модерация», «PIN-код», «Войти». Wrong PIN first, then the moderator PIN from A3.
2. Look at the header and panels. Tap a photo («Открыть фото целиком»), close it with «Закрыть», a tap or Escape.
3. Have guests A and B send several photo/text tasks. Then decide them one per button:
   - «Принять»
   - «Бонус +50%» (note the guest's points first)
   - «Отклонить — переснять»
   - «Отклонить со штрафом»
   - Also «Принять» (or «Бонус +50%») on the partner photo task, so C1 and C2 have a photo link.
4. Tick «Топ-20», then untick.
5. Two moderators (browser A and B) on the same card: press «Принять» in A, then any button in B within 5 s.

Expect:
- Header with the moderator's name and the checkbox «Топ-20». Panels «Ждут проверки» and «Самая старая ждёт» («меньше минуты» or «N мин»; hidden when nothing waits). Then «Экран в зале», then cards or «Очередь пуста».
- New cards appear within 5–10 s, newest first: thumbnail and/or text, task name, points, guest as first name + last initial, «отправлено в HH:MM».
- Each decision removes the card and lowers «Ждут проверки».
- B's card shows «Уже проверено: <name of moderator A>». Guest totals change once.
- «Топ-20» shows only guests in the top «Топ гостей для проверки в модерации» (default 20).

Try:
- Desk or stand PIN at /moderate: refused.
- Any decision error: «Что-то пошло не так. Попробуйте ещё раз.»

**Back to guest:**
- «Принять»: totals unchanged, the task shows «Выполнено».
- «Бонус +50%»: points rise by half the awarded points rounded up (35 → +18 at ×1); coins unchanged.
- «Отклонить — переснять»: points and coins taken back, the task shows «Фото не подошло — отправьте ещё раз» and can be sent again (paid again, back in the queue). The level may drop.
- «Отклонить со штрафом»: points and coins taken back, red chip «Не засчитано», the page text «Задание не засчитано, баллы и монеты за него сняты. Засчитываем только свои фото и тексты, сделанные на форуме по заданию, — без повторов и оскорблений.» The task can't be sent again. Coins may go negative.

### B13. Guest withdraws a photo [018]
1. On a photo task showing «На проверке», press «Удалить фото».
2. Read «Фото ещё не проверено: задание будет снято, а баллы и монеты за него списаны. Удалить фото?», press «Отмена», then repeat and «Подтвердить».
3. On a photo that was already decided, press «Удалить фото».

Expect:
- Points and coins taken back; the page shows «Фото удалено — задание снято»; the task stays closed.
- ↔ /moderate: the card disappears on the next poll.
- Decided photo: the question is «Удалить фото? Баллы и монеты за задание останутся.», and totals don't change.

### B14. Text and photo+text tasks [005]
1. A «Текст» task: type in «Ваш ответ» (counter «N / 500»), «Отправить».
2. A «Фото+текст» task: «Выполнить», a photo, text, «Отправить».

Expect:
- Result card with +N, then «На проверке».
- For photo+text, «Отправить» is disabled until both are there.

Try:
- 501 characters: stops at «500 / 500». Only spaces: «Отправить» disabled.
- On iPhone, tapping the field doesn't zoom.

### B15. Offline sending and the offline feed [018, 002]
1. DevTools → Network Offline. Send a photo task. Go back to /app.
2. Close the tab, go back online, reopen /app.
3. Offline, reload /app.
4. Queue: set «Сколько отправок может ждать на одном телефоне» = 1 (↔ admin), send one photo offline, try another.

Expect:
- Offline: the page and card show «Ждёт сети — ещё не засчитано». While sending: «Загружается».
- After reopening online, sending resumes, pays once, and the card moves to «На проверке».
- Offline reload: the last feed with «Нет связи — показаны последние данные».
- Queue full: «Дождитесь загрузки предыдущих фото», nothing saved.

Try:
- Offline, signed in but with no saved feed (delete `last_feed` from localStorage, then reload): «Что-то пошло не так. Попробуйте ещё раз.»
- If the claim reaches the server after the stage ended: «Этап закрыт».
- Lapse: with «Сколько минут ждать фото после заявки» = 10, a claim with the photo blocked more than 10 minutes shows «Время вышло».

### B16. Quizzes [008, 015]
1. Tap the 5-question quiz card → task page → «Начать».
2. On /app/quiz/{id}: header «Квиз», «К заданиям», «Осталось 00:59», «Вопрос 1 из 5», lettered answers A–D. Answer 3 of 5 correctly.
3. Start another quiz, answer one, wait 30 s, reload. Then let it run under 10 s and to 00:00.
4. Partner quiz: both answers correct.
5. Quiz with «Требует»: open it before scanning the hall check-in QR (not the B9 one), then scan it, then open the quiz again.
6. A quiz whose window closes soon: watch its card.

Expect:
- Answer order is shuffled and stays the same on reload.
- Result: «3 из 5 · +30 баллов, +30 монет», the quiz text, «К заданиям», no correct answers shown. The task page then shows «Выполнено — посмотреть результат».
- After reload the time continues (about 30 s left). At 10 s or less the panel turns red and reads «Мало времени». At 0: «Время вышло» and the score; unanswered count as wrong.
- Partner quiz: «2 из 2 · +25 баллов, +38 монет».
- «Требует» before the scan: «Сначала отметьтесь в зале» and no «Начать». After the scan, «Начать» appears.
- Window card: «Закроется через N мин»; it leaves the feed after closing. A started quiz can be finished within its timer.

Try:
- /app/quiz/99999: «Квиз не найден».
- A quiz not running or with its window closed: «Этот квиз сейчас недоступен». Limit reached: «Лимит исчерпан».
- A finished quiz reopens the result only.

### B17. Blitz [021]
1. Start the blitz. Answer Q1 right within 2 s, Q2 right at about 7.5 s, Q3 right after 12 s, Q4 wrong, Q5 right quickly.
2. **↔ Switch to admin:** while it runs, do the A11 lock check.
3. **Back to guest:** read the result, then /app/profile and /app/rating.

Expect:
- «4 из 5 · +40 баллов, +40 монет · +50 за скорость» (Q1 20, Q2 10, Q3 0, Q4 wrong, Q5 20).
- Rating points grow by 90; coins by 40 only.
- Profile row: «+40 баллов», «+40 монет», «+50 бонус».
- A reload mid-blitz keeps the same question and its timing.

Try:
- Set the phone clock 5 minutes wrong and play a blitz: the speed bonus for the same answer times is the same.

### B18. Levels, profile and badges [009, 024, 015]
1. Get a guest from 140 to 165 points, return to /app. Close the moment with «Отлично» or Escape. Reload.
2. Tap the wallet to open /app/profile.
3. Meet a badge rule (e.g. 2 perfect quizzes in a row, or the A12 badges). Return to /app.
4. **↔ Switch to moderator:** reject a photo that counted toward a photo badge. **Back to guest:** open the profile.

Expect:
- At 140: «Участник» and «до следующего уровня 10 баллов». After 150: «Новый уровень: Актив» with «Отлично», shown once.
- Profile: «Профиль», «К заданиям»; level, points, coins (negative in red); «Бейджи» (earned in colour, others greyed with their condition); «История» newest first: «За приход на форум» «+10 баллов», task rows with «+N баллов», «+N монет», «+N бонус», «отклонено», «фото удалено — снято». Empty: «Здесь появятся выполненные задания».
- Badge: «Новый бейдж: {name}» with «Отлично», once (level moment first if both). Coins added if the badge has «Монеты». With «На экран», /hall shows «{Имя Ф.} — бейдж «{name}»».
- After the rejection the badge disappears with no moment and its coins are taken back. A drop in level is quiet.
- A badge with «Монеты» 20 adds exactly 20 coins at once, even in a ×2 stage. Points and rating place don't change.
- «Первые N» (N = 1, from A12): the first guest to do the task gets it, the second doesn't. ↔ moderator: reject the first guest's photo. The second guest now gets it.
- With /hall in «Эфир сейчас», earning an «На экран» badge does not interrupt the screen.

### B19. Rating [007]
1. Tap «Рейтинг» on /app.
2. Check guest A (in the top), a guest outside the top, and the «В рейтинге» = нет guest.
3. **↔ Switch to admin:** /admin/tasks, card «Рейтинг»: «Зафиксировать рейтинг» → «Подтвердить». Press «Печать» under «Топ-10 для ведущего».
4. **Back to guest:** reload /app/rating. **↔ moderator:** reject a photo of a top-3 guest. Reload /app/rating and /hall.
5. **↔ admin:** «Снять фиксацию» → «Подтвердить».

Expect:
- Top «Мест в рейтинге гостей» rows: place, «Анна К.», badge icons, level, points. My row is highlighted with «Вы».
- Outside the top: «Вы на 34-м месте · 120 баллов». No points or «В рейтинге» = нет: «Вас пока нет в рейтинге».
- Admin: «Итоги зафиксированы: …» and a table Место, ФИО, Компания, Баллы. The «Место» badge from A12 goes to place 1.
- Guest: «Итоги зафиксированы» above the list; places stop changing (also on /hall with a lock icon). The rejection after the freeze doesn't move the frozen places. After unfreezing, live places return.
- Two guests with equal points: the one who reached the score first is above.
- The «В рейтинге» = нет guest with the most points is on neither /app/rating nor /hall, but can still do tasks and buy in the market.
- The printed «Топ-10 для ведущего» shows no buttons or menu.

Try:
- Nobody ranked on the guest page: «В рейтинге пока никого нет».

### B20. Market and stand [004]
1. Before the «Маркет» stage: open /market from «Партнёрский маркет». Then **↔ admin:** if the «Маркет» stage is the next one, on /admin/tasks press «Начать следующий этап сейчас» → «Подтвердить» (otherwise wait for its start time). **Back to guest:** watch /app without reloading and check the B6 "Expect" (stage banner, feed switch).
2. After it opens: press «Обменять» on an affordable prize, read the confirm, «Отмена», then again «Подтвердить».
3. **↔ Switch to stand:** scan the guest's QR or open /stand/<code>. Card «Стенд партнёра», «PIN-код», «Войти». Enter the stand PIN. Press «Выдано». Reopen the same code.
4. **Back to guest:** wait up to 10 s on /market, then open /app/profile.

Expect:
- Header «Партнёрский маркет» with the coin balance and «К заданиям». Cards: partner, name, price, «осталось N».
- Closed: «Маркет откроется в HH:MM» (or «Маркет скоро откроется»); «Обменять» disabled with a lock.
- Confirm: «Обменять N монет на «<prize>»?». After buying: coins drop; the card goes to the top with «Подойдите к стенду партнёра <partner>, покажите этот экран», a QR and «Код: ABC123». «осталось» drops. A «Маркет» task, if any, is completed once.
- Stand: partner, prize, «Гость: <first name>», «Выдано» → green «Приз выдан». Reopen: «Уже выдано в HH:MM».
- Guest: «Получено» instead of the QR. Profile: «{prize} · Покупка в маркете · −30 монет».
- A bought prize shows its QR or «Получено», with no «Обменять»: the same prize can't be bought twice.
- After a «Отклонить со штрафом» that leaves coins negative, every prize shows «Не хватает N монет» until the balance is back above the price.

Try:
- Too few coins: disabled «Не хватает N монет». Stock 0: «Закончились».
- Two guests buy the last item at once: one gets it, the other sees «Закончились» and keeps the coins.
- Stand: wrong PIN «Неверный PIN-код или пароль»; unknown code «Код не найден»; two phones pressing «Выдано» at once, one gets «Уже выдано в HH:MM».
- /market without a guest token: «Бейдж не найден — подойдите к стойке регистрации».
- ↔ admin: re-upload the file with a higher «Количество»: earlier purchases stay valid and «осталось» updates.

### B21. Push opt-in and sending [023]
Needs a production build and VAPID keys.
1. With a fresh guest, look at /app after arrival only (no ask expected).
2. Earn the first task points, return to /app. Tap «Включить» and allow. (On another device, tap «Не сейчас».)
3. **↔ Switch to admin:** «Push» → «Расписание» → «Добавить» a «Разовое сообщение» with «Время» and «Заголовок», «Сохранить». Press «Отправить сейчас» on it and confirm «Отправить «…» всем подписанным сейчас?».
4. **Back to guest:** watch the phone and the open app. Check /admin/live «Push-уведомления».
5. iPhone Safari: open /app; close the guide; reopen it from the profile with «Как получать уведомления на iPhone».
6. **↔ admin:** in «Расписание» press «Изменить» on a planned «Квиз открыт» push, change «Текст», «Сохранить». On another planned push set «Состояние» = «отменено».
7. In «Задания», move that quiz's «Доступно с» by 15 minutes.
8. Untick «Отправлять push-уведомления», wait past a planned push, then tick it again.
9. Put /hall in «Эфир сейчас» (then «Пауза»), send a one-off push. Then switch /hall to «Авто» and send another.

Expect:
- After the first task points: «Узнайте первым о квизе и открытии маркета» with «Включить» and «Не сейчас». After «Не сейчас» or a block, this phone is never asked again.
- The phone gets the push; open apps show a banner. /hall shows it for 15 s in «Авто»/«Только логотипы». The row shows «отправлено X · доставлено Y · ошибок Z»; /admin/live counts go up.
- iPhone: «Чтобы получать уведомления, добавьте приложение на экран «Домой»» with three steps; no push prompt in Safari.
- The edited push arrives with the new text. The cancelled one never arrives.
- After the quiz moves, both its «За 5 минут до квиза» and «Квиз открыт» rows move by 15 minutes; an edited text is kept.
- While switched off nothing reaches phones, but open apps and /hall still show the banner.
- With /hall in «Эфир сейчас» or «Пауза», the push does NOT appear on /hall. In «Авто» it fills the screen for 15 s, once.
- A stage push at ×2 is titled «Новый этап: {name} — очки ×2» with the stage's «Сообщение при смене этапа». When the «Маркет» stage starts (B20), a «Маркет открыт» push arrives.

Try (admin):
- Add a kind other than one-off: «Добавить можно только разовое сообщение — остальные push следуют за этапами и квизами».
- Send with push off: «Push-уведомления выключены — сначала включите их». Without VAPID: «Push-уведомления не настроены на сервере (нет ключей VAPID)».
- Edit a sent push: «Этот push уже отправлен или истёк — его можно только отправить снова».
- Delete a stage or quiz push: «Этот push следует за этапом или квизом — его можно только отменить».
- Without VAPID keys the guest is never asked.

### B22. ↔ Switch to admin: live counts after guest activity [010]
1. On /admin/live, wait up to 30 s without reloading. Compare with A18.

Expect:
- «Гостей вошло» = number of guests who signed in. «Активны за 15 минут» counts guests with task points, a submission or a purchase (the +10 arrival does not count).
- «Ждут проверки» and «Самая старая ждёт» match /moderate (e.g. «6 мин», «0 мин» under a minute).
- «Призов куплено» and «Выдано на стендах» +1 after B20; «Осталось» = stock left.
- Tables show Russian type names and «N. Название» stages. A partner's «Выполнений» and «Уникальных участников» grow; penalty-rejected and withdrawn submissions don't count.

### B23. Task page edge cases and console look [014, 015, 016, 027]
1. Open /app/tasks/999999. Open a «Маркет» task.
2. Open the quiz, market, rating and profile pages at 320 px width.
3. On an iPhone with a notch, open /app and pull past the top.
4. Load /app, go offline, reload. Check the network panel.
5. Turn on reduced motion in the OS.
6. Open /desk, /stand/<code> and /moderate at 320 px; /moderate also at 768 and 1024 px; /hall at 1920×1080.

Expect:
- «Задание не найдено» with «К заданиям».
- Market task: «Обменяйте монеты на любой приз в «Партнёрском маркете»» with «В маркет».
- The console look everywhere, no sideways scroll at 320 px. Only the level and badge moments are full-screen.
- Notch: the wallet and the last card are clear of the notch and home bar. Pulling past the top shows dark ground, and the browser bar is dark.
- Offline reload: titles and numbers still use the skin's fonts. The network panel shows no request to fonts.googleapis.com or fonts.gstatic.com, only the current skin's fonts.
- Reduced motion: nothing glows, flickers or slides.
- Staff pages at 320 px: no sideways scroll. /moderate shows 3 columns at 1024 px or wider, 2 from 768 px, 1 on a phone. /hall at 1920×1080: all ten rows fit without scrolling.

Try:
- Edit `guest_token` in localStorage: «Бейдж не найден — подойдите к стойке регистрации».

---

## Part C — After the event

### C1. Partner reports [010, 025]
1. On /admin/live press «Скачать отчёт по партнёрам». Open partners.csv in Excel.
2. Pick a partner in «Выберите партнёра», press «Отчёт партнёра (Excel)». Open the sheets «Сводка», «Детали», «Фото».
3. Freeze the rating on /admin/tasks and download again.

Expect:
- CSV: semicolon separated, Cyrillic intact. Header «Партнёр», «Пакет», «Задание», «Выполнений», «Уникальных участников». Totals match the «Партнёры» table.
- «Сводка»: «Отчёт партнёра: <name>», «Пакет», «Сформирован», «Предварительные данные: итоги форума ещё не зафиксированы» (only before the freeze), «Ссылки на фото работают до DD.MM.YYYY»; tasks with «Отклонено» and «Итого»; prizes «Куплено», «Выдано на стендах»; «Логотип на экране в зале» «Показов», «Секунд»; «Push-уведомления (весь форум)».
- «Детали»: one row per task per hour.
- «Фото»: only accepted or bonus photos with links /api/photos/<token>. No guest names.
- After the freeze, the «Предварительные данные…» line is gone.

Try:
- Without a partner picked, the button is disabled.
- `GET /api/admin/partners/99999/report` as admin: 404 `partner_not_found`.

### C2. Public photo link [025, 026]
1. Open a link from «Фото» in a private window. Open /api/photos/abc.
2. (Plan ahead in B12:) the partner photo should be a 6 MB phone photo taken with location on. Open its link and save the file.

Expect:
- The JPEG shows without login.
- Its longest side is at most 1600 px, and the file has no GPS/EXIF data.
- Unknown token, undecided or rejected photo: 404 `{"detail":"photo_not_found"}`.

### C3. Balance check (final) [— (piece 12)]
1. Press «Проверить баланс».

Expect:
- «Расхождений нет» after all the awards, bonuses, rejections, withdrawals and purchases.

Try (local only, skip on dev):
- Change one guest's points in the database: the guest appears in the table «Гость», «Баллы», «Сумма баллов», «Монеты», «Сумма монет».

### C4. Photo deletion banner and job [026]
On dev only steps 1–2 can be done, and only if the deletion date really is within 7 days. Step 3 is **local only**: on dev the job runs by itself every minute and can't be called.
1. Make the deletion date fall within 7 days (move the last stage's «Конец» before the lock). Open any admin page.
2. Try changing «Дата удаления фото…» in «Настройки».
3. Make the date today or earlier (on the copy). Run `POST /api/jobs/run` with the `X-Jobs-Secret` header twice, then a third time.

Expect:
- Amber notice «N фото будут удалены D месяца».
- The date field is disabled: «Дата удаления фото уже объявлена администраторам (за 7 дней) — её нельзя изменить».
- Run 1: «photo_deletion», ok, «удалено фото в этом запуске: N; сжатие — в следующем». Run 2: «удалено фото: N; начало …, конец …; в истории восстановления Neon до DD.MM.YYYY». Run 3: empty detail.
- Photo links answer 404; the banner disappears; /admin/live numbers unchanged.
- Each run also lists «lapsed_claims» with «истекло заявок: N». A claim older than «Сколько минут ждать фото после заявки» is counted, and a later upload for it pays nothing.

Try:
- On dev: `POST <DEV>/api/jobs/run` from your browser or curl answers 404 (the Worker refuses it). Locally, a missing or wrong `X-Jobs-Secret` answers 401 `{"detail":"not_allowed"}`.
- Two runs at the same moment: one is logged as «skipped».

---

## Results checklist

| Step | Pass | Fail | Notes |
|---|---|---|---|
| A1 Admin sign-in | | | |
| A2 Login on /admin/live | | | |
| A3 Staff accounts | | | |
| A4 Partners and logos | | | |
| A5 Game settings | | | |
| A6 Skin | | | |
| A7 Push switch and texts | | | |
| A8 Tasks file upload | | | |
| A9 Stage multiplier | | | |
| A10 Start next stage | | | |
| A11 Blitz setup and lock | | | |
| A12 Badges | | | |
| A13 Form editing of lists | | | |
| A14 Partner coin multiplier | | | |
| A15 Guest list import | | | |
| A16 Task QR sheet | | | |
| A17 Hall screen | | | |
| A18 Live counts baseline | | | |
| A19 Balance check (first) | | | |
| A20 Change log | | | |
| A21 Admin on phone and keyboard | | | |
| B1 Unknown address signed out | | | |
| B2 Arrival by badge link | | | |
| B3 Desk | | | |
| B4 Home address signed in | | | |
| B5 Feed | | | |
| B6 Stage change | | | |
| B7 Multiplier on guest side | | | |
| B8 Card rotation | | | |
| B9 QR task | | | |
| B10 Link task | | | |
| B11 Photo task | | | |
| B12 Moderation | | | |
| B13 Withdraw photo | | | |
| B14 Text and photo+text | | | |
| B15 Offline | | | |
| B16 Quizzes | | | |
| B17 Blitz | | | |
| B18 Levels, profile, badges | | | |
| B19 Rating | | | |
| B20 Market and stand | | | |
| B21 Push | | | |
| B22 Live counts after activity | | | |
| B23 Edge cases and look | | | |
| C1 Partner reports | | | |
| C2 Public photo link | | | |
| C3 Balance check (final) | | | |
| C4 Photo deletion | | | |

---

## Open questions

- /admin/settings is not in the admin menu and has no link back.
- The upload hint for «Этапы» doesn't mention «Множитель», though the parser reads it.
- The stage banner text: contract 020 says «Этап 3 — очки ×2»; the app text is «Новый этап: {name} — очки ×2» (not confirmed on screen).
- A stage missing from an uploaded file is not switched off (only tasks, prizes and badges are).
- Settings use the browser's OK/Cancel dialog; /admin/tasks uses «Отмена» / «Подтвердить». The push switch saves without asking.
- If the `MODERATORS` secret of `dev` had empty PINs at the first start, no moderator was seeded: add one in «Доступ» (A3).
- «Активны за 15 минут», «Бонус +50%» and «Топ-20» are fixed labels while the numbers follow the settings.
- /admin/live shows «0 мин» while /moderate shows «меньше минуты».
- Photo links stop ON the deletion date (contract says "after").
- The photo-deletion banner count is read once on page load, not polled.
- The deletion job can be tested only with database changes; job runs have no admin screen.
- Without VAPID keys a due push is marked «истекло» but still shows on /hall and in open apps.
- The partner Excel is saved as «<partner name>.xlsx»; the server names it partner-<id>.xlsx.
- The photo-link 404 is raw JSON, not a styled page.
- The quiz/QR result card shows base points while the wallet gets the multiplied points.
- The rotation advances only on a direct load of /app; the first reload after arrival may repeat the first batch.
- The greeting's «+10 …» line shows again on every return to /app/welcome (the total doesn't change).
- Photo, text and photo+text cards stay «На проверке» until a decision or the stage end (contract 005 said «Выполнено» at once).
- A blitz with no speed bonus still shows «· +0 за скорость». The profile merges the speed bonus into «+N бонус».
- No admin screen lists moderation decisions; not confirmed whether «Журнал» shows them.
- Decision errors all show the generic «Что-то пошло не так. Попробуйте ещё раз.»
- Staff pages have no logout button.
- Nothing here was clicked through in a browser; it is read from the code.
