# ⚽ Бот турнира прогнозов ЧМ-2026

Telegram-бот для группы участников турнира ставок на ЧМ-2026. Говорит по-русски и
работает 24/7: анонсирует матчи, делает пред-матчевые расклады (у кого что на кону),
после матчей подбивает статистику с интересными фактами и по-доброму подкалывает
участников. Источник правды — Google-таблица турнира.

## Архитектура
- `sheet_reader.py` — чтение таблицы (участники, результаты, очки) через публичный CSV.
- `brain.py` — личность бота и генерация текстов через Claude API.
- `bot.py` — Telegram (long polling): реакции в чате и команды.
- `scheduler.py` — авто-анонсы перед матчами и итоги после.
- `config.py` — все настройки из `.env`.

## Что нужно подготовить один раз
1. **Бот в Telegram.** @BotFather → `/newbot` → получить **TOKEN**.
   Затем отключить приватность, чтобы бот видел сообщения в группе:
   @BotFather → `/setprivacy` → выбрать бота → **Disable**.
2. **Ключ Anthropic.** console.anthropic.com → API Keys → Create Key. Пополнить баланс (~$5).
3. **Ключ football-data.org** (бесплатно, для расписания матчей):
   [регистрация](https://www.football-data.org/client/register) → подтвердить email → скопировать токен.
4. Скопировать `.env.example` → `.env` и заполнить значения.

## Установка и запуск (локально)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # заполнить TOKEN и ключ
python bot.py
```

## Проверка чтения таблицы
```bash
python sheet_reader.py                      # живая таблица
python sheet_reader.py data/standings_sample.csv   # тест на примере
```

## Хостинг 24/7
См. **DEPLOY.md** — пошаговая инструкция (VPS + systemd, Docker или свой компьютер).
