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
import identity
import scenario
import sheet_reader
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


def _resolve_participant(update: Update, people):
    """Кто написал: сначала по сохранённой связке user_id (/iam), иначе по имени Telegram."""
    user = update.effective_user
    if user is None:
        return None
    saved = identity.get_name(user.id)
    if saved:
        p = scenario.find_participant(people, saved)
        if p:
            return p
    guess = ((user.first_name or "") + " " + (user.last_name or "")).strip()
    return scenario.find_participant(people, guess) if guess else None


def _scenario_totals(matrix: dict, people, scenario_map: dict):
    return scenario.compute_totals(matrix, scenario.r1_map(people), scenario_map)


def _format_scenario(scenario_map: dict, labels: dict, totals, current: dict) -> str:
    """Детерминированная таблица итогов по сценарию (без LLM)."""
    head = "📊 Сценарий: " + ", ".join(f"{t} → {labels.get(t, '?')}" for t in scenario_map)
    lines = []
    for i, (name, tot) in enumerate(totals, 1):
        diff = round(tot - current.get(name, 0), 1)
        mark = f" (+{diff})" if diff > 0 else ""
        lines.append(f"{i}. {name} — {tot}{mark}")
    return head + "\n\n" + "\n".join(lines)


def _headline(totals, extra: str = "") -> str:
    """Короткая выжимка для комментатора (чтобы он не переписывал всю таблицу)."""
    top = ", ".join(f"{n} ({t})" for n, t in totals[:3])
    if not top:
        return extra
    return "Топ: " + top + ((". " + extra) if extra else "")


def _build_chance_text(people, me) -> str:
    """Детерминированный вывод про шансы участника (без LLM)."""
    info = scenario.chance_analysis(people, me)
    text = (f"🎯 {me.name}: сейчас {info['current']} ({info['place']}-е место), "
            f"максимум возможно {info['ceiling']}.\n")
    if info["can_be_first"]:
        text += (f"Математически первое место ещё достижимо: твой потолок ({info['ceiling']}) "
                 f"не ниже текущих очков всех соперников. Лидер сейчас — {info['leader_name']} "
                 f"({info['leader_current']}). Конкретный расклад проверь через /scenario.")
    else:
        names = ", ".join(f"{p.name} ({p.total})" for p in info["uncatchable"])
        text += (f"Первое место уже не светит: даже твой потолок {info['ceiling']} меньше, чем "
                 f"уже набрали: {names}. Этих не догнать.")
    return text


def _scenario_from_intent(matrix: dict, teams: dict):
    """{'Франция':'чемпион'} -> (scenario{team:cum}, labels{team:word})."""
    sc, labels = {}, {}
    for team_query, stage_word in teams.items():
        team = sheet_reader.find_team(matrix, str(team_query))
        cum, key = scenario.stage_to_cum(str(stage_word))
        if team and cum is not None:
            sc[team] = cum
            labels[team] = key or str(stage_word)
    return sc, labels


# --------------------------------------------------------------------------- #
#  Команды                                                                    #
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я — ведущий вашего турнира прогнозов на ЧМ-2026 🏆\n"
        "Команды:\n"
        "/table — текущий расклад с разбором\n"
        "/next — ближайшие матчи\n"
        "/roast [запрос] — разнос таблицы или ответ на вопрос\n"
        "/team <команда> — кто поставил на эту команду\n"
        "/scenario <расклад> — точный пересчёт таблицы (напр.: Аргентина чемпион, Франция финал)\n"
        "/chance [фамилия] — можешь ли ещё стать первым\n"
        "/iam <фамилия> — представиться, чтобы я узнавал тебя без @\n"
        "/chatid — id этого чата (для настройки)\n\n"
        "А ещё я иногда сам влезаю с комментарием. Не обессудьте 😏"
    )


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")


