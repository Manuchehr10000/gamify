# Test kit: Marketing Forum (mktb.pro) on the dev deploy

Every file here was run through the app's own importer (`task_file.import_xlsx`, `guest_list.import_csv`, branch `dev`) on a fresh database before delivery.

## Timing (Dushanbe time)
| Stage | Name | Start | End | Notes |
|---|---|---|---|---|
| 1 | Утро: открытие форума | 06.11.2026 18:00 | 10.11.2026 18:00 | All Part B task checks run here |
| 2 | День: маркет открыт | 10.11.2026 18:00 | 10.11.2026 19:00 | «Маркет» = да, ×2, 2 tasks. You start it by hand in B20 |
| 3 | Финал и награждение | 10.11.2026 19:00 | 10.11.2026 20:00 | No tasks: shows «Задания этого этапа скоро появятся» |

Stage 1 lasts four days, so the kit works whenever you test before Tuesday evening. To move it, run `python3 make_kit.py --start "DD.MM.YYYY HH:MM"`, or edit the three rows in «Этапы» plus «Доступно с/до» of QR-PAST and QZ-SOON.

## Files → steps
| File | Step |
|---|---|
| `logos/pamir-media.png`, `chinor-print.png` | A4. Create partners with these exact names: **Памир Медиа** = «Генеральный партнёр», **Чинор Принт** = «Нас поддерживают». The tasks file then matches them by name. |
| `logos/somon-analytics.png/.jpg`, `nur-digital.png` | A4 after A8: the file creates **Сомон Аналитикс** (Хедлайнер) and **Нур Диджитал** (MF Партнёр). Upload their logos too. |
| `logos/too-big-over-1mb.png`, `wrong-format.svg`, `wrong-format.gif` | A4 Try |
| `tasks.xlsx` | A8 (main upload) |
| `negative/A8-01…A8-25` | A8 Try: each file is refused whole, and the file name says which error to expect |
| `negative/A8-20`, `A8-21` | Contain a «Бейджи» sheet. They are refused, so your badges stay as they are |
| `negative/A8-26-prize-qty-0-after-B20.xlsx` | Only after a guest buys «Блокнот форума» in B20. Before that it **applies** and hides nothing, but sets that prize's stock to 0 |
| `guests.csv` | A15. Guest A = MF-001 Фаррух Каримов, guest B = MF-002 Нигина Рахимова. MF-012 Далер Абдуллоев has «В рейтинге» = нет. MF-011 Ғайрат Ҷӯраев checks the Tajik letters (A6) |
| `negative/A15-no-id-column.csv`, `A15-bad-rows.csv` | A15 Try |
| `negative/A15-guests-cp1251.csv` | Windows-1251 version: after guests.csv it shows «Изменений нет». MF-011 is left out on purpose because Windows-1251 can't hold ҷ, ғ, ӯ |
| `photos/photo-01…08.jpg` | B11–B15 on a laptop (each guest can send each task once) |
| `photos/not-an-image.jpg` | B11 Try: «Не получилось открыть фото» |
| `photos/C2-phone-6mb-gps.jpg` | Send it as the **PH-PARTNER** photo in B12, then accept it. In C2 the downloaded file must be ≤1600 px with no GPS/EXIF data |

The tasks file has **no «Бейджи» sheet** on purpose. A sheet would switch off every badge it leaves out. Badges are set up in the form (A12).

