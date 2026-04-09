from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize_school_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("·", "")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def clean_text(text: str) -> str:
    cleaned = (text or "").replace("\xa0", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def parse_int(text: str) -> Optional[int]:
    if text is None:
        return None
    match = re.search(r"-?\d+", str(text))
    if not match:
        return None
    return int(match.group(0))
