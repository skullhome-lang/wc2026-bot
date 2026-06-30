"""Офлайн-проверка плумбинга без обращений к API (LLM / Telegram / сеть).

Подменяет загрузку CSV на локальные образцы, расписание — на заглушку, а
генерацию текстов — на «эхо», и прогоняет задачи планировщика, печатая, что
бот ОТПРАВИЛ БЫ в чат. Проверяет: разбор данных, формат раскладов, дедуп,
нормализацию англ→рус названий команд.

Запуск:  python selftest.py
"""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

# chat_id должен быть задан ДО импорта config (load_dotenv не переопределяет env)
os.environ["TELEGRAM_CHAT_ID"] = "123456"
os.environ["STATE_PATH"] = os.path.join(tempfile.gettempdir(), "wc_selftest_state.json")
for p in (os.environ["STATE_PATH"], os.environ["STATE_PATH"] + ".tmp"):
    try:
        os.remove(p)
    except FileNotFoundError:
        pass

import brain
import schedule_source
import sheet_reader
import tournament
import scheduler
from schedule_source import Fixture
from sheet_reader import Match

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = {
    sheet_reader.GID_STANDINGS: "data/standings_sample.csv",
    sheet_reader.GID_MATCHES: "data/matches_sample.csv",
    sheet_reader.GID_POTENTIAL: "data/potential_sample.csv",
}


def fake_fetch_csv(gid):
    with open(os.path.join(HERE, SAMPLES[int(gid)]), encoding="utf-8") as f:
        return f.read()


sheet_reader.fetch_csv = fake_fetch_csv


def fake_fetch_fixtures(*a, **k):
    now = tournament.now_local()
    return [
        Fixture(dt=now + timedelta(hours=2), home="Франция", away="Аргентина",
                stage="1/2 финала", status="TIMED", home_en="France", away_en="Argentina"),
    ]


schedule_source.fetch_fixtures = fake_fetch_fixtures

# LLM-генерацию заменяем «эхом», чтобы видеть, какие данные ушли бы в Claude
brain.standings_roast = lambda people, note="": f"[РАЗБОР] лидер={people[0].name} ({people[0].total}); note={note!r}"
brain.prematch_breakdown = lambda info, stakes="": f"[АНОНС] {info}\n{stakes}"
brain.postmatch_summary = lambda info, stakes="", facts="": f"[ИТОГ] {info}\n{stakes}"

# контролируемый список матчей для job_results
_matches = sheet_reader.parse_matches(fake_fetch_csv(sheet_reader.GID_MATCHES))
tournament.matches = lambda ttl=0: list(_matches)
tournament._cache.clear()


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


class FakeCtx:
    def __init__(self):
        self.bot = FakeBot()


async def main():
    ctx = FakeCtx()

    print("=== АНОНСЫ: 1-й прогон ===")
    await scheduler.job_announcements(ctx)
    for _, t in ctx.bot.sent:
        print(t, "\n")
    assert len(ctx.bot.sent) == 1, "ожидался ровно один анонс"

    print("=== АНОНСЫ: повтор (дедуп) ===")
    before = len(ctx.bot.sent)
    await scheduler.job_announcements(ctx)
    assert len(ctx.bot.sent) == before, "повтор не должен слать дубль"
    print("новых сообщений:", len(ctx.bot.sent) - before, "(ожидается 0)\n")

    print("=== ИТОГИ: 1-й прогон (инициализация, без постинга) ===")
    ctx.bot.sent.clear()
    await scheduler.job_results(ctx)
    assert len(ctx.bot.sent) == 0, "на инициализации не постим историю"
    print("отправлено:", len(ctx.bot.sent), "(ожидается 0)\n")

    print("=== ИТОГИ: появился новый сыгранный матч ===")
    _matches.append(Match(
        dt=datetime(2026, 7, 1, 22, 0, tzinfo=timezone.utc), date_raw="01.07 22:00",
        home="Spain", away="Bosnia-Herzegovina", home_goals=2, away_goals=0,
        stage="LAST_32", winner="Spain"))
    await scheduler.job_results(ctx)
    assert len(ctx.bot.sent) == 1, "ожидался один итог по новому матчу"
    msg = ctx.bot.sent[0][1]
    print(msg, "\n")
    assert "Испания" in msg and "Босния" in msg, "англ→рус нормализация не сработала"

    print("ВСЁ ОК ✅  Плумбинг, дедуп и нормализация названий работают.")


if __name__ == "__main__":
    asyncio.run(main())
