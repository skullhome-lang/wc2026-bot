"""Живая память переписки: лог хронологии чата и реплик бота.

Заменяет «зашитое досье» об участниках. Бот больше не хранит личные факты —
вместо этого помнит РЕАЛЬНУЮ историю сообщений, чтобы:
  • припоминать, кто что писал раньше (и подкалывать за прошлые слова);
  • не повторять одни и те же шутки (видит свои недавние реплики).

Хранение — один JSON-файл data/history.json со списком записей, обрезаемым по
лимиту. Простой потокобезопасный аппенд под блокировкой; для нашей нагрузки
(камерная группа) этого с запасом достаточно.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

log = logging.getLogger("wc2026bot.memory")

_LOCK = threading.Lock()
_PATH = os.path.join(os.path.dirname(__file__), "history.json")
_MAX = 5000          # сколько записей держим суммарно (старое вытесняется)
_TEXT_CAP = 600      # обрезаем слишком длинные сообщения
_BOT = "__bot__"     # маркер реплики самого бота

# ВАЖНО: память — вспомогательная. Любой сбой ввода-вывода здесь НЕ должен ронять
# обработку сообщений бота. Поэтому все публичные функции гасят исключения.


def _load() -> list:
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError, OSError):
        return []


def _save(items: list) -> None:
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[-_MAX:], f, ensure_ascii=False)
    os.replace(tmp, _PATH)


def _append(entry: dict) -> None:
    with _LOCK:
        items = _load()
        items.append(entry)
        _save(items)


def log_message(chat_id: int, name: str, text: str) -> None:
    """Записать сообщение участника (никогда не бросает исключений)."""
    if not text:
        return
    try:
        _append({"t": time.time(), "chat": chat_id, "who": name, "text": text[:_TEXT_CAP]})
    except Exception:
        log.exception("memory.log_message failed")


def log_bot(chat_id: int, text: str) -> None:
    """Записать реплику бота (никогда не бросает; нужно для антиповтора шуток)."""
    if not text:
        return
    try:
        _append({"t": time.time(), "chat": chat_id, "who": _BOT, "text": text[:_TEXT_CAP]})
    except Exception:
        log.exception("memory.log_bot failed")


def recent_dialogue(chat_id: int, limit: int = 30) -> str:
    """Последние сообщения чата 'Имя: текст' (реплики бота — 'Ты (бот)'). Не бросает."""
    try:
        items = [e for e in _load() if e.get("chat") == chat_id]
        lines = []
        for e in items[-limit:]:
            who = "Ты (бот)" if e.get("who") == _BOT else e.get("who", "?")
            lines.append(f"{who}: {e.get('text', '')}")
        return "\n".join(lines)
    except Exception:
        log.exception("memory.recent_dialogue failed")
        return ""


def recent_jokes(chat_id: int, limit: int = 15) -> str:
    """Последние реплики бота — чтобы не повторять шутки. Не бросает."""
    try:
        items = [e for e in _load() if e.get("chat") == chat_id and e.get("who") == _BOT]
        return "\n".join(f"- {e.get('text', '')}" for e in items[-limit:])
    except Exception:
        log.exception("memory.recent_jokes failed")
        return ""