## Task map (stage 1 unless noted)
| ID | Type / done by | Pts | Coins | Used in |
|---|---|---|---|---|
| QR-ENTRY | Регистрация / QR | 15 | 15 | B9 plain: «+15 баллов», «+15 монет» |
| QR-LIMIT | QR, «Лимит» 1 | 15 | 15 | B9 Try: guest B first, then A gets «Лимит исчерпан». Raise to 2 in A13 |
| QR-HALL | QR | 10 | 10 | B16 hall check-in: opens QZ-HALL. Don't scan it before B16 |
| QR-PAST | QR, window already closed | 10 | 10 | B9 Try: «Это задание сейчас недоступно» |
| LINK-SITE | Ссылка → https://mktb.pro | 5 | 5 | B10; B7: at ×1.5 it pays **8** |
| PH-SELFIE, PH-NETWORK, PH-DOOH | Фото | 10 / 20 / 15 | same | B11, B12, B13, B15 |
| PH-SPEAKER | Фото | 35 | 35 | B12/B7 «Бонус +50%»: +18 at ×1, +35 at ×2 |
| PH-CRAZY | Крейзи / Фото | 25 | 25 | «Бонус +50%» on it earns the seeded «Дух форума» badge |
| PH-LIMIT | Фото, «Лимит» 1 | 10 | 10 | B9 Try (limited photo + «Отклонить со штрафом») |
| PH-PARTNER | Фото, Памир Медиа (General) | 15 | **23** | B5, C1, C2. Coins come from the ×1.5 rule (A14) |
| TX-INSIGHT | Текст | 15 | 15 | B14 |
| PT-MASTER | Фото+текст | 20 | 20 | B14 |
| TX-NUR | Текст, Нур Диджитал (MF) | 15 | 23 | B5 feed order by package |
| TX-CHINOR | Текст, Чинор Принт (Supporters) | 10 | 15 | B5 feed order by package |
| NET-SOON | empty «Выполнение» | 10 | 10 | B10 Try: «Выполнить — скоро» |
| QZ-MAIN | Квиз, 5 q, 60 s | 50 | 50 | B16: 3 of 5 → «+30 баллов, +30 монет» |
| QZ-PARTNER | Квиз, 2 q, Сомон Аналитикс (Headliner) | 25 | **38** | B16: «2 из 2 · +25 баллов, +38 монет» |
| QZ-HALL | Квиз, 3 q, «Требует» QR-HALL | 30 | 30 | B16 gate: «Сначала отметьтесь в зале» |
| QZ-SOON | Квиз, 3 q, window until 09.11 18:00 | 20 | 20 | B16 window. **Before B16, set its «Доступно до» to now + 15 min** in «Задания» |
| QZ-BLITZ | Квиз, blitz, 5 q, bonus 20/3/12 | 50 | 50 | B17, A11 lock |
| QZ-THREE | Квиз, 3 q | 10 | 10 | B7: 1 of 3 at ×1 → 4 points |
| PH-AFTER | stage 2, Фото | 15 | 15 | B11 Try «Этап закрыт» (open /app/tasks/{id}) |
| MK-PRIZE | stage 2, Покупка / Маркет | 10 | 10 | B20 (done once on purchase), B23 |

Stage 1 has 23 tasks and «Карточек в ленте» = 5. For B8's exact batches (1–5, 6–10…), the scenario wants exactly 12 tasks with no window tasks. This kit doesn't meet that, so check the rotation rules only, not the exact batch numbers.

## Prizes (B20)
| ID | Prize | Partner | Price | Qty |
|---|---|---|---|---|
| PR-NOTE | Блокнот форума | Чинор Принт | 30 | 50 → profile shows «−30 монет» |
| PR-CONSULT | Разбор медиаплана с экспертом (1 место) | Сомон Аналитикс | 40 | 1 → race check |
| PR-YEAR | Годовая подписка на медиамониторинг | Памир Медиа | 900 | 3 → «Не хватает N монет» |

Levels are the standard five: Новичок форума 0 · Участник 50 · Актив 150 · Эксперт форума 300 · Легенда MF 500.

## Quiz answers (the app shuffles the order, so pick by text)
**QZ-MAIN** (for 3 of 5, answer 1–3 right and 4–5 wrong): 1 Hyatt Regency Dushanbe · 2 10:00 · 3 Istanbul · 4 Digital Out-Of-Home · 5 Криптовалюта для брендов
**QZ-PARTNER**: 1 Где и сколько вышла реклама · 2 Доля кликов от показов
**QZ-HALL**: 1 ИИ-продавец и автоматизация продаж · 2 С цели кампании · 3 Люди, на которых направлена реклама
**QZ-SOON**: 1 25 минут · 2 Две · 3 17:15
**QZ-THREE** (for B7, get only Q1 right): 1 Душанбе · 2 13 декабря · 3 Русский
**QZ-BLITZ** (B17 plan): Q1 Маркетинг в соцсетях — **within 2 s** · Q2 Окупаемость вложений — **at about 7.5 s** · Q3 Ключевой показатель эффективности — **after 12 s** · Q4 CPM: **answer wrong on purpose** (correct is 1000 показов) · Q5 Результат — quickly. Expect «4 из 5 · +40 баллов, +40 монет · +50 за скорость».

## Things the files can't set up
- Accounts and PINs: set in «Доступ» (A3).
- Badges for A12/B18 (Фотоохотник 5→1, Эрудит «Квизы подряд» 2, «Место» 1, «Первые N» 1 on PH-SELFIE): set them in the form.
- Settings: «Баллы за приход» = 10, «Множитель монет партнёрских заданий» = 1.5. The 23 and 38 coin values assume 1.5.
- Clock-driven «Эфир» (A17): the last stage ends 10.11 20:00, and the setting allows at most 120 min. To check it earlier, move stage 3's «Начало/Конец» (and stage 2's «Конец») close to now, then move them back.
- Uploading tasks.xlsx and guests.csv **replaces the dev data for everyone** using dev.
