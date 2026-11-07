"""Builds the test kit for the Event Gamification manual test (test-scenario.md), themed on Marketing Forum (mktb.pro).

    python3 make_kit.py [--start "06.11.2026 18:00"] [--out DIR]

--start is when stage 1 begins (Dushanbe time). Stage 1 then runs 4 days, so the kit works whenever you test
in that window; stage 2 (market, x2) and stage 3 (final, no tasks) follow it.
"""
import argparse
import csv
import io
import os
import random
import shutil
from datetime import datetime, timedelta

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

FMT = "%d.%m.%Y %H:%M"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STAGE_COLS = ["Номер", "Название", "Начало", "Конец", "Сообщение при смене этапа", "Маркет", "Карточек в ленте",
              "Множитель"]
TASK_COLS = ["ID", "Этап", "Тип", "Текст", "Баллы", "Монеты", "Партнёр", "Пакет партнёра", "Доступно с",
             "Доступно до", "Выполнение", "Ссылка", "Таймер, сек", "Требует", "Лимит", "Блиц", "Бонус за скорость",
             "Без потерь, сек", "Время бонуса, сек"]
Q_COLS = ["ID задания", "№ вопроса", "Вопрос", "Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4",
          "Правильный (1–4)"]
PRIZE_COLS = ["ID", "Название", "Партнёр", "Цена в монетах", "Количество"]
LEVEL_COLS = ["Название", "Баллов от"]
BADGE_COLS = ["ID", "Название", "Тип правила", "Число", "Тип задания", "Партнёр", "Задание", "Монеты", "На экран"]

GENERAL, HEADLINER, MF, SUPPORT = "Памир Медиа", "Сомон Аналитикс", "Нур Диджитал", "Чинор Принт"
PARTNERS = [(GENERAL, "Генеральный партнёр", "pamir-media"), (HEADLINER, "Хедлайнер", "somon-analytics"),
            (MF, "MF Партнёр", "nur-digital"), (SUPPORT, "Нас поддерживают", "chinor-print")]


