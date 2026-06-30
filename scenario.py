"""Просчёт сценариев плейофф — детерминированно, без участия LLM.

Очки участника во 2-м раунде = сумма по командам min(прогноз, факт_стадии).
Значения на шкале листа: 0.5=до 1/16, 1.5=до 1/8, 3.5=до 1/4, 6.5=до 1/2, 10.5=чемпион.
Очки «общие»: одна команда, прошедшая дальше, добавляет очки ВСЕМ, кто её так ставил.
"""
from __future__ import annotations

import sheet_reader

# Слово стадии -> накопительный потолок очков
STAGE_CUM = {
    "1/16": 0.5, "1/8": 1.5, "1/4": 3.5, "1/2": 6.5, "финал": 6.5, "чемпион": 10.5,
}
# Нормализация пользовательского ввода стадии
STAGE_ALIASES = {
    "1/16": "1/16", "16": "1/16", "группа": "1/16", "группы": "1/16", "выход": "1/16",
    "1/8": "1/8", "8": "1/8",
    "1/4": "1/4", "4": "1/4", "четверть": "1/4", "четвертьфинал": "1/4",
    "1/2": "1/2", "2": "1/2", "полу": "1/2", "полуфинал": "1/2", "полуфиналист": "1/2",
    "финал": "финал", "финалист": "финал",
    "чемпион": "чемпион", "чемпионы": "чемпион", "победитель": "чемпион", "выиграет": "чемпион",
}


def stage_to_cum(word: str):
    key = STAGE_ALIASES.get(word.strip().lower())
    return (STAGE_CUM.get(key), key) if key else (None, None)


def r1_map(standings) -> dict:
    return {p.name: (p.r1 or 0) for p in standings}


def compute_totals(matrix: dict, r1: dict, scenario: dict) -> list[tuple[str, float]]:
    """Итоговые очки всех участников при заданном сценарии {команда: потолок}.
    Команды вне сценария остаются на текущих очках (realized)."""
    pred = matrix.get("prediction", {})
    realized = matrix.get("realized", {})
    out = []
    for name in matrix.get("players", []):
        total = r1.get(name, 0) or 0
        for team, vals in pred.items():
            p = vals.get(name) or 0
            if team in scenario:
                total += min(p, scenario[team])
            else:
                total += (realized.get(team, {}).get(name) or 0)
        out.append((name, round(total, 1)))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def parse_scenario(matrix: dict, text: str):
    """'Аргентина чемпион, Франция 1/2' -> (scenario{team:cum}, labels{team:word}, warnings)."""
    scenario, labels, warnings = {}, {}, []
    for chunk in text.replace(";", ",").split(","):
        parts = chunk.split()
        if len(parts) < 2:
            continue
        cum, key = stage_to_cum(parts[-1])
        team = sheet_reader.find_team(matrix, " ".join(parts[:-1]))
        if cum is None:
            warnings.append(f"не понял стадию «{parts[-1]}»")
        elif not team:
            warnings.append(f"не нашёл команду «{' '.join(parts[:-1])}»")
        else:
            scenario[team] = cum
            labels[team] = key
    return scenario, labels, warnings


# --- Логика конкретного матча (X обыграл Y) --------------------------------- #
# Код стадии football-data -> накопительный потолок очков ЗА ВЫХОД в эту стадию.
_REACHED_CUM = {
    "LAST_32": 0.5, "LAST_16": 1.5, "QUARTER_FINALS": 3.5,
    "SEMI_FINALS": 6.5, "FINAL": 6.5, "CHAMPION": 10.5,
}
_NEXT_STAGE = {
    "LAST_32": "LAST_16", "LAST_16": "QUARTER_FINALS",
    "QUARTER_FINALS": "SEMI_FINALS", "SEMI_FINALS": "FINAL", "FINAL": "CHAMPION",
}
_STAGE_WORD = {
    "LAST_32": "1/16", "LAST_16": "1/8", "QUARTER_FINALS": "1/4",
    "SEMI_FINALS": "1/2", "FINAL": "финал", "CHAMPION": "чемпион",
}


def match_scenario(winner: str, loser: str, stage_code: str):
    """Матч на стадии stage_code: победитель проходит дальше, проигравший вылетает.
    Возвращает (scenario{team:cum}, labels{team:word}) или (None, None) для группы/неизвестной стадии."""
    nxt = _NEXT_STAGE.get(stage_code)
    if nxt is None:
        return None, None
    scenario = {winner: _REACHED_CUM[nxt], loser: _REACHED_CUM.get(stage_code, 0)}
    win_word = "чемпион" if nxt == "CHAMPION" else f"в {_STAGE_WORD[nxt]}"
    labels = {winner: win_word, loser: f"вылет в {_STAGE_WORD.get(stage_code, '?')}"}
    return scenario, labels


def find_fixture(fixtures, team_a: str, team_b: str):
    """Найти матч между двумя командами в расписании (по нечётким именам, рус/англ)."""
    ak = sheet_reader._team_key(team_a)
    bk = sheet_reader._team_key(team_b)
    for f in fixtures:
        keys = {
            sheet_reader._team_key(f.home), sheet_reader._team_key(f.away),
            sheet_reader._team_key(f.home_en), sheet_reader._team_key(f.away_en),
        }
        if ak in keys and bk in keys:
            return f
    return None


def find_participant(standings, query: str):
    qk = "".join(ch for ch in query.lower() if ch.isalnum())
    if not qk:
        return None
    for p in standings:
        if qk in "".join(ch for ch in p.name.lower() if ch.isalnum()):
            return p
    return None


def chance_analysis(standings, me) -> dict:
    """Математическая проверка: может ли участник ещё стать первым.
    Если чей-то ТЕКУЩИЙ счёт уже больше твоего ПОТОЛКА — догнать его нельзя."""
    ceiling = me.potential_total or 0
    uncatchable = [
        p for p in standings
        if p.name != me.name and (p.total or 0) > ceiling
    ]
    ranked = sorted(standings, key=lambda p: -(p.total or 0))
    place = next(i for i, p in enumerate(ranked, 1) if p.name == me.name)
    leader = ranked[0]
    return {
        "place": place,
        "current": me.total or 0,
        "ceiling": ceiling,
        "leader_name": leader.name,
        "leader_current": leader.total or 0,
        "uncatchable": uncatchable,
        "can_be_first": not uncatchable,
    }
