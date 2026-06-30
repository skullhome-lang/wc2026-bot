"""Простое JSON-хранилище состояния (что уже анонсировано / по чему отчитались).

Нужно, чтобы после перезапуска бот не присылал анонсы и итоги повторно.
"""
from __future__ import annotations

import json
import os

_PATH = os.environ.get("STATE_PATH", "bot_state.json")
_DEFAULT = {"announced": [], "resulted": []}


def load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULT)
    for key, val in _DEFAULT.items():
        data.setdefault(key, list(val))
    return data


def save(state: dict) -> None:
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)