def build(start: datetime):
    s1_end = start + timedelta(days=4)
    s2_end = s1_end + timedelta(hours=1)
    s3_end = s2_end + timedelta(hours=1)
    stages = [
        [1, "Утро: открытие форума", start.strftime(FMT), s1_end.strftime(FMT),
         "Добро пожаловать на Marketing Forum! Задания открыты.", None, 5, None],
        [2, "День: маркет открыт", s1_end.strftime(FMT), s2_end.strftime(FMT),
         "Маркет открыт — обменяйте монеты на призы партнёров.", "да", 5, 2],
        [3, "Финал и награждение", s2_end.strftime(FMT), s3_end.strftime(FMT),
         "Финал: подводим итоги и награждаем лучших.", None, 5, None],
    ]
    past_from, past_to = start.strftime(FMT), (start + timedelta(minutes=1)).strftime(FMT)
    soon_to = (start + timedelta(days=3)).strftime(FMT)

    def t(code, stage, typ, text, pts, coins=None, partner="", package="", w_from=None, w_to=None, method=None,
          link=None, timer=None, requires=None, limit=None, blitz=None):
        return [code, stage, typ, text, pts, coins, partner, package or None, w_from, w_to, method, link, timer,
                requires, limit, blitz, None, None, None]

    tasks = [
        # QR (B9, B16)
        t("QR-ENTRY", 1, "Регистрация", "Отсканируйте QR-код у входа в зал Ballroom", 15, method="QR"),
        t("QR-LIMIT", 1, "Территориальное", "Найдите QR-код у кофе-брейка — успеет только один гость", 15,
          method="QR", limit=1),
        t("QR-HALL", 1, "Регистрация", "Отметьтесь в зале Istanbul перед мастер-классом", 10, method="QR"),
        t("QR-PAST", 1, "Территориальное", "QR-код утреннего кофе (окно уже закрыто)", 10, w_from=past_from,
          w_to=past_to, method="QR"),
        # Link (B10, B7 x1.5 → 8)
        t("LINK-SITE", 1, "Регистрация", "Откройте сайт форума mktb.pro и посмотрите программу", 5, method="Ссылка",
          link="https://mktb.pro"),
        # Photo (B11–B13, B15, B7, B18)
        t("PH-SELFIE", 1, "Селфи", "Селфи на фоне баннера Marketing Forum", 10, method="Фото"),
        t("PH-SPEAKER", 1, "Действие", "Фото со спикером после его выступления", 35, method="Фото"),
        t("PH-NETWORK", 1, "Нетворкинг", "Фото с участником из другой компании", 20, method="Фото"),
        t("PH-DOOH", 1, "На внимательность", "Сфотографируйте любой DOOH-экран по дороге на форум", 15,
          method="Фото"),
        t("PH-CRAZY", 1, "Крейзи", "Покажите в кадре «мёртвый интернет» — как вы его себе представляете", 25,
          method="Фото"),
        t("PH-LIMIT", 1, "Селфи", "Первое селфи с ведущим — только для одного гостя", 10, method="Фото", limit=1),
        t("PH-PARTNER", 1, "Действие", f"Сфотографируйтесь у стенда {GENERAL}", 15, partner=GENERAL,
          package="Генеральный партнёр", method="Фото"),
        # Text, photo+text (B14)
        t("TX-INSIGHT", 1, "Действие", "Главная мысль панели про ИИ в коммуникациях — одной фразой", 15,
          method="Текст"),
        t("PT-MASTER", 1, "Действие", "Фото с мастер-класса и одна мысль, которую вы заберёте с собой", 20,
          method="Фото+текст"),
        t("TX-NUR", 1, "Нетворкинг", f"Найдите представителя {MF} и напишите, как зовут его коллегу", 15,
          partner=MF, package="MF Партнёр", method="Текст"),
        t("TX-CHINOR", 1, "Действие", f"Какой печатный продукт вы бы заказали в {SUPPORT}?", 10, partner=SUPPORT,
          package="Нас поддерживают", method="Текст"),
        # Empty «Выполнение» (B10 Try)
        t("NET-SOON", 1, "Нетворкинг", "Обменяйтесь контактами с тремя участниками", 10),
        # Quizzes (B16, B17, B7)
        t("QZ-MAIN", 1, "Квиз", "Квиз по программе форума", 50, method="Квиз", timer=60),
        t("QZ-PARTNER", 1, "Квиз", f"Квиз от {HEADLINER}", 25, partner=HEADLINER, package="Хедлайнер",
          method="Квиз", timer=60),
        t("QZ-HALL", 1, "Квиз", "Квиз зала Istanbul (сначала отметьтесь в зале)", 30, method="Квиз", timer=60,
          requires="QR-HALL"),
        t("QZ-SOON", 1, "Квиз", "Быстрый квиз — окно скоро закроется", 20, w_from=start.strftime(FMT), w_to=soon_to,
          method="Квиз", timer=60),
        t("QZ-BLITZ", 1, "Квиз", "Блиц: маркетинг за 60 секунд", 50, 50, method="Квиз", timer=60, blitz="да"),
        t("QZ-THREE", 1, "Квиз", "Мини-квиз: три вопроса о форуме", 10, method="Квиз", timer=60),
        # Stage 2 (market, x2)
        t("PH-AFTER", 2, "Селфи", "Селфи с командой после обеда", 15, method="Фото"),
        t("MK-PRIZE", 2, "Покупка", "Обменяйте монеты на любой приз в маркете", 10, method="Маркет"),
    ]

    questions = {
        "QZ-MAIN": [
            ("Где проходит Marketing Forum?", ["Hyatt Regency Dushanbe", "Дворец Нации", "Душанбе Плаза",
                                               "Ботанический сад"], 1),
            ("Во сколько начинается главная сцена?", ["09:00", "10:00", "11:00", "12:00"], 2),
            ("Как называется зал мастер-классов?", ["Ballroom", "Istanbul", "Pamir", "Navruz"], 2),
            ("Что означает DOOH?", ["Digital Out-Of-Home", "Direct Online Output Hub", "Digital Online Office Hours",
                                    "Data Out Of Home"], 1),
            ("Какой темы НЕТ в программе главной сцены?", ["«Мёртвый интернет»", "ИИ в медиапланировании",
                                                           "Криптовалюта для брендов", "Эффективность маркетинга"], 3),
        ],
        "QZ-PARTNER": [
            ("Что показывает медиамониторинг?", ["Где и сколько вышла реклама", "Зарплаты в отрасли",
                                                 "Погоду в день кампании", "Курс валют"], 1),
            ("Что такое CTR?", ["Цена за тысячу показов", "Доля кликов от показов", "Число подписчиков",
                                "Доход с клиента"], 2),
        ],
        "QZ-HALL": [
            ("О чём мастер-класс про Lido?", ["ИИ-продавец и автоматизация продаж", "Наружная реклама",
                                              "Бухгалтерия", "Логистика"], 1),
            ("С чего начинают планировать медиабюджет?", ["С выбора подрядчика", "С цели кампании", "С дизайна",
                                                          "С отчёта"], 2),
            ("Целевая аудитория — это…", ["Все жители страны", "Сотрудники компании",
                                          "Люди, на которых направлена реклама", "Конкуренты"], 3),
        ],
        "QZ-SOON": [
            ("Сколько длится доклад на главной сцене?", ["10 минут", "25 минут", "45 минут", "60 минут"], 2),
            ("Сколько панельных дискуссий в программе?", ["Одна", "Две", "Три", "Ни одной"], 2),
            ("Во сколько завершается главная сцена?", ["15:30", "16:00", "17:15", "19:00"], 3),
        ],
        "QZ-BLITZ": [
            ("SMM — это…", ["Маркетинг в соцсетях", "Наружная реклама", "Email-рассылка", "SEO"], 1),
            ("ROI показывает…", ["Охват", "Окупаемость вложений", "Число кликов", "Цену показа"], 2),
            ("KPI — это…", ["Бюджет кампании", "Рекламный формат", "Ключевой показатель эффективности",
                            "Тип баннера"], 3),
            ("CPM — это цена за…", ["Клик", "Продажу", "Лид", "1000 показов"], 4),
            ("Performance-реклама оплачивается за…", ["Время эфира", "Результат", "Размер баннера",
                                                      "Число сотрудников"], 2),
        ],
        "QZ-THREE": [
            ("В каком городе проходит форум?", ["Худжанд", "Душанбе", "Алматы", "Ташкент"], 2),
            ("Какого числа проходит форум?", ["1 декабря", "13 декабря", "31 декабря", "13 ноября"], 2),
            ("На каком языке программа форума?", ["Английский", "Русский", "Узбекский", "Казахский"], 2),
        ],
    }
    prizes = [
        ["PR-NOTE", "Блокнот форума", SUPPORT, 30, 50],
        ["PR-CONSULT", "Разбор медиаплана с экспертом (1 место)", HEADLINER, 40, 1],
        ["PR-YEAR", "Годовая подписка на медиамониторинг", GENERAL, 900, 3],
    ]
    levels = [["Новичок форума", 0], ["Участник", 50], ["Актив", 150], ["Эксперт форума", 300], ["Легенда MF", 500]]
    return stages, tasks, questions, prizes, levels


