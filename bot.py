import logging
import json
import os
from datetime import datetime, timezone
from aiohttp import web
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN = "8173562858:AAGy1aRrvBuUO1ebS8Q_0krdpexdxFWGu8M"
MINI_APP_URL = "https://veronickaapp.lovable.app"
CONSULTATION_URL = "https://t.me/pa_nicka"
CHANNEL_URL = "https://t.me/potom_podumay"
YOUR_TELEGRAM_ID = 451210923
API_PORT = 8080
# ─────────────────────────────────────────────

GUIDE_FILE_ID = None
DB_FILE = "users.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


# ═══════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_returning_user(user_id: int) -> bool:
    db = load_db()
    return str(user_id) in db

def save_user(user_id: int):
    db = load_db()
    if str(user_id) not in db:
        db[str(user_id)] = {
            "first_seen": datetime.now().isoformat(),
            "notifications_enabled": True
        }
        save_db(db)


# ═══════════════════════════════════════════════
# ТЕКСТЫ — КАРТОЧКИ "ЧТО ДАЁТ ТЕРАПИЯ"
# ═══════════════════════════════════════════════

THERAPY_CARDS = [
    "1/6  Терапия — это не советы и не инструкции. Психолог не говорит, что делать. Он помогает понять, почему вы снова и снова оказываетесь в одной и той же точке.",
    "2/6  В терапии можно говорить то, что неловко говорить близким. Без страха быть осуждённым, неправильно понятым или обременить другого человека.",
    "3/6  Со временем становится легче замечать свои реакции до того, как они уже произошли. Это не контроль — это понимание себя.",
    "4/6  Тревога, усталость, сложности в отношениях — это редко про одну причину. Терапия помогает разобраться в том, что стоит за поверхностью.",
    "5/6  Изменения в терапии происходят постепенно. Не после одной сессии. Но в какой-то момент замечаешь, что реагируешь иначе — и это уже твоё, а не результат чьего-то совета.",
    "6/6  Первая сессия с Вероникой — это знакомство. Полчаса, чтобы рассказать о своём запросе и понять, подходит ли такой формат работы. Без обязательств.",
]


# ═══════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════

def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Хочу разобраться в своём запросе", callback_data="choose_branch")],
        [InlineKeyboardButton("Написать Веронике напрямую", url=CONSULTATION_URL)],
    ])

def kb_returning():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Выбрать тему", callback_data="choose_branch")],
        [InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Написать Веронике", url=CONSULTATION_URL)],
    ])

def kb_branches():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Тревога и страхи", callback_data="branch_anxiety")],
        [InlineKeyboardButton("Отношения и одиночество", callback_data="branch_relations")],
        [InlineKeyboardButton("Усталость и апатия", callback_data="branch_fatigue")],
        [InlineKeyboardButton("Что-то не так, но не могу понять что", callback_data="branch_unclear")],
    ])

def kb_anxiety_clarify():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Больше чувствую это в теле", callback_data="anxiety_body")],
        [InlineKeyboardButton("Больше мысли, которые не останавливаются", callback_data="anxiety_mind")],
        [InlineKeyboardButton("И то и другое примерно поровну", callback_data="anxiety_both")],
    ])

def kb_relations_clarify():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сложности с конкретным человеком", callback_data="relations_person")],
        [InlineKeyboardButton("Чувствую себя одиноко, даже когда не один(а)", callback_data="relations_lonely")],
        [InlineKeyboardButton("Не понимаю, чего хочу от отношений", callback_data="relations_unclear")],
    ])

def kb_fatigue_clarify():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Нет сил, всё даётся с трудом", callback_data="fatigue_nopower")],
        [InlineKeyboardButton("Ничего не хочется, интерес пропал", callback_data="fatigue_noint")],
        [InlineKeyboardButton("Всё нормально, но внутри что-то не так", callback_data="fatigue_empty")],
    ])

def kb_unclear_clarify():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Одни и те же ситуации повторяются", callback_data="unclear_repeat")],
        [InlineKeyboardButton("Живу не так, как хочу, но не понимаю как иначе", callback_data="unclear_lost")],
        [InlineKeyboardButton("Просто хочу лучше понимать себя", callback_data="unclear_selfknow")],
    ])

