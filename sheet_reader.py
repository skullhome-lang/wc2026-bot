"""Чтение турнирной Google-таблицы через публичный CSV-экспорт (gviz).

Сеть (fetch_csv) отделена от разбора (parse_*), чтобы логику можно было
тестировать на сохранённом CSV без обращения к сети.
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # очень старый Python без zoneinfo
    ZoneInfo = None

SHEET_ID = os.environ.get("SHEET_ID", "1QCXWhUI5JAIG2otuMykCKcAFllWWk-voEAMM47RZf1I")
GID_STANDINGS = int(os.environ.get("GID_STANDINGS", "1174225275"))
GID_MATCHES = int(os.environ.get("GID_MATCHES", "61546759"))  # вкладка с результатами/счётом
GID_POTENTIAL = int(os.environ.get("GID_POTENTIAL", "920965875"))  # матрица прогнозов/потенциала

CSV_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}"


@dataclass
class Participant:
    avatar: str
    name: str
    r1: float | None          # очки 1 этапа (группы)
    r2: float | None          # очки 2 этапа (плейофф)
    total: float | None       # очки всего
    potential_playoff: float | None
    potential_total: float | None
    failed_playoff: str = ""   # «подвели» в плейофф (флаги команд)
    failed_group: str = ""     # «подвели» на 1 этапе
    surprised_group: str = ""  # «удивили» на 1 этапе


def _num(s: str | None):
    s = (s or "").strip().replace(" ", "").replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_csv(gid) -> str:
    """Скачать одну вкладку как CSV-текст (используется ботом в рантайме)."""
    import requests  # ленивый импорт: парсер тестируется без сети

    url = CSV_URL.format(sheet_id=SHEET_ID, gid=gid)
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_standings(csv_text: str) -> list[Participant]:
    people: list[Participant] = []
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 8:
            continue
        total = _num(row[7])
        name = (row[1] or "").strip()
        if total is None or not name:
            continue  # заголовок / пустые строки
        people.append(
            Participant(
                avatar=(row[0] or "").strip(),
                name=name,
                r1=_num(row[4]),
                r2=_num(row[6]),
                total=total,
                potential_playoff=_num(row[8]) if len(row) > 8 else None,
                potential_total=_num(row[9]) if len(row) > 9 else None,
                failed_playoff=row[10].strip() if len(row) > 10 else "",
                failed_group=row[11].strip() if len(row) > 11 else "",
                surprised_group=row[12].strip() if len(row) > 12 else "",
            )
        )
    return people


def standings_sorted(people: list[Participant]) -> list[Participant]:
    return sorted(people, key=lambda p: (-(p.total or 0), p.name))


def get_standings() -> list[Participant]:
    """Боевой путь: скачать и разобрать таблицу лидеров."""
    return standings_sorted(parse_standings(fetch_csv(GID_STANDINGS)))


# --------------------------------------------------------------------------- #
#  МАТЧИ / РЕЗУЛЬТАТЫ                                                          #
# --------------------------------------------------------------------------- #
@dataclass
class Match:
    dt: datetime | None       # дата-время начала (МСК), если распознано
    date_raw: str
    home: str
    away: str
    home_goals: int | None
    away_goals: int | None
    stage: str                # GROUP_STAGE, LAST_32, LAST_16, ...
    winner: str               # пусто = ничья или ещё не сыгран

    @property
    def played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    @property
    def score(self) -> str:
        return f"{self.home_goals}:{self.away_goals}" if self.played else ""

    @property
    def key(self) -> str:
        """Стабильный идентификатор матча (защита от повторных постов)."""
        return f"{self.date_raw}|{self.home}|{self.away}"


def _parse_score(s: str | None):
    s = (s or "").strip()
    if ":" not in s:
        return None, None
    a, _, b = s.partition(":")
    try:
        return int(a.strip()), int(b.strip())
    except ValueError:
        return None, None


def _parse_dt(s: str, year: int = 2026, tz: str = "Europe/Moscow"):
    try:
        datepart, timepart = s.strip().split()
        day, month = datepart.split(".")
        hh, mm = timepart.split(":")
        dt = datetime(year, int(month), int(day), int(hh), int(mm))
        if ZoneInfo is not None:
            dt = dt.replace(tzinfo=ZoneInfo(tz))
        return dt
    except (ValueError, AttributeError):
        return None


def parse_matches(csv_text: str, tz: str = "Europe/Moscow") -> list[Match]:
    matches: list[Match] = []
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 5:
            continue
        if row[0].strip().lower() in ("дата", "date", ""):
            continue  # заголовок
        home, away = row[1].strip(), row[3].strip()
        if not home or not away:
            continue
        hg, ag = _parse_score(row[2])
        matches.append(
            Match(
                dt=_parse_dt(row[0], tz=tz),
                date_raw=row[0].strip(),
                home=home,
                away=away,
                home_goals=hg,
                away_goals=ag,
                stage=row[4].strip(),
                winner=row[5].strip() if len(row) > 5 else "",
            )
        )
    return matches


def completed_matches(matches: list[Match]) -> list[Match]:
    """Сыгранные матчи, по времени (старые → новые); матчи без даты в конце."""
    done = [m for m in matches if m.played]
    done.sort(key=lambda m: (m.dt is None, m.dt or datetime.max))
    return done


def get_matches(tz: str = "Europe/Moscow") -> list[Match]:
    return parse_matches(fetch_csv(GID_MATCHES), tz=tz)


# --------------------------------------------------------------------------- #
#  МАТРИЦА ПРОГНОЗОВ / ПОТЕНЦИАЛА  (у кого что на кону по каждой команде)      #
# --------------------------------------------------------------------------- #
# Во вкладке три таблицы подряд с одинаковыми колонками-участниками:
#   1) прогнозы (потолок очков по команде),  2) «Факт на текущий момент»
#   (уже реализовано),  3) «ПОТЕНЦИАЛ» (сколько ещё можно взять с команды).
_MATRIX_MARKERS = {
    "", "проверка", "факт на текущий момент", "потенциал",
    "общий потенцеал в по", "очков на данный момент в по",
    "сколько ещё может набрать в п/о", "сколько еще может набрать в п/о",
    "сколько всего может набрать очков",
}

# Потолок очков по команде -> до какой стадии участник поставил команду.
# Очки за ПОБЕДУ в раунде плейофф: 1/16=0.5, +1/8=+1, +1/4=+2, +1/2=+3, финал=+4.
# 0.5 = прошла 1/16 (дошла до 1/8 финала), 1.5 = до 1/4, 3.5 = до 1/2,
# 6.5 = до финала, 10.5 = чемпион.
_PRED_LABEL = {10.5: "в чемпионы", 6.5: "в финал", 3.5: "до 1/2",
               1.5: "до 1/4", 0.5: "до 1/8"}


def predicted_label(value: float | None) -> str:
    return _PRED_LABEL.get(value or 0, "")


def parse_potential_matrix(csv_text: str) -> dict:
    """Вернуть {players, prediction, realized, remaining}, где каждый блок —
    это {команда: {участник: очки}}."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    players: list[str] = []
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) > 3 and row[1].strip().upper() == "ИСТИНА":
            end = len(row)
            for j in range(2, len(row)):
                if row[j].strip().lower() == "итого":
                    end = j
                    break
            players = [row[j].strip() for j in range(2, end)]
            header_idx = i
            break
    if header_idx is None:
        return {"players": [], "prediction": {}, "realized": {}, "remaining": {}}

    blocks = {"prediction": {}, "realized": {}, "remaining": {}}
    current = "prediction"
    for row in rows[header_idx + 1:]:
        label = (row[0] if row else "").strip()
        low = label.lower()
        if low == "факт на текущий момент":
            current = "realized"
            continue
        if low == "потенциал":
            current = "remaining"
            continue
        if low in _MATRIX_MARKERS:
            continue
        vals = {}
        for k, player in enumerate(players):
            col = 2 + k
            vals[player] = _num(row[col]) if col < len(row) else None
        blocks[current][label] = vals
    return {"players": players, **blocks}


