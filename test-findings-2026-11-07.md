# Test findings and fix plan: dev run of 2026-11-07

Source: a full run of `test-scenario.md` on https://gamify-dev.manuchehr-407.workers.dev with the kit in `gamify-test-kit/`. Step-by-step evidence is in `gamify-test-kit/RESULTS.md`.

Each finding was checked against its contract in `contracts/` and sorted into one of four kinds:
- **Bug**: the app breaks what a contract says. Fix it inside that piece; no new spec.
- **Client question**: no contract covers it. The owner asks TAG; a yes becomes a new piece via ship-spec.
- **Infra**: deployment, not a piece. It comes first because it would hurt a live event.
- **Scenario fix**: the app follows its contract and the test text is wrong. Fix `test-scenario.md`.

Rules for whoever runs this plan (from CLAUDE.md): build only what a contract lists; Claude never edits a contract on its own, and a contract change needs the owner's one-line approval; any new package stops work until the owner approves it; run `/mg-ship-kit:cto-check` before a piece reaches dev; run `cd backend && .venv/bin/pytest` before calling anything done; flag any change of direction as "CHANGE: …".

---

## Findings

### F1. Dev drops requests now and then (infra, highest priority)
- **Seen:** 4 times in about 90 minutes. The body was HTTP 500 «Container suddenly disconnected, try again». Guests saw «Что-то пошло не так»: on a staff save, a tasks list read, a task read, and a quiz answer. A manual retry always worked.
- **Cause found:** `deploy/src/index.ts:50` retries only when the body starts with `Error proxying request to container`. Dev returned «Container suddenly disconnected, try again», which falls through to the guest.
- **Context:** `deploy/wrangler.jsonc` runs one `basic` instance (`max_instances: 1`) for dev and production. Photo uploads and resizing run in that same container, so memory pressure or a restart is a likely trigger. Not confirmed.
- **Why first:** at the event every guest shares that one container, so random errors hit quizzes and purchases.

### F2. The admin lock card says «Список гостей», not «Администратор» (bug, piece 016)
- Already fixed in the working tree but not committed or deployed. Uncommitted files: `frontend/src/components/console/admin.tsx`, `frontend/src/locales/ru.json`, `frontend/src/pages/AdminGuests.tsx`, `backend/tests/test_console_admin.py`, `backend/tests/test_console_staff_hall.py`, **and `contracts/016-console-look-staff-and-hall-screen.md`**.
- **The contract file is modified locally.** Confirm the owner approved that change before committing. If not, revert the contract edit and keep only the code.

### F3. Result cards disagree on points under a stage multiplier (client question)
- **Seen at ×2:** QR, link and photo result cards show base points («+15 баллов» while the wallet gets 30). Quiz results show multiplied points («3 из 5 · +60 баллов»; the partner quiz shows «+50 баллов»). The blitz shows multiplied points plus a multiplied speed bonus.
- **Contracts:** 020 says feed cards keep the base points with a «×2» mark (line 13), but says nothing about result cards. 008, 015 and 021 define the result line only at ×1. Also listed in the scenario's "Open questions".
- **Question for TAG:** should a result card show what the guest actually got (multiplied), or the task's base points? Pick one rule for every result card.
- **If the answer is "what they got":** a small piece that touches the QR/link/photo result card only (014/018 area). If the answer is "base": change the quiz result text instead. Either way it's a new contract line, so the owner approves it.

### F4. The tasks file changes a partner's package, and the preview never says so (bug, piece 013, owner to confirm)
- **Seen:** the kit file names «Нур Диджитал» as «MF Партнёр». Dev had it as «Нас поддерживают». The preview listed only stages, tasks and prizes; after «Применить» the package had changed.
- **Contracts:** 012 line 40 says the «Задания» sheet sets a partner's package, so the change itself is correct. 013 line 29 says a valid upload «first shows a preview: added, changed, and rows that would be hidden». The preview left out a change the file makes. Partners created by the file («Сомон Аналитикс») weren't listed either.
- **Fix:** the tasks preview (`POST /api/admin/tasks/import/preview`) lists partner rows that will be added or will change package, as «Партнёры» · <name> — добавится / изменится (пакет: было → стало). No new endpoint.
- **Owner check:** confirm this reading of 013 before building. If the owner says partners aren't covered by 013's preview, it becomes a client question.

