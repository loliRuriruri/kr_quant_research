from __future__ import annotations

from types import SimpleNamespace

from kr_quant.strategy import seasonality


def _row(ticker: str, stage: str, score: float, remaining: float) -> dict:
    return {
        "ticker": ticker,
        "pattern_id": f"{ticker}_M09_L5",
        "entry_stage": stage,
        "seasonality_score": score,
        "remaining_peak": {"available": True, "remaining_p50": remaining},
    }


def test_pre_entry_rank_is_canonical_and_deterministic(monkeypatch):
    rows = [
        _row("000001", "PRE_ENTRY_30", 99.0, 0.20),
        _row("000002", "TODAY_ENTRY", 70.0, 0.05),
        _row("000003", "TODAY_ENTRY", 80.0, 0.03),
        _row("000004", "ACCUMULATE_60", 100.0, 0.40),
    ]
    monkeypatch.setattr(seasonality, "_clean_active_tickers", lambda settings: {row["ticker"] for row in rows})
    monkeypatch.setattr(
        seasonality,
        "_latest_quotes",
        lambda settings, tickers: {
            ticker: {"last_close": 10_000.0, "chg_pct": 0.0, "as_of": "2026-08-26"}
            for ticker in tickers
        },
    )

    ranked = seasonality.rank_pre_entry_candidates(SimpleNamespace(), rows)

    assert [row["ticker"] for row in ranked] == ["000003", "000002", "000001", "000004"]
    assert [row["pre_entry_rank"] for row in ranked] == [1, 2, 3, 4]
    assert all(row["price_as_of"] == "2026-08-26" for row in ranked)
