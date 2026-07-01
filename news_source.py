"""Свежие футбольные новости из RSS-лент (бесплатно, без ключей).

Берём заголовки, отдаём боту для короткой сводки. Сеть (fetch_news) отделена от
разбора (parse_rss) — разбор тестируется офлайн.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return " ".join(html.unescape(s).split())


def parse_rss(xml_text: str, limit: int = 6) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = _clean(item.findtext("title") or "")
        summary = _clean(item.findtext("description") or "")
        if title:
            items.append({"title": title, "summary": summary[:200]})
        if len(items) >= limit:
            break
    return items


def fetch_news(urls: list[str], per_feed: int = 5, total: int = 10) -> list[dict]:
    import requests

    out: list[dict] = []
    seen = set()
    for url in urls:
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            for it in parse_rss(resp.text, per_feed):
                key = it["title"].lower()
                if key not in seen:
                    seen.add(key)
                    out.append(it)
        except Exception:  # noqa: BLE001 — недоступная лента не должна ронять бота
            continue
        if len(out) >= total:
            break
    return out[:total]