def qrows(questions):
    return [[code, i, q, *(opts + [None] * (4 - len(opts))), right]
            for code, qs in questions.items() for i, (q, opts, right) in enumerate(qs, 1)]


SEED_BADGES = [["photo_hunter", "Фотоохотник", "Задания", 5, "Фото, Фото+текст", None, None, 0, None],
               ["networker", "Нетворкер", "Все задания типа", None, "Нетворкинг", None, None, 0, None],
               ["erudite", "Эрудит", "Квизы подряд", 5, None, None, None, 0, None],
               ["brand_friend", "Друг бренда", "Задания", 3, None, "Любой один партнёр", None, 0, None],
               ["forum_spirit", "Дух форума", "Бонусы", 1, "Крейзи", None, None, 0, None]]


def workbook(stages, tasks, qs, prizes, levels, badges=None):
    wb = Workbook()
    sheets = [("Этапы", STAGE_COLS, stages), ("Задания", TASK_COLS, tasks), ("Вопросы", Q_COLS, qs),
              ("Призы", PRIZE_COLS, prizes), ("Уровни", LEVEL_COLS, levels)]
    if badges is not None:
        sheets.append(("Бейджи", BADGE_COLS, badges))
    first = True
    for name, cols, rows in sheets:
        ws = wb.active if first else wb.create_sheet(name)
        ws.title, first = name, False
        ws.append(cols)
        for r in rows:
            ws.append(r)
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(10, min(45, len(c) + 4))
        ws.freeze_panes = "A2"
    return wb


