"""Связка Telegram user_id -> участник турнира (кто есть кто).

Заполняется командой /iam и хранится в файле, чтобы бот узнавал людей без @username.
"""
from __future__ import annotations

import json
import os

_PATH = os.environ.get("IDENTITY_PATH", "identities.json")


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


def get_name(user_id) -> str | None:
    return _load().get(str(user_id))


def set_name(user_id, name: str) -> None:
    data = _load()
    data[str(user_id)] = name
    _save(data)
