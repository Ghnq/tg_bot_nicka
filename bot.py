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
# НАСТРОЙКИ — замени на свои значения
# ─────────────────────────────────────────────
BOT_TOKEN = "8173562858:AAGy1aRrvBuUO1ebS8Q_0krdpexdxFWGu8M"
MINI_APP_URL = "https://veronickaapp.lovable.app"
CONSULTATION_URL = "https://t.me/pa_nicka"
CHANNEL_URL = "https://t.me/potom_podumay"
YOUR_TELEGRAM_ID = 451210923

# Порт на котором будет слушать API-сервер
API_PORT = 8080

# Задержка перед первым сообщением воронки (в часах)
DELAY_AFTER_GUIDE_HOURS = 1
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

def mark_guide_downloaded(user_id: int):
    db = load_db()
    db[str(user_id)] = {
        "downloaded_at": datetime.now().isoformat(),
        "funnel_step": 0,
        "notifications_enabled": True  # по умолчанию включены
    }
    save_db(db)


# ═══════════════════════════════════════════════
# ТЕКСТЫ ВОРОНКИ
# Структура: (через сколько часов, текст, кнопка или None)
# ═══════════════════════════════════════════════

FUNNEL_MESSAGES = [
    (
        DELAY_AFTER_GUIDE_HOURS,
        """Гайд у тебя 📎

Один совет: не пытайся внедрить все 7 шагов сразу. Выбери один — тот, что откликнулся больше всего — и попробуй именно его на этой неделе.

Маленький реальный шаг работает лучше большого плана.""",
        None
    ),
    (
        24,
        """Прокрастинация почти никогда не про лень.

За ней обычно стоит что-то конкретное: страх не справиться, перфекционизм, усталость которую не замечаешь, или задача которая просто не твоя.

Попробуй сегодня спросить себя: что именно я откладываю — и что я на самом деле чувствую по отношению к этому?

Ответ может удивить.""",
        InlineKeyboardMarkup([[
            InlineKeyboardButton("🧘 Попробовать практику", web_app=WebAppInfo(url=MINI_APP_URL))
        ]])
    ),
    (
        72,
        """Есть один момент, про который редко говорят.

Прокрастинация часто усиливается, когда мы слишком строги к себе. Чем больше ругаем — тем сильнее избегание.

Это не значит "разреши себе всё". Это значит — попробуй отнестись к себе так, как отнёсся бы к другу в похожей ситуации. Без осуждения, но честно.""",
        InlineKeyboardMarkup([[
            InlineKeyboardButton("🧘 Открыть практики", web_app=WebAppInfo(url=MINI_APP_URL))
        ]])
    ),
    (
        120,
        """Если после гайда что-то сдвинулось — здорово. Если нет — это тоже нормально.

Иногда паттерны уходят корнями глубже, чем любая техника может достать. Это не повод расстраиваться — просто повод копнуть глубже.

Я работаю с этим в индивидуальном формате — если когда-нибудь захочется разобраться именно в своём случае, ты знаешь где меня найти 🤍""",
        InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Записаться к Веронике", url=CONSULTATION_URL)
        ]])
    ),
    (
        168,
        """

Надеюсь, что-то из гайда и этих заметок оказалось полезным. Забирай что откликнулось, остальное оставь.

Если захочешь продолжить — больше материалов в канале: https://t.me/potom_podumay
Если захочешь поработать лично — @pa_nicka""",
        None
    ),
]


# ═══════════════════════════════════════════════
# API-СЕРВЕР ДЛЯ МИНИ-ПРИЛОЖЕНИЯ
# Принимает запросы на включение/отключение уведомлений
# ═══════════════════════════════════════════════

async def handle_notifications(request):
    """
    POST /notifications
    { "user_id": 123456789, "enabled": true }
    """
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        enabled = bool(data.get("enabled", True))

        if not user_id:
            return web.json_response({"ok": False, "error": "user_id required"}, status=400)

        db = load_db()
        if user_id not in db:
            # Пользователь ещё не в базе (не скачивал гайд) — создаём запись
            db[user_id] = {"notifications_enabled": enabled}
        else:
            db[user_id]["notifications_enabled"] = enabled
        save_db(db)

        status = "включены" if enabled else "отключены"
        logging.info(f"Уведомления {status} для пользователя {user_id}")
        return web.json_response({"ok": True, "notifications_enabled": enabled})

    except Exception as e:
        logging.error(f"Ошибка в handle_notifications: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_notifications_status(request):
    """
    GET /notifications?user_id=123456789
    Возвращает текущий статус уведомлений — мини-приложение может
    прочитать его при загрузке, чтобы показать правильное состояние тоггла.
    """
    user_id = str(request.rel_url.query.get("user_id", ""))
    if not user_id:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)

    db = load_db()
    enabled = db.get(user_id, {}).get("notifications_enabled", True)
    return web.json_response({"ok": True, "notifications_enabled": enabled})


