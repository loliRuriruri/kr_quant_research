from __future__ import annotations

from collections import defaultdict
from typing import Any
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    return tag.split("}")[-1] if tag else ""


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return str(el.text).strip()


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for child in list(el):
        if _local(child.tag) == name:
            return child
    return None


def _num(text: str) -> int:
    raw = (text or "").replace(",", "").replace("$", "").strip()
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_infotable(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    for el in root.iter():
        if _local(el.tag) != "infoTable":
            continue
        shrs = _child(el, "shrsOrPrnAmt")
        rows.append(
            {
                "issuer": _text(_child(el, "nameOfIssuer")),
                "class": _text(_child(el, "titleOfClass")),
                "cusip": _text(_child(el, "cusip")).upper(),
                "value": _num(_text(_child(el, "value"))),
                "shares": _num(_text(_child(shrs, "sshPrnamt") if shrs is not None else None)),
                "share_type": _text(_child(shrs, "sshPrnamtType") if shrs is not None else None) or "SH",
            }
        )
    return [r for r in rows if r.get("cusip")]


def aggregate_holdings(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for row in rows:
        cusip = str(row.get("cusip") or "").upper()
        if not cusip:
            continue
        cur = by.setdefault(
            cusip,
            {
                "cusip": cusip,
                "issuer": row.get("issuer") or cusip,
                "class": row.get("class") or "",
                "value": 0,
                "shares": 0,
            },
        )
        cur["value"] += int(row.get("value") or 0)
        cur["shares"] += int(row.get("shares") or 0)
        if row.get("issuer"):
            cur["issuer"] = str(row["issuer"])
    total = sum(v["value"] for v in by.values()) or 1
    for item in by.values():
        item["weight"] = item["value"] / total
    return by


def compare_holdings(
    prev: dict[str, dict[str, Any]],
    curr: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = set(prev) | set(curr)
    out: list[dict[str, Any]] = []
    for cusip in keys:
        a = prev.get(cusip)
        b = curr.get(cusip)
        if a is None and b is not None:
            action = "new"
        elif a is not None and b is None:
            action = "exit"
        elif b is not None and a is not None and b["shares"] > a["shares"]:
            action = "increase"
        elif b is not None and a is not None and b["shares"] < a["shares"]:
            action = "decrease"
        else:
            action = "hold"
        src = b or a or {}
        prev_val = int(a["value"]) if a else 0
        curr_val = int(b["value"]) if b else 0
        prev_sh = int(a["shares"]) if a else 0
        curr_sh = int(b["shares"]) if b else 0
        out.append(
            {
                "cusip": cusip,
                "issuer": src.get("issuer") or cusip,
                "action": action,
                "value": curr_val,
                "prev_value": prev_val,
                "value_delta": curr_val - prev_val,
                "shares": curr_sh,
                "prev_shares": prev_sh,
                "weight": float(b["weight"]) if b else 0.0,
                "prev_weight": float(a["weight"]) if a else 0.0,
            }
        )
    out.sort(key=lambda r: abs(int(r.get("value_delta") or 0)), reverse=True)
    return out


def common_holdings(
    filer_holdings: dict[str, dict[str, dict[str, Any]]],
    min_filers: int = 2,
) -> list[dict[str, Any]]:
    owners: dict[str, list[str]] = defaultdict(list)
    meta: dict[str, dict[str, Any]] = {}
    for filer, book in filer_holdings.items():
        for cusip, row in book.items():
            owners[cusip].append(filer)
            slot = meta.setdefault(cusip, {"issuer": row.get("issuer") or cusip, "value": 0, "filers": []})
            slot["issuer"] = row.get("issuer") or slot["issuer"]
            slot["value"] += int(row.get("value") or 0)
    rows: list[dict[str, Any]] = []
    for cusip, names in owners.items():
        if len(names) < min_filers:
            continue
        info = meta[cusip]
        rows.append(
            {
                "cusip": cusip,
                "issuer": info["issuer"],
                "n_filers": len(names),
                "filers": sorted(names),
                "value": info["value"],
            }
        )
    rows.sort(key=lambda r: (int(r["n_filers"]), int(r["value"])), reverse=True)
    return rows


def trend_rows(filer_changes: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    tally: dict[str, dict[str, Any]] = {}
    for filer, changes in filer_changes.items():
        for row in changes:
            cusip = row["cusip"]
            slot = tally.setdefault(
                cusip,
                {
                    "cusip": cusip,
                    "issuer": row.get("issuer") or cusip,
                    "new": 0,
                    "increase": 0,
                    "decrease": 0,
                    "exit": 0,
                    "hold": 0,
                    "value_delta": 0,
                    "buyers": [],
                    "sellers": [],
                },
            )
            action = row.get("action")
            if action in slot:
                slot[action] += 1
            slot["value_delta"] += int(row.get("value_delta") or 0)
            if action in {"new", "increase"}:
                slot["buyers"].append(filer)
            elif action in {"exit", "decrease"}:
                slot["sellers"].append(filer)
    rows = list(tally.values())
    for row in rows:
        row["score"] = (row["new"] + row["increase"]) - (row["exit"] + row["decrease"])
    rows.sort(key=lambda r: (int(r["score"]), int(r["value_delta"])), reverse=True)
    return rows
