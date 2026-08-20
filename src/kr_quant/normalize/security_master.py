from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kr_quant.ingest.krx import parse_krx_number


def normalize_krx_rows(rows: list[dict[str, Any]], market: str, as_of: date) -> pd.DataFrame:
    recs = []
    for raw in rows:
        ticker = str(raw.get("ISU_SRT_CD") or raw.get("ISU_CD") or "")[-6:]
        isu_cd = str(raw.get("ISU_CD") or ticker)
        close = parse_krx_number(raw.get("TDD_CLSPRC"))
        recs.append(
            {
                "security_id": isu_cd,
                "ticker": ticker,
                "company": raw.get("ISU_NM") or raw.get("ISU_ABBRV"),
                "market": market,
                "trade_date": as_of,
                "open": parse_krx_number(raw.get("TDD_OPNPRC")),
                "high": parse_krx_number(raw.get("TDD_HGPRC")),
                "low": parse_krx_number(raw.get("TDD_LWPRC")),
                "close": close,
                "adj_close": None,
                "volume": parse_krx_number(raw.get("ACC_TRDVOL")),
                "trading_value": parse_krx_number(raw.get("ACC_TRDVAL")),
                "market_cap": parse_krx_number(raw.get("MKTCAP")),
                "listed_shares": parse_krx_number(raw.get("LIST_SHRS")),
                "kind": raw.get("KIND_STKCERT_TP_NM") or "",
                "secu_group": raw.get("SECUGRP_NM") or "",
            }
        )
    return pd.DataFrame(recs)


def dart_corp_crosswalk(stock_code: str, corp_map: pd.DataFrame) -> str | None:
    if corp_map.empty:
        return None
    hit = corp_map[corp_map["stock_code"].astype(str).str.zfill(6) == str(stock_code).zfill(6)]
    if hit.empty:
        return None
    return str(hit.iloc[0]["corp_code"]).zfill(8)
