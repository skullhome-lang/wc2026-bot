"""Котировки букмекеров на матчи ЧМ-2026 (the-odds-api.com) — «мнение» бота.

Из коэффициентов считаем подразумеваемые вероятности и фаворита матча.
Усредняем по букмекерам и убираем маржу (нормируем сумму к 1).
Сеть (fetch_odds) отделена от разбора (parse_events) — разбор тестируется офлайн.
"""
from __future__ import annotations

import schedule_source
import sheet_reader

API_URL = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"


def fetch_odds(api_key: str, regions: str = "eu", market: str = "h2h") -> list:
    import requests

    params = {"regions": regions, "markets": market,
              "oddsFormat": "decimal", "apiKey": api_key}
    resp = requests.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _implied(price) -> float:
    try:
        price = float(price)
        return 1.0 / price if price > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_events(payload: list) -> list[dict]:
    """-> список матчей с вероятностями и фаворитом (русские имена команд)."""
    out = []
    for ev in payload or []:
        home_en = ev.get("home_team", "")
        away_en = ev.get("away_team", "")
        if not home_en or not away_en:
            continue
        # усредняем подразумеваемую вероятность по всем букмекерам
        acc: dict[str, list] = {}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                for oc in mk.get("outcomes", []):
                    nm = oc.get("name", "")
                    acc.setdefault(nm, [0.0, 0])
                    acc[nm][0] += _implied(oc.get("price"))
                    acc[nm][1] += 1
        if not acc:
            continue
        avg = {nm: (s / c if c else 0.0) for nm, (s, c) in acc.items()}
        total = sum(avg.values()) or 1.0
        probs = {nm: v / total for nm, v in avg.items()}  # нормировка (убрали маржу)

        p_home = probs.get(home_en, 0.0)
        p_away = probs.get(away_en, 0.0)
        home, away = schedule_source.normalize_team(home_en), schedule_source.normalize_team(away_en)
        favorite, fav_prob = (home, p_home) if p_home >= p_away else (away, p_away)
        out.append({
            "home": home, "away": away, "home_en": home_en, "away_en": away_en,
            "p_home": p_home, "p_away": p_away, "p_draw": probs.get("Draw", 0.0),
            "favorite": favorite, "fav_prob": fav_prob,
            "commence": ev.get("commence_time", ""),
        })
    return out


def match_favorite(events: list[dict], team_a: str, team_b: str):
    """Найти матч между двумя командами в котировках."""
    ak, bk = sheet_reader._team_key(team_a), sheet_reader._team_key(team_b)
    for e in events:
        keys = {
            sheet_reader._team_key(e["home"]), sheet_reader._team_key(e["away"]),
            sheet_reader._team_key(e["home_en"]), sheet_reader._team_key(e["away_en"]),
        }
        if ak in keys and bk in keys:
            return e
    return None


def pct(prob: float) -> str:
    return f"{round(prob * 100)}%"