def negatives(stages, tasks, qs, prizes, levels):
    """One broken file per A8 «Try» line: (file name, what to expect)."""
    import copy

    def task(code):
        return next(r for r in T if r[0] == code)

    out = []

    def add(name, expect, mutate=None, badges=None, drop_col=None, sheets=None):
        nonlocal S, T, Q, P, L
        S, T, Q, P, L = (copy.deepcopy(x) for x in (stages, tasks, qs, prizes, levels))
        if mutate:
            mutate()
        wb = workbook(S, T, Q, P, L, badges)
        if drop_col:
            ws = wb["Задания"]
            ws.delete_cols(TASK_COLS.index(drop_col) + 1)
        if sheets:
            for s in list(wb.sheetnames):
                if s not in sheets:
                    del wb[s]
        out.append((name, expect, wb))

    S = T = Q = P = L = None
    add("A8-02-no-stages-sheet.xlsx", "«В файле нет: Этапы»", sheets=["Задания", "Вопросы"])
    add("A8-03-no-points-column.xlsx", "«В файле нет: Задания: Баллы»", drop_col="Баллы")
    add("A8-04-no-points.xlsx", "Задания, строка 2: нет баллов", lambda: task("QR-ENTRY").__setitem__(4, None))
    add("A8-05-unknown-type.xlsx", "неизвестный тип задания", lambda: task("QR-ENTRY").__setitem__(2, "Танец"))
    add("A8-06-unknown-stage.xlsx", "нет такого этапа на листе «Этапы»",
        lambda: task("QR-ENTRY").__setitem__(1, 9))
    add("A8-07-duplicate-id.xlsx", "этот ID уже есть выше в файле",
        lambda: task("QR-LIMIT").__setitem__(0, "QR-ENTRY"))
    add("A8-08-bad-time.xlsx", "не понятно время начала", lambda: S[0].__setitem__(2, "завтра утром"))
    add("A8-09-end-before-start.xlsx", "конец раньше начала", lambda: S[0].__setitem__(3, "01.01.2026 09:00"))
    add("A8-10-market-maybe.xlsx", "в столбце «Маркет» напишите «да» или оставьте пусто",
        lambda: S[1].__setitem__(5, "может быть"))
    add("A8-11-link-empty.xlsx", "для «Ссылка» нужна ссылка", lambda: task("LINK-SITE").__setitem__(11, None))
    add("A8-12-link-ftp.xlsx", "ссылка должна начинаться с http:// или https://",
        lambda: task("LINK-SITE").__setitem__(11, "ftp://mktb.pro"))
    add("A8-13-quiz-no-questions.xlsx", "у квиза нет вопросов на листе «Вопросы»",
        lambda: Q.__setitem__(slice(None), [r for r in Q if r[0] != "QZ-THREE"]))
    add("A8-14-bad-requires.xlsx", "в «Требует» укажите ID задания с выполнением «QR»",
        lambda: task("QZ-HALL").__setitem__(13, "PH-SELFIE"))
    add("A8-15-two-packages.xlsx", "у этого партнёра в строке выше другой пакет",
        lambda: task("TX-CHINOR").__setitem__(6, GENERAL))
    add("A8-16-unknown-package.xlsx", "неизвестный пакет партнёра",
        lambda: task("PH-PARTNER").__setitem__(7, "Платиновый"))
    add("A8-17-batch-4.xlsx", "«Карточек в ленте» должно быть целым числом от 5 до 50",
        lambda: S[0].__setitem__(6, 4))
    add("A8-18-levels-not-from-0.xlsx", "первый уровень должен начинаться с 0 баллов",
        lambda: L[0].__setitem__(1, 10))
    add("A8-19-levels-not-increasing.xlsx", "«Баллов от» должно расти сверху вниз",
        lambda: L[2].__setitem__(1, 50))
    add("A8-20-badge-unknown-rule.xlsx", "неизвестный тип правила (старые бейджи остаются)",
        badges=SEED_BADGES + [["bad_rule", "Плохое правило", "Случайно", 1, None, None, None, 0, None]])
    add("A8-21-badge-no-number.xlsx", "нет числа для этого правила",
        badges=SEED_BADGES + [["no_count", "Без числа", "Задания", None, None, None, None, 0, None]])
    add("A8-22-correct-points-to-empty.xlsx", "«Правильный (1–4)» должен быть номером заполненного варианта",
        lambda: next(r for r in Q if r[0] == "QZ-PARTNER").__setitem__(slice(3, 8), ["Да", "Нет", None, None, 4]))
    add("A8-23-one-option.xlsx", "нужно от 2 до 4 вариантов",
        lambda: next(r for r in Q if r[0] == "QZ-PARTNER").__setitem__(slice(3, 8), ["Да", None, None, None, 1]))
    add("A8-24-blitz-on-photo.xlsx", "«Блиц» — только для квиза", lambda: task("PH-SELFIE").__setitem__(15, "да"))
    add("A8-25-grace-equals-bonus.xlsx", "«Без потерь, сек» должно быть меньше, чем «Время бонуса, сек»",
        lambda: task("QZ-BLITZ").__setitem__(slice(17, 19), [12, 12]))
    add("A8-26-prize-qty-0-after-B20.xlsx", "(только после покупки в B20) количество меньше, чем уже куплено",
        lambda: P[0].__setitem__(4, 0))
    return out


