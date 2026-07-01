"""Слой данных: кэширующие обёртки над таблицей и расписанием.

Снимает нагрузку с gviz и football-data (лимит 10 запросов/мин): результаты
переиспользуются в пределах TTL. Здесь же — сборки, которые нужны и боту, и
планировщику.
"""
from __future__ import annotations

import time
from datetime import datetime

import config
import odds_source
import schedule_source
import sheet_reader

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, producer):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _cache[key] = (now, value)
    return value


def now_local() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(config.TIMEZONE))
    return datetime.now()


def standings(ttl: float = 120):
    return _cached("standings", ttl, sheet_reader.get_standings)


def matches(ttl: float = 120):
    return _cached("matches", ttl, lambda: sheet_reader.get_matches(config.TIMEZONE))


def potential(ttl: float = 300):
    return _cached("potential", ttl, sheet_reader.get_potential)


def fixtures(ttl: float = 900):
    if not config.FOOTBALL_DATA_API_KEY:
        return []
    return _cached(
        "fixtures",
        ttl,
        lambda: schedule_source.fetch_fixtures(config.FOOTBALL_DATA_API_KEY, config.TIMEZONE),
    )


def upcoming(within_hours: float = 48):
    return schedule_source.upcoming_fixtures(fixtures(), now_local(), within_hours)


def stakes(team_a: str, team_b: str):
    return sheet_reader.stakes_for_match(potential(), team_a, team_b)


def predictions_digest() -> str:
    """Компактный конспект «кто на кого ставил» — для ответов бота на такие вопросы."""
    return sheet_reader.format_predictions_digest(potential())


def odds(ttl: float = 1800):
    """Котировки букмекеров на матчи ЧМ (пусто, если ключ не задан)."""
    if not config.ODDS_API_KEY:
        return []
    return _cached(
        "odds", ttl,
        lambda: odds_source.parse_events(odds_source.fetch_odds(config.ODDS_API_KEY)),
    )