def kb_after_practice():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Узнать, что даёт терапия", callback_data="therapy_cards")],
        [InlineKeyboardButton("Написать Веронике", url=CONSULTATION_URL)],
        [InlineKeyboardButton("Задать анонимный вопрос", web_app=WebAppInfo(url=MINI_APP_URL))],
    ])

def kb_after_practice_unclear():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Задать вопрос Веронике анонимно", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Написать Веронике напрямую", url=CONSULTATION_URL)],
        [InlineKeyboardButton("Узнать, что даёт терапия", callback_data="therapy_cards")],
    ])

def kb_therapy_next(card_index: int):
    buttons = []
    if card_index < len(THERAPY_CARDS) - 1:
        buttons.append([InlineKeyboardButton("Дальше →", callback_data=f"therapy_{card_index + 1}")])
    buttons.append([InlineKeyboardButton("Написать Веронике", url=CONSULTATION_URL)])
    return InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════
# КОМАНДА /start
# ═══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    returning = is_returning_user(user_id)
    save_user(user_id)

    if returning:
        await update.message.reply_text(
            "Рада, что ты снова здесь.\n\nС чего начнём?",
            reply_markup=kb_returning()
        )
    else:
        await update.message.reply_text(
            "Привет. Это бот Вероники Пахомовой, психолога, которая работает с тревогой, отношениями и тем, что мешает чувствовать себя хорошо.\n\n"
            "Здесь можно разобраться в том, что происходит, попробовать практики под свой запрос и при желании выйти на связь с Вероникой.\n\n"
            "С чего начнём?",
            reply_markup=kb_start()
        )


