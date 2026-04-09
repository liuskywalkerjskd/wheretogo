from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from rmuc_analyzer.models import QingflowSnapshot


def save_snapshot(cache_file: Path, snapshot: QingflowSnapshot) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "fetched_at": snapshot.fetched_at.isoformat(),
        "region_counts": snapshot.region_counts,
        "region_schools": snapshot.region_schools,
        "source_url": snapshot.source_url,
    }
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_snapshot(cache_file: Path) -> Optional[QingflowSnapshot]:
    if not cache_file.exists():
        return None

    with cache_file.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    fetched_at_raw = payload.get("fetched_at")
    fetched_at = datetime.fromisoformat(fetched_at_raw) if fetched_at_raw else datetime.now(timezone.utc)

    return QingflowSnapshot(
        fetched_at=fetched_at,
        region_counts=payload.get("region_counts", {}),
        region_schools=payload.get("region_schools", {}),
        source_url=payload.get("source_url", ""),
        stale=True,
    )
