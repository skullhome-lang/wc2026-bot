"""Планировщик: авто-анонсы перед матчами и итоги после.

Работает на JobQueue из python-telegram-bot:
  • job_announcements — раз в 30 мин ищет матчи, стартующие в ближайшие
    ANNOUNCE_HOURS_BEFORE часов, и шлёт анонс с раскладом «у кого что на кону».
  • job_results — раз в 10 мин смотрит таблицу и постит итог по матчам,
    у которых появился счёт.

Защита от повторов — через state.py. Имена команд из таблицы (английские)
нормализуются в русские, чтобы сходиться с матрицей потенциала.
"""
from __future__ import annotations

import asyncio
import logging

import brain
import config
import state
import tournament
from schedule_source import normalize_team
from sheet_reader import predicted_label

log = logging.getLogger("wc2026bot.scheduler")


def _format_stakes(stakes: dict, team_a: str, team_b: str) -> str:
    def side(team: str) -> str:
        lst = stakes.get(team, [])[:6]
        if not lst:
            return f"{team}: на кону ни у кого 🤷"
        parts = [
            f"{player} ({val}{', ' + predicted_label(pred) if predicted_label(pred) else ''})"
            for player, val, pred in lst
        ]
        return f"{team} — на кону у: " + "; ".join(parts)

    return side(team_a) + "\n" + side(team_b)


async def _post(context, text: str) -> bool:
    if config.TELEGRAM_CHAT_ID is None:
        log.warning("TELEGRAM_CHAT_ID не задан — сообщение не отправлено.")
        return False
    await context.bot.send_message(config.TELEGRAM_CHAT_ID, text)
    return True


async def job_announcements(context) -> None:
    st = state.load()
    announced = set(st["announced"])
    fixtures = await asyncio.to_thread(tournament.upcoming, config.ANNOUNCE_HOURS_BEFORE)

    changed = False
    for f in fixtures:
        key = f"{f.home}|{f.away}|{f.dt.isoformat() if f.dt else ''}"
        if key in announced:
            continue
        stakes = await asyncio.to_thread(tournament.stakes, f.home, f.away)
        stakes_text = _format_stakes(stakes, f.home, f.away)
        text = await asyncio.to_thread(brain.prematch_breakdown, f.label(), stakes_text)
        if await _post(context, text):
            announced.add(key)
            changed = True

    if changed:
        st["announced"] = sorted(announced)
        state.save(st)


async def job_results(context) -> None:
    st = state.load()
    resulted = set(st["resulted"])
    matches = await asyncio.to_thread(tournament.matches)

    # Первый запуск: помечаем всю историю как обработанную, ничего не постим.
    if not resulted:
        for m in matches:
            if m.played:
                resulted.add(m.key)
        st["resulted"] = sorted(resulted)
        state.save(st)
        log.info("Инициализация результатов: %d сыгранных матчей помечено.", len(resulted))
        return

    new = [m for m in matches if m.played and m.key not in resulted]
    if not new:
        return

    standings = await asyncio.to_thread(tournament.standings)
    standings_text = brain.format_standings(standings)[:1500]

    for m in sorted(new, key=lambda x: (x.dt is None, x.dt)):
        home, away = normalize_team(m.home), normalize_team(m.away)
        winner = normalize_team(m.winner) if m.winner else "ничья"
        info = f"{home} {m.score} {away} ({m.stage}). Итог: {winner}"
        stakes = await asyncio.to_thread(tournament.stakes, home, away)
        stakes_text = _format_stakes(stakes, home, away)
        facts = f"Таблица после матча (топ):\n{standings_text}"
        text = await asyncio.to_thread(brain.postmatch_summary, info, stakes_text, facts)
        if await _post(context, text):
            resulted.add(m.key)

    st["resulted"] = sorted(resulted)
    state.save(st)


def setup(app) -> None:
    jq = app.job_queue
    if jq is None:
        log.warning("JobQueue недоступен — поставь python-telegram-bot[job-queue].")
        return
    jq.run_repeating(job_announcements, interval=1800, first=20)  # каждые 30 мин
    jq.run_repeating(job_results, interval=600, first=45)         # каждые 10 мин
    log.info("Задачи планировщика поставлены.")