# ═══════════════════════════════════════════════
# ОБРАБОТЧИК CALLBACK-КНОПОК
# ═══════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Выбор ветки ──────────────────────────────
    if data == "choose_branch":
        await query.message.reply_text(
            "Что сейчас мешает жить спокойно?",
            reply_markup=kb_branches()
        )

    # ── Ветка: Тревога ───────────────────────────
    elif data == "branch_anxiety":
        await query.message.reply_text(
            "Тревога редко приходит с понятной причиной. Чаще это фоновое ощущение, что что-то пойдёт не так.\n\n"
            "Иногда тело реагирует раньше, чем успеваешь понять, что именно случилось: напрягаются плечи, сбивается дыхание, сердце начинает биться чуть быстрее.\n\n"
            "Иногда это мысли, которые крутятся по кругу и не дают остановиться.\n\n"
            "Уточни, пожалуйста.",
            reply_markup=kb_anxiety_clarify()
        )

    elif data == "anxiety_body":
        await query.message.reply_text(
            "Когда тревога живёт в теле, первое что помогает — это вернуть себе ощущение почвы под ногами. "
            "Не анализировать, не разбираться с причинами, а просто немного стабилизироваться.\n\n"
            "В приложении есть три практики, которые хорошо работают именно с этим.\n\n"
            "Заземление 5-4-3-2-1 помогает вернуться в настоящий момент через ощущения. "
            "Дыхание 4-7-8 замедляет нервную систему. "
            "Прогрессивная релаксация снимает напряжение из мышц, которое накапливается незаметно.\n\n"
            "Попробуй начать с любой из них прямо сейчас.",
            reply_markup=kb_after_practice()
        )

    elif data == "anxiety_mind":
        await query.message.reply_text(
            "Когда голова не останавливается, обычно помогает не успокоиться, а разобрать то, что крутится. "
            "Вытащить мысль наружу и посмотреть на неё чуть со стороны.\n\n"
            "В приложении для этого есть Дневник мыслей, Декатастрофизация и За и против. "
            "Они устроены так, чтобы не давать советов, а помочь тебе самому(-ой) увидеть картину чуть чётче.",
            reply_markup=kb_after_practice()
        )

    elif data == "anxiety_both":
        await query.message.reply_text(
            "Это частое сочетание. Тело напряжено, голова работает вхолостую, и они друг друга раскручивают.\n\n"
            "Попробуй начать с тела — когда немного снижается физическое напряжение, мысли тоже становятся чуть тише. "
            "Дыхание 4-7-8 или Заземление 5-4-3-2-1 как первый шаг. "
            "Потом, если захочется, Дневник мыслей или Декатастрофизация.",
            reply_markup=kb_after_practice()
        )

    # ── Ветка: Отношения ─────────────────────────
    elif data == "branch_relations":
        await query.message.reply_text(
            "Отношения — это одна из самых сложных тем, потому что в них всегда двое, а разбираться приходится в одиночку.\n\n"
            "Иногда это усталость от конфликтов, которые повторяются по одному сценарию. "
            "Иногда ощущение, что тебя не слышат, или что ты сам(а) не можешь сказать то, что важно. "
            "Иногда просто одиноко, даже когда люди рядом есть.\n\n"
            "Что ближе к тому, что происходит у тебя?",
            reply_markup=kb_relations_clarify()
        )

    elif data == "relations_person":
        await query.message.reply_text(
            "Когда есть напряжение с кем-то конкретным, обычно помогает сначала разобраться в своей части. "
            "Не в том, кто прав, а в том, что именно тебя задевает и почему.\n\n"
            "В приложении для этого есть Дневник мыслей и За и против. "
            "Дневник помогает вытащить наружу то, что крутится внутри. "
            "За и против помогает увидеть ситуацию чуть шире, когда кажется, что выхода нет.",
            reply_markup=kb_after_practice()
        )

    elif data == "relations_lonely":
        await query.message.reply_text(
            "Это особенный вид одиночества. Он часто связан не с количеством людей вокруг, "
            "а с тем, насколько ты можешь быть собой рядом с ними.\n\n"
            "Попробуй Дневник мыслей — не чтобы найти ответ, а чтобы просто побыть с тем, что есть. "
            "Иногда это первый шаг к тому, чтобы понять, чего на самом деле не хватает.",
            reply_markup=kb_after_practice()
        )

    elif data == "relations_unclear":
        await query.message.reply_text(
            "Это честный запрос. Часто мы знаем, что что-то не так, но не можем сформулировать что именно.\n\n"
            "В приложении есть За и против и Дневник мыслей. "
            "Они не дадут готового ответа, но помогут начать разбираться. "
            "Иногда этого достаточно, чтобы что-то сдвинулось.",
            reply_markup=kb_after_practice()
        )

    # ── Ветка: Усталость ─────────────────────────
    elif data == "branch_fatigue":
        await query.message.reply_text(
            "Усталость, которая не проходит после отдыха — это отдельное состояние. Не лень и не слабость.\n\n"
            "Просто в какой-то момент сил становится меньше, чем нужно, и непонятно откуда их взять. "
            "Иногда пропадает интерес к тому, что раньше нравилось. "
            "Иногда всё как будто идёт нормально, но внутри пусто.\n\n"
            "Что из этого ближе?",
            reply_markup=kb_fatigue_clarify()
        )

    elif data == "fatigue_nopower":
        await query.message.reply_text(
            "Когда сил мало, важно не требовать от себя больше, чем есть. "
            "Первый шаг — небольшое действие, которое даёт ощущение, что ты не стоишь на месте.\n\n"
            "В приложении есть Поведенческая активация — практика, которая помогает постепенно возвращать себе активность без давления. "
            "И Заряд поддержки — короткое упражнение для тех дней, когда совсем тяжело.",
            reply_markup=kb_after_practice()
        )

    elif data == "fatigue_noint":
        await query.message.reply_text(
            "Когда пропадает интерес, иногда это сигнал, что что-то важное долго игнорировалось. "
            "Не обязательно что-то серьёзное, просто накопилось.\n\n"
            "Попробуй Дневник мыслей — без задачи что-то решить, просто записать, что есть. "
            "И Поведенческая активация помогает нащупать хотя бы небольшое действие, от которого становится чуть лучше.",
            reply_markup=kb_after_practice()
        )

    elif data == "fatigue_empty":
        await query.message.reply_text(
            "Это состояние трудно объяснить другим, потому что внешне всё выглядит нормально. "
            "Но ты сам(а) чувствуешь, что что-то не так — и этого достаточно, чтобы разобраться.\n\n"
            "Начни с трекера настроения в приложении — он помогает замечать, в какие моменты становится лучше или хуже. "
            "Иногда это первая подсказка о том, что именно влияет на состояние.",
            reply_markup=kb_after_practice()
        )

    # ── Ветка: Не понимаю что ────────────────────
    elif data == "branch_unclear":
        await query.message.reply_text(
            "Иногда нет конкретной проблемы, но есть ощущение, что что-то идёт не так. "
            "Или что живёшь немного не своей жизнью. "
            "Или просто хочется понять себя лучше — почему реагируешь именно так, почему одни ситуации повторяются, чего на самом деле хочешь.\n\n"
            "Это не менее важный запрос, чем любой другой.\n\n"
            "Расскажи немного больше. Что сейчас вызывает это ощущение?",
            reply_markup=kb_unclear_clarify()
        )

    elif data == "unclear_repeat":
        await query.message.reply_text(
            "Когда что-то повторяется, обычно есть паттерн, который сложно увидеть изнутри. "
            "Не потому что ты его не замечаешь, а потому что он кажется нормой.\n\n"
            "Начни с Дневника мыслей — записывай, что происходит в моменты, которые тебя задевают. "
            "Не чтобы анализировать, а просто фиксировать. "
            "Со временем начинают проявляться связи, которые раньше не были заметны.\n\n"
            "Также в приложении есть анонимные вопросы к Веронике. "
            "Если что-то конкретное не даёт покоя — можно спросить там.",
            reply_markup=kb_after_practice_unclear()
        )

    elif data == "unclear_lost":
        await query.message.reply_text(
            "Это ощущение появляется, когда между тем, что есть, и тем, чего хочется, накапливается расстояние. "
            "Иногда это про работу, иногда про отношения, иногда просто про то, как проходят дни.\n\n"
            "Практика За и против помогает разложить по полочкам конкретную ситуацию, если она есть. "
            "Если ситуация размытая — начни с Дневника мыслей. "
            "Иногда нужно просто дать себе место, чтобы это сформулировать.",
            reply_markup=kb_after_practice_unclear()
        )

    elif data == "unclear_selfknow":
        await query.message.reply_text(
            "Хорошая отправная точка — трекер настроения. "
            "Он помогает замечать, что влияет на твоё состояние, и постепенно выстраивать картину.\n\n"
            "Если хочется копнуть глубже — в приложении есть Дневник мыслей и Декатастрофизация. "
            "И анонимные вопросы к Веронике, если что-то конкретное хочется спросить у специалиста.",
            reply_markup=kb_after_practice_unclear()
        )

    # ── Карточки "Что даёт терапия" ──────────────
    elif data == "therapy_cards":
        await query.message.reply_text(
            THERAPY_CARDS[0],
            reply_markup=kb_therapy_next(0)
        )

    elif data.startswith("therapy_"):
        index = int(data.split("_")[1])
        if index < len(THERAPY_CARDS):
            await query.message.reply_text(
                THERAPY_CARDS[index],
                reply_markup=kb_therapy_next(index)
            )

    # ── Скачать гайд ─────────────────────────────
    elif data == "download_guide":
        user_id = query.from_user.id
        if not GUIDE_FILE_ID:
            await query.message.reply_text("Гайд скоро появится здесь. Следи за обновлениями.")
            return
        await query.message.reply_document(
            document=GUIDE_FILE_ID,
            caption="7 шагов для преодоления прокрастинации 📎"
        )
        db = load_db()
        if str(user_id) not in db:
            save_user(user_id)