async def cmd_iam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Представься фамилией из таблицы, напр.: /iam Кравченко")
        return
    people = await asyncio.to_thread(tournament.standings)
    query = " ".join(context.args).strip()
    p = scenario.find_participant(people, query)
    if not p:
        await update.message.reply_text(
            f"Не нашёл «{query}» среди участников. Напиши фамилию как в таблице: /iam Кравченко"
        )
        return
    identity.set_name(update.effective_user.id, p.name)
    await update.message.reply_text(
        f"Готово, узнал тебя: {p.avatar} {p.name}. Теперь буду обращаться по-человечески 👌"
    )


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    people = await asyncio.to_thread(tournament.standings)
    p = _resolve_participant(update, people)
    if p:
        await update.message.reply_text(f"Ты у меня записан как {p.avatar} {p.name}.")
    else:
        await update.message.reply_text("Пока не знаю, кто ты. Представься: /iam Фамилия")


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
    preds = await asyncio.to_thread(tournament.predictions_digest)
    elim = ", ".join(sorted(scenario.eliminated_teams(await asyncio.to_thread(tournament.matches))))
    query = " ".join(context.args).strip() if context.args else ""
    note = f"Запрос от ведущего: {query}" if query else ""
    text = await asyncio.to_thread(brain.standings_roast, people, note, preds, elim)
    await update.message.reply_text(text)


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи команду: /team Кот-д'Ивуар")
        return
    await _typing(context, update.effective_chat.id)
    query = " ".join(context.args).strip()
    matrix = await asyncio.to_thread(tournament.potential)
    team = sheet_reader.find_team(matrix, query)
    if not team:
        await update.message.reply_text(f"Не нашёл команду «{query}» в прогнозах 🤷")
        return
    backers = sheet_reader.team_backers(matrix, team)
    backers_text = ", ".join(
        f"{p} ({v}{', ' + predicted_label(v) if predicted_label(v) else ''})"
        for p, v in backers
    ) or "никто не ставил"
    people = await asyncio.to_thread(tournament.standings)
    note = f"Вопрос: кто поставил на {team}. Данные — на {team} поставили: {backers_text}."
    elim = ", ".join(sorted(scenario.eliminated_teams(await asyncio.to_thread(tournament.matches))))
    text = await asyncio.to_thread(brain.standings_roast, people, note, "", elim)
    await update.message.reply_text(text)


async def cmd_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Зададим расклад — и я точно пересчитаю очки всех.\n"
            "Пример: /scenario Аргентина чемпион, Франция финал, Испания 1/4\n"
            "Стадии: 1/16, 1/8, 1/4, 1/2, финал, чемпион"
        )
        return
    await _typing(context, update.effective_chat.id)
    matrix = await asyncio.to_thread(tournament.potential)
    people = await asyncio.to_thread(tournament.standings)
    sc, labels, warns = scenario.parse_scenario(matrix, " ".join(context.args))
    if not sc:
        msg = "Не разобрал сценарий. " + ("; ".join(warns) if warns else "")
        await update.message.reply_text(
            msg + "\nПример: /scenario Аргентина чемпион, Франция финал")
        return

    totals = _scenario_totals(matrix, people, sc)
    current = {p.name: (p.total or 0) for p in people}
    table = _format_scenario(sc, labels, totals, current)
    if warns:
        table += "\n\n⚠️ не разобрал: " + "; ".join(warns)
    comment = await asyncio.to_thread(brain.scenario_comment, _headline(totals))
    await update.message.reply_text(table + "\n\n" + comment)


