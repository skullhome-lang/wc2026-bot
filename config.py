"""Конфигурация бота: читается из переменных окружения (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Не задана переменная окружения {key} (см. .env.example)")
    return val


# --- Telegram ---
TELEGRAM_BOT_TOKEN = _required("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or None
if TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = int(TELEGRAM_CHAT_ID)

# --- Claude ---
ANTHROPIC_API_KEY = _required("ANTHROPIC_API_KEY")
MODEL_MAIN = os.environ.get("MODEL_MAIN", "claude-sonnet-4-6")
MODEL_FAST = os.environ.get("MODEL_FAST", "claude-haiku-4-5-20251001")

# --- Турнир ---
SHEET_ID = os.environ.get("SHEET_ID", "1QCXWhUI5JAIG2otuMykCKcAFllWWk-voEAMM47RZf1I")
GID_STANDINGS = int(os.environ.get("GID_STANDINGS", "1174225275"))
GID_MATCHES = int(os.environ.get("GID_MATCHES", "61546759"))
GID_POTENTIAL = os.environ.get("GID_POTENTIAL") or None  # матрица «у кого что на кону»

# --- Расписание (football-data.org, бесплатный ключ) ---
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY") or None

# --- Котировки букмекеров (the-odds-api.com, бесплатный ключ) ---
ODDS_API_KEY = os.environ.get("ODDS_API_KEY") or None

# --- Новости (RSS-ленты футбола, без ключей) ---
# Google News RSS — доступен с сервера (championat/ria блокируются на уровне сети VPS).
# Запрос «футбол чемпионат мира» на русском. В URL нет запятых — не ломает split ниже.
_DEFAULT_RSS = (
    "https://news.google.com/rss/search?q=%D1%84%D1%83%D1%82%D0%B1%D0%BE%D0%BB%20"
    "%D1%87%D0%B5%D0%BC%D0%BF%D0%B8%D0%BE%D0%BD%D0%B0%D1%82%20%D0%BC%D0%B8%D1%80%D0%B0"
    "&hl=ru&gl=RU&ceid=RU:ru"
)
NEWS_RSS = [u.strip() for u in os.environ.get("NEWS_RSS", _DEFAULT_RSS).split(",") if u.strip()]

# --- Админы (кому можно вещать от имени бота через /say) ---
# По умолчанию — Кравченко Константин. Переопределяется переменной ADMIN_IDS
# (через запятую или пробел). Пример: ADMIN_IDS=436853096,123456789
_DEFAULT_ADMIN = "436853096"
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", _DEFAULT_ADMIN).replace(",", " ").split()
    if x.strip().isdigit()
}

# --- Поведение ---
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")
ANNOUNCE_HOURS_BEFORE = float(os.environ.get("ANNOUNCE_HOURS_BEFORE", "3"))
# Вероятность (0..1), что бот сам влезет с подколом в обычное сообщение
REPLY_PROBABILITY = float(os.environ.get("REPLY_PROBABILITY", "0.05"))
