from __future__ import annotations

from typing import Any


def load_account_lookup(account_map: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    accounts = account_map.get("accounts", {})
    for canonical, spec in accounts.items():
        for concept in spec.get("concepts", []):
            lookup[str(concept)] = canonical
        for name in spec.get("approved_names", []):
            lookup[f"name:{name}"] = canonical
    return lookup


_PLACEHOLDER_IDS = {"", "-", "-표준계정코드 미사용-", "null", "None"}


def map_account(account_id: str | None, account_nm: str | None, lookup: dict[str, str]) -> str | None:
    aid = (account_id or "").strip()
    if aid and aid not in _PLACEHOLDER_IDS:
        if aid in lookup:
            return lookup[aid]
        if aid.startswith("ifrs-") or aid.startswith("dart_"):
            return None
    name = (account_nm or "").strip()
    if name and f"name:{name}" in lookup:
        return lookup[f"name:{name}"]
    for key, canonical in lookup.items():
        if not key.startswith("name:"):
            continue
        label = key[5:]
        if name == label:
            return canonical
        if len(label) >= 4 and name.startswith(label) and name[len(label) : len(label) + 1] in {"(", "（"}:
            return canonical
    return None


def normalize_amount(value: Any, sign: str = "+") -> float | None:
    if value is None or value == "" or str(value) in {"-", "null"}:
        return None
    text = str(value).replace(",", "").replace(" ", "")
    try:
        num = float(text)
    except ValueError:
        return None
    if sign == "outflow_abs":
        return abs(num)
    return num
