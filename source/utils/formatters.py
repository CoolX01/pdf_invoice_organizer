from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional
import unicodedata


UNICODE_CHAR_REPLACEMENTS = str.maketrans(
    {
        "⻔": "门",
        "⻝": "食",
        "⻋": "车",
        "⻓": "长",
        "⻄": "西",
        "⻥": "鱼",
        "⺠": "民",
        "⽉": "月",
        "⽇": "日",
    }
)


def clean_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.translate(UNICODE_CHAR_REPLACEMENTS)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_amount(raw_value: str) -> Optional[float]:
    if not raw_value:
        return None
    cleaned = raw_value.replace("￥", "").replace(",", "").strip()
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def normalize_date(raw_value: str) -> str:
    raw_value = clean_text(raw_value)
    if not raw_value:
        return ""

    compact_value = re.sub(r"\s+", "", raw_value)

    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y年%m月%d日",
    ]
    for value in (raw_value, compact_value):
        for pattern in patterns:
            try:
                return datetime.strptime(value, pattern).strftime("%Y-%m-%d")
            except ValueError:
                continue

    if compact_value.isdigit() and len(compact_value) == 5:
        base = datetime(1899, 12, 30)
        try:
            return (base + timedelta(days=int(compact_value))).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    match = re.search(r"(20\d{2})[^\d]?(\d{1,2})[^\d]?(\d{1,2})", compact_value)
    if not match:
        return ""

    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).strftime("%Y-%m-%d")
    except ValueError:
        return ""