GUESTS = [
    ("MF-001", "Каримов", "Фаррух", "+992 90 100 00 01", "Агентство «Ракурс»", "да"),
    ("MF-002", "Рахимова", "Нигина", "+992 90 100 00 02", "Банк «Сарвари»", "да"),
    ("MF-003", "Шарипов", "Бахтиёр", "+992 90 100 00 03", "Ракурс Медиа", "да"),
    ("MF-004", "Назарова", "Мадина", "+992 90 100 00 04", "Интернет-магазин «Бозор»", "да"),
    ("MF-005", "Холов", "Сухроб", "+992 90 100 00 05", "Строительная компания «Девор»", "да"),
    ("MF-006", "Юсупова", "Зарина", "+992 90 100 00 06", "Кофейня «Чашма»", "да"),
    ("MF-007", "Мирзоев", "Шохин", "+992 90 100 00 07", "Студия SMM «Пост»", "да"),
    ("MF-008", "Олимова", "Тахмина", "+992 90 100 00 08", "Страховая «Сипар»", "да"),
    ("MF-009", "Давлатов", "Рустам", "+992 90 100 00 09", "Логистика «Карвон»", "да"),
    ("MF-010", "Сафарова", "Парвина", "+992 90 100 00 10", "Агентство «Ракурс»", "да"),
    ("MF-011", "Ҷӯраев", "Ғайрат", "+992 90 100 00 11", "Тоҷик Диҷитал", "да"),
    ("MF-012", "Абдуллоев", "Далер", "+992 90 100 00 12", "Оргкомитет форума", "нет"),
]
GUEST_HEAD = ["ID регистрации", "Фамилия", "Имя", "Телефон", "Компания", "В рейтинге"]


def write_csv(path, head, rows, encoding="utf-8-sig"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(head)
        w.writerows(rows)


def logo(path, text, color, fmt="PNG", size=(600, 300)):
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 44)
    w = d.textlength(text, font=font)
    d.text(((size[0] - w) / 2, size[1] / 2 - 26), text, font=font, fill="white")
    d.rectangle([12, 12, size[0] - 12, size[1] - 12], outline="white", width=4)
    img.save(path, fmt, **({"quality": 90} if fmt == "JPEG" else {}))


def photo(path, label, color, size=(1280, 960)):
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for _ in range(60):
        x, y = random.randrange(size[0]), random.randrange(size[1])
        r = random.randrange(20, 160)
        d.ellipse([x, y, x + r, y + r], fill=tuple(random.randrange(256) for _ in range(3)))
    font = ImageFont.truetype(FONT, 64)
    d.rectangle([0, size[1] - 120, size[0], size[1]], fill="black")
    d.text((40, size[1] - 100), label, font=font, fill="white")
    img.save(path, "JPEG", quality=88)


