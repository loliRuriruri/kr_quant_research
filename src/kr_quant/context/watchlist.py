from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def watchlist_path(root: Path) -> Path:
    return root / "data" / "watchlist.json"


def load_watchlist(root: Path) -> list[dict[str, Any]]:
    path = watchlist_path(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_watchlist(root: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = watchlist_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def add_ticker(root: Path, ticker: str, company: str | None = None, note: str = "") -> list[dict[str, Any]]:
    from kr_quant.universe.identifiers import canonical_ticker

    code = canonical_ticker(ticker)
    if not code:
        return load_watchlist(root)
    rows = [r for r in load_watchlist(root) if canonical_ticker(r.get("ticker")) != code]
    rows.insert(
        0,
        {
            "ticker": code,
            "company": company or code,
            "note": note,
            "added_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return save_watchlist(root, rows)


def remove_ticker(root: Path, ticker: str) -> list[dict[str, Any]]:
    from kr_quant.universe.identifiers import canonical_ticker

    code = canonical_ticker(ticker)
    rows = [r for r in load_watchlist(root) if canonical_ticker(r.get("ticker")) != code]
    return save_watchlist(root, rows)
