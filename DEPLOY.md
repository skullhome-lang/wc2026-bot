# 🚀 Запуск бота 24/7

Боту нужен всегда включённый сервер. Рекомендация — небольшой **VPS на Ubuntu**:
самый надёжный вариант для бота на long polling. Подойдёт любой за ~300–500₽/мес
(Timeweb / Beget — оплата в рублях) или ~€4/мес (Hetzner CX22 — нужна зарубежная карта).

**Перед деплоем** (один раз, в @BotFather):
- `/setprivacy` → выбрать бота → **Disable** — чтобы бот видел сообщения в группе.
- Добавь бота в группу участников турнира.

---

## Вариант A. VPS + systemd (рекомендуется)

1. Создай VPS (Ubuntu 22/24), зайди по SSH.
2. Поставь зависимости системы:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv
   ```
3. Скопируй папку проекта на сервер в `/opt/wc2026-bot` (вместе с файлом `.env`).
   Например, с локального компа: `scp -r wc2026-bot root@IP:/opt/`
4. Окружение и зависимости:
   ```bash
   cd /opt/wc2026-bot
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
5. Узнай `chat_id` группы: запусти разово `.venv/bin/python bot.py`, напиши в группе
   `/chatid`, скопируй число в `.env` → `TELEGRAM_CHAT_ID=...`, останови (Ctrl+C).
6. Поставь автозапуск:
   ```bash
   sudo cp wc2026-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now wc2026-bot
   ```
7. Логи в реальном времени: `journalctl -u wc2026-bot -f`

> Если папка не в `/opt/wc2026-bot` — поправь пути в `wc2026-bot.service`.

---

## Вариант B. Docker (любой хост)

```bash
echo '{}' > bot_state.json          # чтобы состояние сохранялось между перезапусками
docker build -t wc2026-bot .
docker run -d --name wc2026-bot --restart=always \
  --env-file .env \
  -v "$(pwd)/bot_state.json:/app/bot_state.json" \
  wc2026-bot
docker logs -f wc2026-bot
```

---

## Вариант C. Свой компьютер (для теста)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```
Минус — бот работает, только пока компьютер включён и не спит.

---

## Первый запуск — проверка вживую
- В группе набери `/table` → бот должен прислать разбор таблицы (первая реальная
  генерация Claude). Это же проверит, что ключ Anthropic и модель валидны.
- `/next` → ближайшие матчи из расписания (проверка ключа football-data).
- Если `/table` ругается на модель — поправь `MODEL_MAIN` / `MODEL_FAST` в `.env`.
- Дальше анонсы и итоги бот будет слать сам.