# ═══════════════════════════════════════════════
# API-СЕРВЕР
# ═══════════════════════════════════════════════

async def handle_notifications(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        enabled = bool(data.get("enabled", True))
        if not user_id:
            return web.json_response({"ok": False, "error": "user_id required"}, status=400)
        db = load_db()
        if user_id not in db:
            db[user_id] = {"notifications_enabled": enabled}
        else:
            db[user_id]["notifications_enabled"] = enabled
        save_db(db)
        return web.json_response({"ok": True, "notifications_enabled": enabled})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def handle_notifications_status(request):
    user_id = str(request.rel_url.query.get("user_id", ""))
    if not user_id:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    db = load_db()
    enabled = db.get(user_id, {}).get("notifications_enabled", True)
    return web.json_response({"ok": True, "notifications_enabled": enabled})

async def handle_mood_checkin(request):
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        date = data.get("date")
        if not user_id or not date:
            return web.json_response({"ok": False, "error": "user_id and date required"}, status=400)
        db = load_db()
        if user_id not in db:
            db[user_id] = {}
        db[user_id]["last_checkin"] = date
        save_db(db)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

async def start_api_server():
    app = web.Application()
    app.router.add_post("/notifications", handle_notifications)
    app.router.add_get("/notifications", handle_notifications_status)
    app.router.add_post("/mood-checkin", handle_mood_checkin)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    logging.info(f"API-сервер запущен на порту {API_PORT}")


# ═══════════════════════════════════════════════
# НАПОМИНАНИЯ О НАСТРОЕНИИ
# ═══════════════════════════════════════════════

MOOD_REMINDER_TEXTS = [
    "Привет 🌙 Ты сегодня ещё не проверял(а) своё состояние.\n\nПара минут сейчас — и день завершится осознаннее.",
    "Вечер — хорошее время остановиться на минуту 🌿\n\nКак ты сегодня? Зафиксируй своё состояние — это занимает меньше минуты.",
    "Маленькое напоминание 💙\n\nСегодняшняя запись настроения ещё не сделана. Загляни в приложение, когда будет момент.",
]

async def check_mood_reminders(context: ContextTypes.DEFAULT_TYPE):
    import random
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Отметить состояние", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])
    for user_id_str, data in db.items():
        if not data.get("notifications_enabled", True):
            continue
        if data.get("last_checkin") == today:
            continue
        try:
            text = random.choice(MOOD_REMINDER_TEXTS)
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=text,
                reply_markup=keyboard
            )
        except Exception as e:
            logging.warning(f"Ошибка напоминания пользователю {user_id_str}: {e}")