async def cmd_chance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(context, update.effective_chat.id)
    people = await asyncio.to_thread(tournament.standings)
    if context.args:
        me = scenario.find_participant(people, " ".join(context.args).strip())
    else:
        me = _resolve_participant(update, people)
    if not me:
        await update.message.reply_text(
            "Не понял, кто ты. Представься командой /iam Фамилия — или укажи: /chance Кравченко"
        )
        return

    summary = _build_chance_text(people, me)
    comment = await asyncio.to_thread(brain.scenario_comment, summary)
    await update.message.reply_text(summary + "\n\n" + comment)


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

    addressed = mentioned or replied
    if not addressed:
        return  # бот молчит, пока к нему явно не обратятся (@упоминание или ответ ему)

    await _typing(context, msg.chat_id)
    text_in = msg.text.replace(f"@{bot_username}", "").strip()
    people = await asyncio.to_thread(tournament.standings)
    speaker = _resolve_participant(update, people)
    name = speaker.name if speaker else ((msg.from_user.first_name if msg.from_user else None) or "Аноним")

    # При явном обращении пробуем понять «сценарий/шансы» и посчитать точно
    if addressed:
        matrix = await asyncio.to_thread(tournament.potential)
        team_names = list(matrix.get("prediction", {}).keys())
        intent = await asyncio.to_thread(brain.parse_intent, text_in, team_names)
        kind = intent.get("intent")

        if kind == "match" and intent.get("winner") and intent.get("loser"):
            fixtures = await asyncio.to_thread(tournament.fixtures)
            fx = scenario.find_fixture(fixtures, str(intent["winner"]), str(intent["loser"]))
            if fx is None:
                await msg.reply_text(
                    f"Не нашёл матч {intent['winner']}–{intent['loser']} в ближайшем "
                    "расписании — возможно, они не встречаются в этом раунде. Можно задать "
                    "стадии напрямую: /scenario."
                )
                return
            wk = sheet_reader._team_key(str(intent["winner"]))
            if wk in (sheet_reader._team_key(fx.home), sheet_reader._team_key(fx.home_en)):
                winner, loser = fx.home, fx.away
            else:
                winner, loser = fx.away, fx.home
            w = sheet_reader.find_team(matrix, winner) or winner
            l = sheet_reader.find_team(matrix, loser) or loser
            sc, labels = scenario.match_scenario(w, l, fx.stage_code)
            if not sc:
                await msg.reply_text(
                    "Это групповой этап — там вылет зависит от всей группы, такие расклады "
                    "пока не считаю. В плейофф — без проблем."
                )
                return
            totals = _scenario_totals(matrix, people, sc)
            current = {p.name: (p.total or 0) for p in people}
            table = _format_scenario(sc, labels, totals, current)
            losers = scenario.potential_losers(matrix, l, sc[l])
            hurt = ""
            if losers:
                top_hurt = "\n".join(f"• {n}: −{d}" for n, d in losers[:6])
                hurt = f"📉 Кто теряет потенциал (ставил {loser} глубже):\n{top_hurt}\n\n"
            header = (
                f"⚽ Если {winner} обыграет {loser} ({fx.stage}): {loser} вылетает.\n"
                f"Текущие очки почти не двигаются — за проигранный матч очков не дают, "
                f"а {winner} в этом матче мало кто ставил. Главный удар — по потенциалу:\n\n"
            )
            extra = f"Сильнее всех просел {losers[0][0]} (−{losers[0][1]})." if losers else ""
            comment = await asyncio.to_thread(brain.scenario_comment, _headline(totals, extra))
            await msg.reply_text(header + hurt + table + "\n\n" + comment)
            return

        if kind == "result" and intent.get("team_a") and intent.get("team_b"):
            matches = await asyncio.to_thread(tournament.matches)
            m = scenario.find_result(matches, str(intent["team_a"]), str(intent["team_b"]))
            if m is None:
                await msg.reply_text(
                    f"Не нашёл сыгранного матча {intent['team_a']}–{intent['team_b']} "
                    "в таблице результатов."
                )
                return
            fact = scenario.format_result(m)
            comment = await asyncio.to_thread(brain.scenario_comment, fact)
            await msg.reply_text(f"⚽ {fact}\n\n{comment}")
            return

        if kind == "scenario" and isinstance(intent.get("teams"), dict) and intent["teams"]:
            sc, labels = _scenario_from_intent(matrix, intent["teams"])
            if sc:
                totals = _scenario_totals(matrix, people, sc)
                current = {p.name: (p.total or 0) for p in people}
                table = _format_scenario(sc, labels, totals, current)
                comment = await asyncio.to_thread(brain.scenario_comment, _headline(totals))
                await msg.reply_text(table + "\n\n" + comment)
                return

        if kind == "chance":
            target = intent.get("player")
            who = scenario.find_participant(people, str(target)) if target else speaker
            if who:
                summary = _build_chance_text(people, who)
                comment = await asyncio.to_thread(brain.scenario_comment, summary)
                await msg.reply_text(summary + "\n\n" + comment)
                return
            await msg.reply_text("Не понял, про кого шанс. Представься: /iam Фамилия")
            return

    # Обычный разговор
    preds = await asyncio.to_thread(tournament.predictions_digest)
    elim = ", ".join(sorted(scenario.eliminated_teams(await asyncio.to_thread(tournament.matches))))
    ctx = brain.format_standings(people)
    reply = await asyncio.to_thread(brain.chat_reply, name, text_in, ctx, preds, elim)
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
    app.add_handler(CommandHandler(["iam", "me"], cmd_iam))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler(["table", "standings"], cmd_table))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("roast", cmd_roast))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("scenario", cmd_scenario))
    app.add_handler(CommandHandler("chance", cmd_chance))
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