### F5. A next-stage task page shows an active «Выполнить» (scenario fix; small UX option)
- **Seen:** /app/tasks/74 (stage 2, while stage 1 ran) shows «Выполнить». «Этап закрыт» comes back only after the guest has picked a photo (the claim returns `stage_closed`).
- **Contracts:** 018 line 65 promises «Этап закрыт» only when a claim reaches the server after the stage. No contract says the page itself shows it. A guest reaches a next-stage task only by typing its URL, because the feed hides other stages.
- **Do:** fix B11 «Try» in `test-scenario.md`: «Этап закрыт» appears after a photo is picked, not on opening the page.
- **Optional (client question, low value):** show «Этап закрыт» on the page before the picker. Skip unless TAG asks.

### F6. Times without dates on long stages; «Закроется через 3757 мин» (scenario/kit artefact)
- **Seen:** the stage card «18:00–18:00» and the stage bar «до 18:00» for a stage that runs four days; the window quiz card «Закроется через 3757 мин».
- **Contracts:** 008 line 19 specifies «Закроется через N мин» exactly, and 002 shows times only. The app matches its contracts. Only the test kit has a four-day stage; the real event runs within one day.
- **Do:** nothing in the app. Optionally ask TAG whether any stage can cross midnight; if yes, it's a new piece.

### F7. Small cleanups (check each against 013/017; batch or drop)
- «Журнал» shows a partner's package as raw codes (`general` → `supporters`) instead of «Генеральный партнёр» → «Нас поддерживают». Probably a 013 bug: other choice fields show Russian labels. Check 013's log rules.
- The number fields in «Настройки» have no label tied to them (`<input>` without a label or aria-label). A screen reader can't name them. Check 017's keyboard/accessibility lines; if covered, it's a 017 bug.
- The /admin/settings lists stay tables at 320 px. The page doesn't scroll sideways, but 017/A21 say «Every table row becomes a card». Check whether 017 covers /admin/settings or only the other admin pages.
- The «Действует с этого момента: прошлые результаты остаются» hint shows under every field of the «Доступ» staff form, including «Имя» and «Включён», where it means nothing. Check 013's hint rule.

---

## Not run, so not cleared (do by hand)
- **A3:** «Удалить» on the desk account and the last admin. Expect «Общий доступ не удаляется — смените его PIN» and «Нельзя выключить последнего администратора». Blocked here because a wrong result would delete real dev accounts.
- **A5:** saving the same setting from two tabs in the UI (the API `stale` check passed).
- **A8-02…A8-26:** the negative tasks files on dev (only A8-01 was run; the kit says all were checked locally).
- **B15** offline sending; **B21** phone push opt-in, delivery and the iPhone home-screen guide; **B23** iPhone notch and reduced motion. These need a real phone.
- **B6:** stage 3 («Задания этого этапа скоро появятся», then «Игра завершена»).
- **C2:** the kit's 6 MB GPS photo. A 4000×3000 photo was stored as 1600×1200 with no EXIF data, but GPS removal from a real phone photo isn't proven.

