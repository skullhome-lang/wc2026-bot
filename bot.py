"""Telegram-бот турнира ЧМ-2026: команды и живые реакции в чате."""
from __future__ import annotations

import asyncio
import logging
import os
import random

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import brain
import config
import tournament
from sheet_reader import predicted_label

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("wc2026bot")


# --------------------------------------------------------------------------- #
#  Хелперы                                                                    #
# --------------------------------------------------------------------------- #
async def _typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    except Exception:  # noqa: BLE001 — индикатор печати не критичен
        pass


def _in_target_chat(update: Update) -> bool:
    """True, если сообщение из рабочей группы (или группа не задана)."""
    if config.TELEGRAM_CHAT_ID is None:
        return True
    return update.effective_chat and update.effective_chat.id == config.TELEGRAM_CHAT_ID


# --------------------------------------------------------------------------- #
#  Команды                                                                    #
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я — ведущий вашего турнира прогнозов на ЧМ-2026 🏆\n"
        "Команды:\n"
        "/table — текущий расклад с разбором\n"
        "/next — ближайшие матчи\n"
        "/roast [имя] — разнос таблицы или конкретного игрока\n"
        "/chatid — id этого чата (для настройки)\n\n"
        "А ещё я иногда сам влезаю с комментарием. Не обессудьте 😏"
    )


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")


async def cmd_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(context, update.effective_chat.id)
    people = await asyncio.to_thread(tournament.standings)
    text = await asyncio.to_thread(brain.standings_roast, people)
    await update.message.reply_text(text)


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(context, update.effective_chat.id)
    fx = await asyncio.to_thread(tournament.upcoming, 48)
    if not fx:
        await update.message.reply_text("В ближайшие 48 часов матчей нет. Отдыхаем 😴")
        return
    lines = "\n".join(f"• {f.label()}" for f in fx[:8])
    await update.message.reply_text("Ближайшие матчи:\n" + lines)


async def cmd_roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(context, update.effective_chat.id)
    people = await asyncio.to_thread(tournament.standings)
    target = " ".join(context.args) if context.args else ""
    note = f"Особенно пройдись по участнику: {target}" if target else ""
    text = await asyncio.to_thread(brain.standings_roast, people, note)
    await update.message.reply_text(text)


# --------------------------------------------------------------------------- #
#  Живые реакции на сообщения                                                 #
# --------------------------------------------------------------------------- #
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or (msg.from_user and msg.from_user.is_bot):
        return

    bot_username = context.bot.username or ""
    bot_id = context.bot.id
    mentioned = bool(bot_username) and f"@{bot_username}" in msg.text
    replied = bool(
        msg.reply_to_message
        and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.id == bot_id
    )

    # Без явного обращения вмешиваемся только в рабочем чате и лишь иногда
    if not (mentioned or replied):
        if not _in_target_chat(update):
            return
        if random.random() > config.REPLY_PROBABILITY:
            return

    await _typing(context, msg.chat_id)
    name = (msg.from_user.first_name if msg.from_user else None) or "Аноним"
    text_in = msg.text.replace(f"@{bot_username}", "").strip()
    people = await asyncio.to_thread(tournament.standings)
    ctx = brain.format_standings(people)
    reply = await asyncio.to_thread(brain.chat_reply, name, text_in, ctx)
    await msg.reply_text(reply)


# --------------------------------------------------------------------------- #
#  Точка входа                                                                #
# --------------------------------------------------------------------------- #
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Ошибка при обработке апдейта: %s", context.error)


def build_app() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(CommandHandler(["table", "standings"], cmd_table))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("roast", cmd_roast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)

    # Планировщик анонсов/итогов подключается отдельным модулем (scheduler.py)
    try:
        import scheduler

        scheduler.setup(app)
        log.info("Планировщик подключён.")
    except ImportError:
        log.info("scheduler.py пока нет — работаю без авто-анонсов.")
    return app


def _maybe_start_health_server():
    """На хостингах вроде Koyeb «web»-сервис ждёт открытый порт. Если задан PORT —
    поднимаем простой health-эндпоинт в фоне. Как worker (без PORT) — пропускаем."""
    port = os.environ.get("PORT")
    if not port:
        return
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Health(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):  # глушим access-лог
            pass

    srv = HTTPServer(("0.0.0.0", int(port)), _Health)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("Health-сервер слушает порт %s", port)


def main():
    _maybe_start_health_server()
    app = build_app()
    log.info("Бот запускается…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