# ═══════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ КОМАНДЫ
# ═══════════════════════════════════════════════

HELP_TEXT = """Вот что есть в этом боте

Практики и инструменты — приложение открывается прямо в Telegram. Есть упражнения для расслабления, работы с мыслями и восстановления энергии, трекер настроения и анонимные вопросы к Веронике.

Гайд — бесплатный материал «7 шагов от прокрастинации».

Консультация — индивидуальная работа в формате серии сессий. Если хочешь разобраться в своей ситуации глубже — напиши Веронике напрямую.

Если что-то не работает — пиши @pa_nicka"""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Скачать гайд", callback_data="download_guide")],
        [InlineKeyboardButton("Написать Веронике", url=CONSULTATION_URL)],
    ])
    await update.message.reply_text(HELP_TEXT, reply_markup=keyboard)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return
    db = load_db()
    total = len(db)
    with_guide = len([u for u in db.values() if "downloaded_at" in u])
    notifications_off = len([u for u in db.values() if not u.get("notifications_enabled", True)])
    await update.message.reply_text(
        f"Статистика\n\n"
        f"Всего пользователей: {total}\n"
        f"Скачали гайд: {with_guide}\n"
        f"Отключили уведомления: {notifications_off}"
    )

async def upload_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return
    await update.message.reply_text("Жду PDF файл — отправь его следующим сообщением 📎")
    context.user_data["waiting_for_guide"] = True

async def receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return
    if not context.user_data.get("waiting_for_guide"):
        return
    context.user_data["waiting_for_guide"] = False
    global GUIDE_FILE_ID
    file_id = update.message.document.file_id
    GUIDE_FILE_ID = file_id
    config = {}
    if os.path.exists("config.json"):
        with open("config.json") as f:
            config = json.load(f)
    config["guide_file_id"] = file_id
    with open("config.json", "w") as f:
        json.dump(config, f)
    await update.message.reply_text("Гайд сохранён и сразу доступен пользователям.")

async def test_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return
    await update.message.reply_text("Запускаю проверку напоминаний...")
    await check_mood_reminders(context)
    await update.message.reply_text("Готово.")


# ═══════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════

def load_config():
    global GUIDE_FILE_ID
    if os.path.exists("config.json"):
        with open("config.json") as f:
            config = json.load(f)
            GUIDE_FILE_ID = config.get("guide_file_id")
            if GUIDE_FILE_ID:
                logging.info("Гайд загружен из config.json")

async def main_async():
    load_config()
    await start_api_server()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("uploadguide", upload_guide))
    app.add_handler(CommandHandler("testnotify", test_notify))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.PDF, receive_document))

    from datetime import time as dtime
    app.job_queue.run_daily(check_mood_reminders, time=dtime(hour=17, minute=0, tzinfo=timezone.utc))

    print("Бот запущен ✅")
    print(f"API-сервер слушает на порту {API_PORT} ✅")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())