def stakes_for_match(matrix: dict, team_a: str, team_b: str) -> dict:
    """Кто и сколько ещё может взять с каждой из двух команд (по убыванию)."""
    out: dict[str, list[tuple[str, float, float]]] = {}
    for team in (team_a, team_b):
        remaining = matrix.get("remaining", {}).get(team, {})
        prediction = matrix.get("prediction", {}).get(team, {})
        lst = [
            (player, val, prediction.get(player) or 0)
            for player, val in remaining.items()
            if val and val > 0
        ]
        lst.sort(key=lambda x: (-x[1], -x[2], x[0]))
        out[team] = lst
    return out


def _team_key(name: str) -> str:
    """Ключ для нечёткого сравнения названий команд (без дефисов/пробелов/регистра)."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def find_team(matrix: dict, query: str) -> str | None:
    """Найти команду в матрице по нечёткому запросу («Кот Дивуар» → «Кот-д'Ивуар»)."""
    qk = _team_key(query)
    if not qk:
        return None
    teams = list(matrix.get("prediction", {})) or list(matrix.get("remaining", {}))
    for t in teams:                       # точное совпадение
        if _team_key(t) == qk:
            return t
    for t in teams:                       # вхождение в любую сторону
        tk = _team_key(t)
        if tk and (qk in tk or tk in qk):
            return t
    return None


def team_backers(matrix: dict, team: str, block: str = "prediction"):
    """Кто поставил на команду: [(участник, очки-потолок)] по убыванию."""
    data = matrix.get(block, {}).get(team, {})
    lst = [(p, v) for p, v in data.items() if v and v > 0]
    lst.sort(key=lambda x: (-x[1], x[0]))
    return lst


def format_predictions_digest(matrix: dict, block: str = "prediction") -> str:
    """Компактный конспект «кто на кого ставил» по всем командам (только ненулевые)."""
    lines = []
    for team, data in matrix.get(block, {}).items():
        backers = [(p, v) for p, v in data.items() if v and v > 0]
        if not backers:
            continue
        backers.sort(key=lambda x: (-x[1], x[0]))
        parts = [
            f"{p} ({v}{', ' + predicted_label(v) if predicted_label(v) else ''})"
            for p, v in backers
        ]
        lines.append(f"{team}: " + ", ".join(parts))
    return "\n".join(lines)


def get_potential() -> dict:
    return parse_potential_matrix(fetch_csv(GID_POTENTIAL))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:  # тест на локальном CSV
        with open(sys.argv[1], encoding="utf-8") as f:
            people = parse_standings(f.read())
    else:
        people = get_standings()

    people = standings_sorted(people)
    print(f"{'#':>2}  {'Участник':<24}{'1р':>5}{'2р':>5}{'Итого':>7}{'Потенц.':>9}")
    print("-" * 56)
    for i, p in enumerate(people, 1):
        print(
            f"{i:>2}. {p.avatar} {p.name:<22}"
            f"{p.r1!s:>5}{p.r2!s:>5}{p.total!s:>7}{p.potential_total!s:>9}"
        )