async def handle_mood_checkin(request):
    """
    POST /mood-checkin
    { "user_id": 123456789, "date": "2024-01-15" }
    Приложение вызывает это при каждой записи настроения.
    """
    try:
        data = await request.json()
        user_id = str(data.get("user_id"))
        date = data.get("date")  # формат YYYY-MM-DD

        if not user_id or not date:
            return web.json_response({"ok": False, "error": "user_id and date required"}, status=400)

        db = load_db()
        if user_id not in db:
            db[user_id] = {}
        db[user_id]["last_checkin"] = date
        save_db(db)

        logging.info(f"Запись настроения от {user_id} за {date}")
        return web.json_response({"ok": True})

    except Exception as e:
        logging.error(f"Ошибка в handle_mood_checkin: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ═══════════════════════════════════════════════
# ПЛАНИРОВЩИК НАПОМИНАНИЙ О НАСТРОЕНИИ
# Запускается каждый день в 20:00
# Шлёт уведомление тем, кто не делал запись сегодня
# и у кого включены уведомления
# ═══════════════════════════════════════════════

MOOD_REMINDER_TEXTS = [
    "Привет 🌙 Ты сегодня ещё не проверяла своё состояние.\n\nПара минут сейчас — и день завершится осознаннее.",
    "Вечер — хорошее время остановиться на минуту 🌿\n\nКак ты сегодня? Зафиксируй своё состояние — это занимает меньше минуты.",
    "Маленькое напоминание 💙\n\nСегодняшняя запись настроения ещё не сделана. Загляни в приложение, когда будет момент.",
]

async def check_mood_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Запускается каждый день в 20:00. Шлёт напоминание тем, кто не заполнял настроение сегодня."""
    import random
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🌿 Отметить состояние", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])

    for user_id_str, data in db.items():
        # Только те, у кого включены уведомления
        if not data.get("notifications_enabled", True):
            continue

        # Только те, кто ещё не делал запись сегодня
        if data.get("last_checkin") == today:
            continue

        try:
            text = random.choice(MOOD_REMINDER_TEXTS)
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=text,
                reply_markup=keyboard
            )
            logging.info(f"Напоминание о настроении → пользователь {user_id_str}")
        except Exception as e:
            logging.warning(f"Ошибка напоминания пользователю {user_id_str}: {e}")


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
# ПЛАНИРОВЩИК ВОРОНКИ
# ═══════════════════════════════════════════════

async def check_funnel(context: ContextTypes.DEFAULT_TYPE):
    """Запускается каждые 30 минут. Выживает после перезапуска бота."""
    db = load_db()
    now = datetime.now()
    changed = False

    for user_id_str, data in db.items():
        # Пропускаем пользователей у которых нет данных о скачивании гайда
        if "downloaded_at" not in data:
            continue

        downloaded_at = datetime.fromisoformat(data["downloaded_at"])
        hours_passed = (now - downloaded_at).total_seconds() / 3600
        current_step = data.get("funnel_step", 0)

        for step_index, (hours_threshold, text, keyboard) in enumerate(FUNNEL_MESSAGES):
            if hours_passed >= hours_threshold and current_step <= step_index:
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_str),
                        text=text,
                        reply_markup=keyboard  # None = без кнопок
                    )
                    db[user_id_str]["funnel_step"] = step_index + 1
                    changed = True
                    logging.info(f"Воронка шаг {step_index + 1} → пользователь {user_id_str}")
                except Exception as e:
                    logging.warning(f"Ошибка отправки шага {step_index + 1} пользователю {user_id_str}: {e}")
                break

    if changed:
        save_db(db)


# ═══════════════════════════════════════════════
# КОМАНДА /start
# ═══════════════════════════════════════════════

WELCOME_TEXT = """Привет! 👋

Меня зовут Вероника, я практикующий психолог.

В этом боте я собрала короткие практики, гайды и инструменты, которые использую в работе с клиентами. Они помогут повысить качество жизни и лучше понять себя ❤️

Выбери что тебя интересует 👇"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧘 Открыть приложение с практиками", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("📥 Скачать гайд: 7 шагов от прокрастинации", callback_data="download_guide")],
        [InlineKeyboardButton("💬 Записаться на консультацию", url=CONSULTATION_URL)],
    ])
    await update.message.reply_text(WELCOME_TEXT, reply_markup=keyboard)


# ═══════════════════════════════════════════════
# КОМАНДА /help
# ═══════════════════════════════════════════════