## Dev state left by the run
- **Stage 2 «День: маркет открыт» is running** (started by hand at 03:46). The market is open and stage-1 tasks are closed. To test stage-1 tasks again, re-upload `gamify-test-kit/tasks.xlsx` with times moved (`python3 gamify-test-kit/make_kit.py --start "DD.MM.YYYY HH:MM"`).
- The skin is «Консоль». Partners match the kit names (`chinor-print` was renamed «Чинор Принт»).
- **Staff:** test moderator «Тест Модератор» and a new «Стенды партнёров» account; the desk PIN was changed. The PINs aren't recorded anywhere, so reset them in /admin/settings → «Доступ».
- **Badges changed for the test:** Фотоохотник count 1 with any partner; Эрудит count 2; added «Первое селфи», «Чемпион», «Старт» (20 coins, on screen). Remove «Старт» before a real event.
- QR-LIMIT «Лимит» = 2. Walk-in guest «Тестовый Гость» exists. Two photos still wait in moderation. Guest A (MF-001) has an open claim on PH-AFTER from an API test; it lapses after 60 minutes.

---

## Fix plan (in order)

### Step 1: F1, the dropped requests (infra)
1. Read the dev Worker logs (Cloudflare dashboard → gamify-dev → Observability) for 2026-11-07, roughly 02:40–03:45 Dushanbe time (the exact minutes weren't recorded; search for «Container suddenly disconnected»). Note whether the container restarted or ran out of memory.
2. In `deploy/src/index.ts`, treat «Container suddenly disconnected» like `DROPPED`, but retry only when that's safe:
   - GET and HEAD: retry once.
   - POST: retry only routes that are already idempotent. Claims carry an `id`, `/files` repeats by claim id, and decisions answer `already`. Don't blindly retry `/api/market/{id}/buy` or quiz `/answer` until you've confirmed they're idempotent; read `backend/app/routers/market.py` and `quiz.py` first.
3. If the logs show memory or restarts, propose a bigger `instance_type` for production in `deploy/wrangler.jsonc` as a one-line "CHANGE:" for the owner. Don't change it unasked.
4. Production changes go only through the pipeline, never by hand.
5. Verify: a burst of reads and photo uploads on dev shows no «Что-то пошло не так».

### Step 2: F2, ship the 016 fix
1. Ask the owner to confirm the local edit to `contracts/016-console-look-staff-and-hall-screen.md` (one line). If not approved, revert that file only.
2. Run `cd backend && .venv/bin/pytest` and `cd frontend && npm run lint && npm run build`.
3. Run `/mg-ship-kit:cto-check`, then commit and push to `dev` through the usual pipeline.
4. Verify on dev: /admin/tasks signed out shows the lock card «Администратор».

### Step 3: F4, partner changes in the tasks preview (after owner confirms it's 013)
1. Find where the tasks import preview builds its lines (`backend/app/task_file.py`, preview path) and add partner add/package-change lines.
2. Add a backend test: a file that changes a partner's package previews «Партнёры» · <name> — изменится, and a new partner previews — добавится.
3. Verify on dev with the kit's `tasks.xlsx` against a partner set to another package.

### Step 4: questions for TAG (owner sends; no code until answered)
- F3: result cards, base or received points?
- F5 (optional): show «Этап закрыт» on a next-stage task page?
- F6 (optional): can any stage cross midnight?
- Each yes becomes a piece via ship-spec, then `/mg-ship-kit:next`.

### Step 5: F7 cleanups
For each item, read the named contract. Where the contract covers it, fix it as a bug in that piece (one small commit each, tests first). Where it doesn't, drop it unless the client asks.

### Step 6: test-scenario.md corrections (no app change)
- B11 «Try»: «Этап закрыт» appears after picking a photo on a next-stage task, not on opening it.
- B7/B9/B16: note that QR/link/photo result cards show base points and quiz results show multiplied points, until F3 is decided.
- A3: «Стенды партнёров» may be missing if `STAND_PIN` was empty at first start; add it in «Доступ».
- B23: /moderate column check: count the columns of `.gc-moderation-grid` (2 at 768 px, 3 at 1024 px+).

### Step 7: re-test
- Re-run only the failed and changed steps on dev: A1, A8 preview, plus any piece touched.
- Then the "Not run" list above, on a real phone.
- Copy the passes into the results checklist at the end of `test-scenario.md`.
