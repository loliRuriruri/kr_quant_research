from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from kr_quant.settings import Settings

WARN_KO = {
    "SECTOR_CONCENTRATION_HIGH": "한 업종 비중이 한도를 넘습니다.",
    "PORTFOLIO_CORRELATION_HIGH": "종목 간 수익률 상관이 높습니다. 분산이 약합니다.",
    "SINGLE_NAME_HIGH": "한 종목 비중이 한도를 넘습니다.",
}


def _prices(settings: Settings) -> pd.DataFrame:
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            return pd.read_parquet(path)
    return pd.DataFrame()


def _bucket_series(holdings: pd.DataFrame) -> pd.Series:
    if "industry" in holdings.columns:
        bucket = holdings["industry"]
        if "sector" in holdings.columns:
            bucket = bucket.fillna(holdings["sector"])
        return bucket.fillna("미분류")
    if "sector" in holdings.columns:
        return holdings["sector"].fillna("미분류")
    return pd.Series(["미분류"] * len(holdings), index=holdings.index)


def analyze_top20(settings: Settings, *, max_sector_weight: float = 0.40, max_name_weight: float = 0.25) -> dict[str, Any]:
    path = settings.output_dir / "latest_top20.csv"
    if not path.exists():
        return {"configured": False, "used_in_quant": False, "error": "TOP20 결과가 없습니다.", "warnings": []}
    holdings = pd.read_csv(path, dtype={"ticker": str})
    holdings["ticker"] = holdings["ticker"].astype(str).str.zfill(6)
    if "company" not in holdings.columns:
        holdings["company"] = holdings["ticker"]
    if "quant_rank" not in holdings.columns:
        holdings["quant_rank"] = range(1, len(holdings) + 1)
    holdings["bucket"] = _bucket_series(holdings)
    n = max(len(holdings), 1)
    holdings["weight"] = 1 / n
    sector_weights = holdings.groupby("bucket")["weight"].sum().sort_values(ascending=False)
    names = holdings.sort_values("weight", ascending=False)[["ticker", "company", "bucket", "weight", "quant_rank"]].head(20)
    warnings: list[str] = []
    top_sector = float(sector_weights.iloc[0]) if not sector_weights.empty else 0.0
    if top_sector > max_sector_weight:
        warnings.append("SECTOR_CONCENTRATION_HIGH")
    if float(holdings["weight"].max()) > max_name_weight and n <= 3:
        warnings.append("SINGLE_NAME_HIGH")

    avg_corr = None
    effective = float(n)
    prices = _prices(settings)
    if not prices.empty and n >= 2:
        tickers = holdings["ticker"].tolist()
        px = prices.copy()
        px["ticker"] = px["ticker"].astype(str).str.zfill(6)
        px["date"] = pd.to_datetime(px["trade_date"], errors="coerce")
        pivot = (
            px[px["ticker"].isin(tickers)]
            .pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
            .sort_index()
        )
        rets = pivot.pct_change(fill_method=None).dropna(how="all").fillna(0.0)
        if rets.shape[1] >= 2 and len(rets) >= 10:
            corr = rets.corr()
            mask = ~np.eye(len(corr), dtype=bool)
            vals = corr.where(mask).stack()
            if not vals.empty:
                avg_corr = float(vals.mean())
                if math.isnan(avg_corr) or math.isinf(avg_corr):
                    avg_corr = None
            if avg_corr is not None and avg_corr > 0.70:
                warnings.append("PORTFOLIO_CORRELATION_HIGH")
            filled = corr.fillna(0.0).to_numpy(dtype=float)
            k = filled.shape[0]
            if k >= 2:
                w = np.full(k, 1 / k)
                port = float(w @ filled @ w)
                if port > 1e-9:
                    effective = float(1 / port)

    comment_bits = [
        f"TOP{n}을 동일 비중으로 본 연구 포트폴리오입니다. 실제 주문·비중 조절이 아닙니다.",
        f"최대 업종 비중 {(top_sector * 100):.0f}% ({sector_weights.index[0] if not sector_weights.empty else '—'}).",
    ]
    if avg_corr is not None:
        comment_bits.append(f"종목 쌍 평균 상관 {avg_corr:.2f}.")
    comment_bits.append(f"유효 종목 수(상관 반영) {effective:.1f} / {n}.")
    if warnings:
        comment_bits.append(" ".join(WARN_KO.get(w, w) for w in warnings))
    else:
        comment_bits.append("업종·상관 한도는 당장 넘지 않습니다.")

    return {
        "configured": True,
        "used_in_quant": False,
        "n": n,
        "max_sector_weight": max_sector_weight,
        "top_sector": None if sector_weights.empty else str(sector_weights.index[0]),
        "sector_concentration": round(top_sector, 4),
        "avg_pairwise_correlation": None if avg_corr is None else round(avg_corr, 3),
        "effective_positions": round(effective, 2),
        "warnings": warnings,
        "warning_labels": [WARN_KO.get(w, w) for w in warnings],
        "sectors": [{"name": str(k), "weight": round(float(v), 4)} for k, v in sector_weights.items()],
        "names": [
            {
                "ticker": str(r.ticker),
                "company": r.company,
                "bucket": r.bucket,
                "weight": round(float(r.weight), 4),
                "quant_rank": r.quant_rank,
            }
            for r in names.itertuples(index=False)
        ],
        "comment": " ".join(comment_bits),
        "disclaimer": "연구용 집중도입니다. Quant 점수를 바꾸지 않고 주문도 없습니다.",
    }