HELP_TEXT = """Вот что есть в этом боте 👇

🧘 *Приложение с практиками*
Короткие упражнения для снижения тревожности и осознанности. Нажми кнопку «Открыть приложение с практиками» — оно откроется прямо здесь в Telegram, выходить никуда не нужно.

📥 *Гайд «7 шагов от прокрастинации»*
Бесплатный материал, который я использую в работе с клиентами. Нажми кнопку «Скачать гайд» и получишь PDF файл.

💬 *Консультация*
Индивидуальная работа в формате серии сессий. Если хочешь разобраться в своей ситуации глубже — напиши мне напрямую через кнопку «Записаться на консультацию».

Если что-то не работает или есть вопросы — пиши @pa\\_nicka"""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧘 Открыть приложение с практиками", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("📥 Скачать гайд", callback_data="download_guide")],
        [InlineKeyboardButton("💬 Записаться на консультацию", url=CONSULTATION_URL)],
    ])
    await update.message.reply_text(HELP_TEXT, reply_markup=keyboard, parse_mode="Markdown")


# ═══════════════════════════════════════════════
# КОМАНДА /stats (только для тебя)
# ═══════════════════════════════════════════════

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return

    db = load_db()
    total = len([u for u in db.values() if "downloaded_at" in u])

    if total == 0:
        await update.message.reply_text("Пока никто не скачал гайд.")
        return

    steps = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    notifications_off = 0
    for data in db.values():
        if "downloaded_at" not in data:
            continue
        step = data.get("funnel_step", 0)
        steps[step] = steps.get(step, 0) + 1
        if not data.get("notifications_enabled", True):
            notifications_off += 1

    completed = steps.get(5, 0)

    text = (
        f"📊 *Статистика воронки*\n\n"
        f"Всего скачали гайд: *{total}*\n"
        f"Отключили уведомления: *{notifications_off}*\n\n"
        f"По шагам воронки:\n"
        f"  Шаг 0 (только скачали): {steps.get(0, 0)}\n"
        f"  Шаг 1 (получили сообщение день 0): {steps.get(1, 0)}\n"
        f"  Шаг 2 (день 1): {steps.get(2, 0)}\n"
        f"  Шаг 3 (день 3): {steps.get(3, 0)}\n"
        f"  Шаг 4 (день 5): {steps.get(4, 0)}\n"
        f"  Шаг 5 (прошли всю воронку): {steps.get(5, 0)}\n\n"
        f"Прошли воронку полностью: *{completed}* из *{total}*"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════
# СКАЧИВАНИЕ ГАЙДА
# ═══════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "download_guide":
        user_id = query.from_user.id

        if not GUIDE_FILE_ID:
            await query.message.reply_text("Гайд скоро появится здесь! Следи за обновлениями 🤍")
            return

        await query.message.reply_document(
            document=GUIDE_FILE_ID,
            caption="7 шагов для преодоления прокрастинации 📎"
        )

        db = load_db()
        if str(user_id) not in db:
            mark_guide_downloaded(user_id)
            logging.info(f"Новый пользователь в воронке: {user_id}")


# ═══════════════════════════════════════════════
# ЗАГРУЗКА / ЗАМЕНА ГАЙДА
# ═══════════════════════════════════════════════

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

    await update.message.reply_text(
        "✅ Гайд сохранён и сразу доступен пользователям!\n\n"
        "Нажми кнопку «Скачать гайд» чтобы проверить."
    )


# ═══════════════════════════════════════════════
# ТЕСТОВАЯ КОМАНДА /testnotify (только для тебя)
# Запускает проверку напоминаний прямо сейчас
# ═══════════════════════════════════════════════

async def test_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID:
        return
    await update.message.reply_text("Запускаю проверку напоминаний о настроении...")
    await check_mood_reminders(context)
    await update.message.reply_text("Готово. Проверь — пришло ли уведомление.")


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
                logging.info("✅ Гайд загружен из config.json")

async def main_async():
    load_config()

    # Запускаем API-сервер параллельно с ботом
    await start_api_server()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("uploadguide", upload_guide))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.PDF, receive_document))

    app.job_queue.run_repeating(check_funnel, interval=1800, first=10)

    # Напоминание о записи настроения — каждый день в 20:00 MSK (= 17:00 UTC)
    from datetime import time as dtime
    app.job_queue.run_daily(check_mood_reminders, time=dtime(hour=17, minute=0, tzinfo=timezone.utc))

    app.add_handler(CommandHandler("testnotify", test_notify))

    print("Бот запущен ✅")
    print(f"API-сервер слушает на порту {API_PORT} ✅")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()  # держим процесс живым

if __name__ == "__main__":
    asyncio.run(main_async())
