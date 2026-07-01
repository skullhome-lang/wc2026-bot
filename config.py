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

# --- Поведение ---
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")
ANNOUNCE_HOURS_BEFORE = float(os.environ.get("ANNOUNCE_HOURS_BEFORE", "3"))
# Вероятность (0..1), что бот сам влезет с подколом в обычное сообщение
REPLY_PROBABILITY = float(os.environ.get("REPLY_PROBABILITY", "0.05"))
