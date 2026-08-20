"""Industry ranking overlay from scored names. used_in_quant=false."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kr_quant.settings import Settings

MIN_N = 4
STATE_KO = {
    "LEADING": "선행",
    "IMPROVING": "개선",
    "NEUTRAL": "보통",
    "WEAKENING": "약화",
    "LAGGING": "부진",
}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _pct_rank(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=float)
    n = len(arr)
    if n <= 1:
        return [0.5] * n
    order = arr.argsort()
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.linspace(0, 1, n)
    return ranks.tolist()


def _state(score: float, delta: float | None) -> str:
    d = 0.0 if delta is None else float(delta)
    if score >= 80 and d >= 0:
        return "LEADING"
    if score >= 65 and d > 3:
        return "IMPROVING"
    if score >= 65:
        return "LEADING"
    if score >= 40:
        return "NEUTRAL"
    if score < 35 or d < -5:
        return "LAGGING"
    return "WEAKENING"


def _load_holdings(settings: Settings) -> pd.DataFrame:
    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "universe_eligible" in df.columns:
        df = df[df["universe_eligible"] == True]  # noqa: E712
    if "industry" in df.columns:
        bucket = df["industry"]
        if "sector" in df.columns:
            bucket = bucket.fillna(df["sector"])
        df["bucket"] = bucket.fillna("미분류")
    elif "sector" in df.columns:
        df["bucket"] = df["sector"].fillna("미분류")
    else:
        df["bucket"] = "미분류"
    return df


def _cache_path(settings: Settings) -> Path:
    return settings.root / "data" / "cache" / "sector_rank.json"


def _prev_scores(settings: Settings) -> dict[str, float]:
    path = _cache_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(r["name"]): float(r["score"]) for r in data.get("rows") or [] if r.get("name") and r.get("score") is not None}


def rank_sectors(settings: Settings) -> dict[str, Any]:
    df = _load_holdings(settings)
    if df.empty:
        return {
            "configured": False,
            "used_in_quant": False,
            "error": "조건 통과 종목 결과가 없습니다.",
            "rows": [],
        }
    prev = _prev_scores(settings)
    market_ret = float(_num(df.get("return_3m", pd.Series(dtype=float))).mean() or 0)
    groups: list[dict[str, Any]] = []
    for name, g in df.groupby("bucket"):
        n = int(len(g))
        if n < MIN_N:
            continue
        ret3 = _num(g.get("return_3m", pd.Series(dtype=float)))
        ret6 = _num(g.get("return_6m", pd.Series(dtype=float)))
        rs_raw = float(ret3.mean() - market_ret) if ret3.notna().any() else 0.0
        breadth = float((ret3 > 0).mean()) if ret3.notna().any() else 0.0
        rev = _num(g.get("revenue_yoy", pd.Series(dtype=float)))
        opy = _num(g.get("op_yoy", pd.Series(dtype=float)))
        earn = float(((rev > 0).mean() + (opy > 0).mean()) / 2) if rev.notna().any() or opy.notna().any() else 0.0
        val = _num(g.get("value_score", pd.Series(dtype=float)))
        valuation = float((val.median() or 0) / 30) if val.notna().any() else 0.0
        liq = min(1.0, n / 20)
        accel = 0.0
        if ret3.notna().any() and ret6.notna().any():
            accel = float(ret3.mean() - (ret6.mean() / 2))
        names = (
            g.sort_values("quant_score", ascending=False)[["ticker", "company", "quant_score", "quant_rank"]]
            .head(3)
            .to_dict("records")
        )
        groups.append(
            {
                "name": str(name),
                "n": n,
                "rs_raw": rs_raw,
                "breadth": breadth,
                "earnings": earn,
                "liquidity": liq,
                "valuation": max(0.0, min(1.5, valuation)),
                "accel_raw": accel,
                "names": [
                    {
                        "ticker": str(r["ticker"]).zfill(6),
                        "company": r["company"],
                        "quant_score": None if pd.isna(r["quant_score"]) else round(float(r["quant_score"]), 1),
                        "quant_rank": None if pd.isna(r["quant_rank"]) else int(r["quant_rank"]),
                    }
                    for r in names
                ],
            }
        )
    if not groups:
        return {"configured": True, "used_in_quant": False, "rows": [], "error": "업종별 종목이 부족합니다."}
    rs_pct = _pct_rank([g["rs_raw"] for g in groups])
    acc_pct = _pct_rank([g["accel_raw"] for g in groups])
    rows: list[dict[str, Any]] = []
    for g, rs, acc in zip(groups, rs_pct, acc_pct, strict=True):
        score = (
            rs * 25
            + g["breadth"] * 20
            + g["earnings"] * 20
            + g["liquidity"] * 15
            + min(1.0, g["valuation"]) * 10
            + acc * 10
        )
        prev_s = prev.get(g["name"])
        delta = None if prev_s is None else round(score - prev_s, 1)
        state = _state(score, delta)
        rows.append(
            {
                "name": g["name"],
                "n": g["n"],
                "score": round(score, 1),
                "previous_score": prev_s,
                "delta": delta,
                "state": state,
                "state_ko": STATE_KO[state],
                "rs": round(rs * 100, 0),
                "breadth": round(g["breadth"] * 100, 0),
                "earnings": round(g["earnings"] * 100, 0),
                "liquidity": round(g["liquidity"] * 100, 0),
                "valuation": round(min(1.0, g["valuation"]) * 100, 0),
                "accel": round(acc * 100, 0),
                "names": g["names"],
                "comment": (
                    f"{g['name']} {g['n']}종목. 시장 대비 3개월 상대강도 {rs*100:.0f}점대, "
                    f"상승 종목 {g['breadth']*100:.0f}%, 실적 증가 비율 {g['earnings']*100:.0f}%. "
                    f"상태 {STATE_KO[state]}. Quant 점수에 넣지 않습니다."
                ),
            }
        )
    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    out = {
        "configured": True,
        "used_in_quant": False,
        "n_sectors": len(rows),
        "market_return_3m": round(market_ret, 4),
        "fetched_at": time.time(),
        "selection": (
            "조건 통과 종목을 업종으로 묶어 상대강도 25·확산 20·실적확산 20·구성규모 15·가치 10·가속 10으로 봅니다. "
            "한 종목 급등과 업종 전체 강세를 가르기 위한 연구 점수이며 Quant에 합산하지 않습니다."
        ),
        "disclaimer": "연구용 업종 점수입니다. 매수 지시가 아니고 재무 Quant를 바꾸지 않습니다.",
        "rows": rows,
    }
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out
