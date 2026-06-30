"""«Мозг» бота: личность + генерация текстов через Claude API.

Чистые функции сборки промптов (format_*/build_*) отделены от сетевого вызова
(_complete), чтобы их можно было тестировать без ключа и без обращения к API.
"""
from __future__ import annotations

from sheet_reader import Participant

# --------------------------------------------------------------------------- #
#  ЛИЧНОСТЬ                                                                    #
# --------------------------------------------------------------------------- #
PERSONALITY = """\
Ты — ведущий и комментатор турнира прогнозов на ЧМ-2026 в Telegram-группе из 16 друзей.
Это закрытая компания своих, все играют на деньги (взнос 2000₽), все друг друга знают.

ХАРАКТЕР:
- Дерзкий, острый на язык спортивный шоумен. Трэш-ток, подколы, кураж — как в раздевалке.
- Подкалываешь по-доброму, но с зубами. Это дружеский стёб, а не травля.
- Живой разговорный русский. Эмодзи — в меру (1–3 на сообщение), к месту.

КАК ОБРАЩАЕШЬСЯ:
- Зовёшь участников по имени и/или по их аватарке-животному (🦉 Стрюков, 🦝 Никульшин и т.п.).
- Любишь приплести цифры из таблицы: очки, потенциал, кого «подвели» и «удивили» команды.

ЖЁСТКИЕ ПРАВИЛА:
- Опирайся ТОЛЬКО на факты и числа, которые даны во входных данных. Никогда не выдумывай
  счёт, голы, события матчей или цифры. Не знаешь — не утверждай.
- Подкалывай исключительно за прогнозы и футбольные выборы. НИКОГДА не шути про внешность,
  национальность, религию, пол, семью или что-то личное. Без мата.
- Коротко: 2–5 предложений, формат телеграма. Без простыней и без занудных списков.
- Не повторяй одни и те же шутки и формулировки.

ОБРАЗЦЫ ТВОЕГО ТОНА (стиль, а не шаблон — каждый раз придумывай заново):
1) «🇩🇪 Германия вышла на пенальти как на эшафот, и Парагвай дёрнул рычаг. Полтаблицы
   держало немцев в фаворитах — собирайте кости, ваш "надёжный" уехал домой бизнес-классом.»
2) «🦉 Стрюков, ноль в плейофф — это талант: собрать сетку, где не зашло вообще ничего.
   Переверни прогноз вверх ногами и внезапно возглавишь таблицу.»
3) «🦝 Никульшин на вершине (29.5), и его единственная боль — та самая Германия. Сидит
   наверху и тихонько потеет, как будто мы не видим.»
"""


# --------------------------------------------------------------------------- #
#  ЧИСТЫЕ ХЕЛПЕРЫ (без сети)                                                   #
# --------------------------------------------------------------------------- #
def format_standings(people: list[Participant]) -> str:
    """Компактная таблица лидеров для подстановки в промпт."""
    ranked = sorted(people, key=lambda p: (-(p.total or 0), p.name))
    lines = []
    for i, p in enumerate(ranked, 1):
        lines.append(
            f"{i}. {p.avatar} {p.name} — всего {p.total} "
            f"(1р {p.r1} / 2р {p.r2}), потенциал ИТОГО {p.potential_total}"
        )
    return "\n".join(lines)


def build_roast_prompt(people: list[Participant], event_note: str = "") -> str:
    note = f"\nПовод / свежие события:\n{event_note}\n" if event_note else ""
    return (
        "Текущая турнирная таблица:\n"
        f"{format_standings(people)}\n{note}\n"
        "Напиши дерзкий разбор расклада для группы: пройдись по лидеру и аутсайдеру, "
        "подметь что-то смешное в цифрах, подколи 1–2 участников. 3–5 предложений."
    )


def build_prematch_prompt(match_info: str, stakes: str = "") -> str:
    stakes_block = f"\nЧто на кону у участников:\n{stakes}\n" if stakes else ""
    return (
        f"Скоро матч:\n{match_info}\n{stakes_block}\n"
        "Напиши задорный анонс-расклад перед матчем: подведи интригу, напомни, у кого из "
        "участников на этот матч завязаны очки, добавь дерзкий прогноз-провокацию. 3–5 предложений."
    )


def build_postmatch_prompt(match_info: str, stakes: str = "", facts: str = "") -> str:
    blocks = ""
    if stakes:
        blocks += f"\nУ кого что было на кону:\n{stakes}\n"
    if facts:
        blocks += f"\nФакты/цифры матча:\n{facts}\n"
    return (
        f"Матч завершён:\n{match_info}\n{blocks}\n"
        "Подбей итоги для группы: кто на этом матче поднялся, а кого результат подкосил. "
        "Добавь 1 интересный факт и фирменный подкол. Только реальные данные. 3–5 предложений."
    )


# --------------------------------------------------------------------------- #
#  ВЫЗОВ МОДЕЛИ (ленивые импорты, чтобы модуль грузился без ключа)             #
# --------------------------------------------------------------------------- #
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        import config

        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _model(fast: bool = False) -> str:
    import config

    return config.MODEL_FAST if fast else config.MODEL_MAIN


def _complete(user_prompt: str, *, fast: bool = False, max_tokens: int = 600,
              temperature: float = 1.0) -> str:
    msg = _get_client().messages.create(
        model=_model(fast),
        max_tokens=max_tokens,
        temperature=temperature,
        system=PERSONALITY,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# --------------------------------------------------------------------------- #
#  ПУБЛИЧНЫЕ ГЕНЕРАТОРЫ                                                        #
# --------------------------------------------------------------------------- #
def standings_roast(people: list[Participant], event_note: str = "") -> str:
    return _complete(build_roast_prompt(people, event_note))


def prematch_breakdown(match_info: str, stakes: str = "") -> str:
    return _complete(build_prematch_prompt(match_info, stakes))


def postmatch_summary(match_info: str, stakes: str = "", facts: str = "") -> str:
    return _complete(build_postmatch_prompt(match_info, stakes, facts))


def chat_reply(user_name: str, text: str, context: str = "") -> str:
    ctx = f"\nКонтекст турнира:\n{context}\n" if context else ""
    prompt = (
        f"Участник {user_name} написал в группе: «{text}»{ctx}\n"
        "Ответь коротко и дерзко в своём стиле (1–3 предложения)."
    )
    return _complete(prompt, fast=True, max_tokens=300)
