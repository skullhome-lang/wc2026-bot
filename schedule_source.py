"""Официальное расписание ЧМ-2026 из football-data.org (бесплатный тариф).

Используется ТОЛЬКО для будущих матчей (анонсы): дата, время, соперники, стадия.
Счёт и результаты бот берёт из Google-таблицы (sheet_reader), а не отсюда.

Сеть (fetch_fixtures) отделена от разбора (parse_fixtures) — разбор тестируется
на сохранённом JSON без обращения к сети.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"

# Стадии football-data -> по-русски (как принято в сетке)
STAGE_RU = {
    "GROUP_STAGE": "Групповой этап",
    "LAST_32": "1/16 финала",
    "LAST_16": "1/8 финала",
    "QUARTER_FINALS": "1/4 финала",
    "SEMI_FINALS": "1/2 финала",
    "THIRD_PLACE": "Матч за 3-е место",
    "FINAL": "Финал",
}

# Английское имя команды (в разных написаниях) -> русское имя как в таблице
_TEAM_RU_RAW = {
    "netherlands": "Нидерланды", "morocco": "Марокко", "germany": "Германия",
    "paraguay": "Парагвай", "brazil": "Бразилия", "japan": "Япония",
    "south africa": "ЮАР", "jordan": "Иордания", "argentina": "Аргентина",
    "algeria": "Алжир", "austria": "Австрия", "colombia": "Колумбия",
    "portugal": "Португалия", "congo dr": "ДР Конго", "dr congo": "ДР Конго",
    "uzbekistan": "Узбекистан", "panama": "Панама", "england": "Англия",
    "croatia": "Хорватия", "ghana": "Гана", "new zealand": "Новая Зеландия",
    "belgium": "Бельгия", "egypt": "Египет", "iran": "Иран", "uruguay": "Уругвай",
    "spain": "Испания", "cape verde islands": "Кабо-Верде", "cape verde": "Кабо-Верде",
    "saudi arabia": "Саудовская Аравия", "norway": "Норвегия", "france": "Франция",
    "senegal": "Сенегал", "iraq": "Ирак", "turkey": "Турция", "turkiye": "Турция",
    "united states": "США", "usa": "США", "australia": "Австралия", "tunisia": "Тунис",
    "sweden": "Швеция", "ecuador": "Эквадор", "curacao": "Кюрасао",
    "ivory coast": "Кот-д'Ивуар", "cote divoire": "Кот-д'Ивуар",
    "czechia": "Чехия", "czech republic": "Чехия", "mexico": "Мексика",
    "south korea": "Южная Корея", "korea republic": "Южная Корея",
    "haiti": "Гаити", "scotland": "Шотландия", "switzerland": "Швейцария",
    "bosnia and herzegovina": "Босния", "bosnia herzegovina": "Босния",
    "qatar": "Катар", "canada": "Канада",
}


def _key(name: str) -> str:
    """Нормализация имени: убрать диакритику, пунктуацию, регистр."""
    s = unicodedata.normalize("NFKD", name or "")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    for ch in "-.'":
        s = s.replace(ch, " ")
    return " ".join(s.split())


_TEAM_RU = {_key(k): v for k, v in _TEAM_RU_RAW.items()}


def normalize_team(name: str) -> str:
    """Английское имя команды -> русское (как в таблице). Неизвестное вернёт как есть."""
    return _TEAM_RU.get(_key(name), name)


@dataclass
class Fixture:
    dt: datetime | None        # время начала в локальном поясе (МСК)
    home: str                  # русское имя
    away: str                  # русское имя
    stage: str                 # русская стадия
    status: str                # SCHEDULED, TIMED, IN_PLAY, FINISHED, ...
    home_en: str = ""
    away_en: str = ""

    @property
    def upcoming(self) -> bool:
        return self.status in ("SCHEDULED", "TIMED")

    def label(self) -> str:
        when = self.dt.strftime("%d.%m %H:%M") if self.dt else "—"
        return f"{when} | {self.home} — {self.away} ({self.stage})"


def _to_local(utc_iso: str, tz: str):
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        return dt.astimezone(ZoneInfo(tz))
    return dt


def parse_fixtures(payload: dict, tz: str = "Europe/Moscow") -> list[Fixture]:
    out: list[Fixture] = []
    for m in payload.get("matches", []):
        home_en = (m.get("homeTeam") or {}).get("name") or ""
        away_en = (m.get("awayTeam") or {}).get("name") or ""
        out.append(
            Fixture(
                dt=_to_local(m.get("utcDate", ""), tz),
                home=normalize_team(home_en),
                away=normalize_team(away_en),
                stage=STAGE_RU.get(m.get("stage", ""), m.get("stage", "")),
                status=m.get("status", ""),
                home_en=home_en,
                away_en=away_en,
            )
        )
    out.sort(key=lambda f: (f.dt is None, f.dt or datetime.max.replace(tzinfo=timezone.utc)))
    return out


def fetch_fixtures(api_key: str | None = None, tz: str = "Europe/Moscow",
                   date_from: str | None = None, date_to: str | None = None) -> list[Fixture]:
    """Скачать матчи ЧМ-2026. date_from/date_to в формате YYYY-MM-DD (опционально)."""
    import requests

    if api_key is None:
        import config
        api_key = config.FOOTBALL_DATA_API_KEY
    params = {}
    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to
    resp = requests.get(API_URL, headers={"X-Auth-Token": api_key}, params=params, timeout=20)
    resp.raise_for_status()
    return parse_fixtures(resp.json(), tz=tz)


def upcoming_fixtures(fixtures: list[Fixture], now: datetime,
                      within_hours: float = 48) -> list[Fixture]:
    """Будущие матчи в ближайшие within_hours часов."""
    res = []
    for f in fixtures:
        if not f.upcoming or f.dt is None:
            continue
        delta_h = (f.dt - now).total_seconds() / 3600
        if 0 <= delta_h <= within_hours:
            res.append(f)
    return res


def unmapped_team_names(fixtures: list[Fixture]) -> set[str]:
    """Имена, которые не удалось перевести на русский (для отладки маппинга)."""
    bad = set()
    for f in fixtures:
        if f.home == f.home_en and _key(f.home_en) not in _TEAM_RU:
            bad.add(f.home_en)
        if f.away == f.away_en and _key(f.away_en) not in _TEAM_RU:
            bad.add(f.away_en)
    return bad