def big_gps_photo(path):
    """A ~6 MB 'phone photo' with GPS EXIF (C2 checks the app shrinks it to 1600 px and strips EXIF)."""
    import piexif
    w, h = 4032, 3024
    img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3)).resize((w // 4, h // 4)).resize((w, h))
    noise = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    img = Image.blend(img, noise, 0.24)
    d = ImageDraw.Draw(img)
    d.text((80, 80), "C2: 4032x3024 + GPS", font=ImageFont.truetype(FONT, 160), fill="white")
    dms = lambda v: ((int(v), 1), (int(v * 60 % 60), 1), (int(v * 3600 % 60 * 100), 100))
    exif = {"0th": {piexif.ImageIFD.Make: b"TestPhone", piexif.ImageIFD.Model: b"Kit C2"},
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: dms(38.5737),
                    piexif.GPSIFD.GPSLongitudeRef: b"E", piexif.GPSIFD.GPSLongitude: dms(68.7738)}}
    q = 95
    while True:
        img.save(path, "JPEG", quality=q, exif=piexif.dump(exif))
        mb = os.path.getsize(path) / 1e6
        if mb <= 7 or q <= 60:
            break
        q -= 5
    return mb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="06.11.2026 18:00")
    ap.add_argument("--out", default="gamify-test-kit")
    a = ap.parse_args()
    start = datetime.strptime(a.start, FMT)
    random.seed(7)
    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    for sub in ("logos", "photos", "negative"):
        os.makedirs(os.path.join(out, sub))

    stages, tasks, questions, prizes, levels = build(start)
    qs = qrows(questions)
    workbook(stages, tasks, qs, prizes, levels).save(os.path.join(out, "tasks.xlsx"))

    with open(os.path.join(out, "negative", "A8-01-not-an-xlsx.xlsx"), "w") as f:
        f.write("Это не Excel-файл\n")
    for name, _, wb in negatives(stages, tasks, qs, prizes, levels):
        wb.save(os.path.join(out, "negative", name))

    write_csv(os.path.join(out, "guests.csv"), GUEST_HEAD, GUESTS)
    # Same list in Windows-1251, minus the Tajik letters 1251 can't hold (uploading it after guests.csv = no changes
    # only for MF-001…010; MF-011 is left out on purpose)
    write_csv(os.path.join(out, "negative", "A15-guests-cp1251.csv"), GUEST_HEAD, GUESTS[:10] + GUESTS[11:],
              encoding="cp1251")
    write_csv(os.path.join(out, "negative", "A15-no-id-column.csv"), ["Фамилия", "Имя", "Телефон"],
              [g[1:4] for g in GUESTS[:3]])
    write_csv(os.path.join(out, "negative", "A15-bad-rows.csv"), GUEST_HEAD,
              [GUESTS[0], ("", "Безномеров", "Олим", "+992 90 100 00 99", "Тест", "да"),
               ("MF-098", "Безымянный", "", "+992 90 100 00 98", "Тест", "да"), GUESTS[0]])

    colors = ["#1f4e79", "#7b2d26", "#2e6b3a", "#5b3d8a"]
    for (name, _, slug), c in zip(PARTNERS, colors):
        logo(os.path.join(out, "logos", f"{slug}.png"), name, c)
    logo(os.path.join(out, "logos", f"{PARTNERS[1][2]}.jpg"), HEADLINER, colors[1], "JPEG")
    big = Image.frombytes("RGB", (1200, 1200), os.urandom(1200 * 1200 * 3))
    big.save(os.path.join(out, "logos", "too-big-over-1mb.png"))
    with open(os.path.join(out, "logos", "wrong-format.svg"), "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" '
                'fill="#333"/><text x="20" y="60" fill="#fff" font-size="28">SVG logo</text></svg>')
    Image.new("RGB", (200, 100), "#888").save(os.path.join(out, "logos", "wrong-format.gif"))

    for i, c in enumerate(["#2d6a8f", "#a0522d", "#3b7d4f", "#6d4c8d", "#8f2d56", "#2d8f86", "#8f7a2d",
                           "#44546a"], 1):
        photo(os.path.join(out, "photos", f"photo-{i:02d}.jpg"), f"Тестовое фото {i}", c)
    mb = big_gps_photo(os.path.join(out, "photos", "C2-phone-6mb-gps.jpg"))
    with open(os.path.join(out, "photos", "not-an-image.jpg"), "w") as f:
        f.write("Это текст, а не фото\n")
    print(f"kit in {out}; big photo {mb:.1f} MB")


if __name__ == "__main__":
    main()
