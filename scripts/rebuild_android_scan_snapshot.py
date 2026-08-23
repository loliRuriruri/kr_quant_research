# Rebuild Android seasonality_scan_snapshot.json from full KRX live prices.
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\a4jud\kr_quant_research")
PRICES = ROOT / "data" / "staged" / "live" / "prices.parquet"
LISTED = Path(r"C:\TEST\수익-&-계절성-대시보드 (1)\app\src\main\assets\kr_listed_stocks.json")
OUT = Path(r"C:\TEST\수익-&-계절성-대시보드 (1)\app\src\main\assets\seasonality_scan_snapshot.json")

ETF_PREFIXES = (
    "KODEX", "TIGER", "ACE", "PLUS", "SOL", "KIWOOM", "TREX", "KOSEF",
    "HANARO", "TIMEFOLIO", "ARIRANG", "KBSTAR", "KINDEX", "SMART",
)


def is_preferred(name: str) -> bool:
    if "우" not in name:
        return False
    return name.endswith("우") or "우B" in name or "우C" in name or "우(" in name or "전환" in name


def is_etf(name: str) -> bool:
    upper = name.upper()
    return any(upper.startswith(p) or name.startswith(p) for p in ETF_PREFIXES)


def main() -> None:
    listed = {r["t"]: r for r in json.loads(LISTED.read_text(encoding="utf-8"))}
    df = pd.read_parquet(PRICES, columns=["ticker", "company", "market", "trade_date", "close"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    df = df.sort_values(["ticker", "date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    monthly = (
        df.groupby(["ticker", "year", "month"], as_index=False)
        .agg(start_close=("close", "first"), end_close=("close", "last"))
    )
    monthly = monthly[monthly["start_close"] > 0]
    monthly["ret"] = (monthly["end_close"] - monthly["start_close"]) / monthly["start_close"]

    meta = (
        df.drop_duplicates("ticker")[["ticker", "company", "market"]]
        .set_index("ticker")
        .to_dict("index")
    )

    stocks_out = []
    skipped_pref = skipped_etf = skipped_thin = 0
    for ticker, sub in monthly.groupby("ticker"):
        info = meta.get(ticker, {})
        listed_row = listed.get(ticker)
        name = (listed_row["n"] if listed_row else info.get("company") or ticker)
        if is_preferred(str(name)):
            skipped_pref += 1
            continue
        if is_etf(str(name)):
            skipped_etf += 1
            continue
        market = (listed_row["m"] if listed_row else info.get("market") or "KOSPI")
        sector = listed_row["s"] if listed_row else ""
        month_map = {}
        for m, msub in sub.groupby("month"):
            rets = [round(float(v), 4) for v in msub["ret"].tolist()]
            if not rets:
                continue
            wins = sum(1 for v in rets if v > 0)
            month_map[int(m)] = {
                "m": int(m),
                "wr": round(wins / len(rets), 3),
                "ar": round(float(sum(rets) / len(rets)), 4),
                "mr": round(float(pd.Series(rets).median()), 4),
                "n": len(rets),
                "h": rets,
            }
        if len(month_map) < 6:
            skipped_thin += 1
            continue
        months = []
        for m in range(1, 13):
            months.append(month_map.get(m, {"m": m, "wr": 0.0, "ar": 0.0, "mr": 0.0, "n": 0, "h": []}))
        stocks_out.append({"t": ticker, "n": name, "m": market, "s": sector, "months": months})

    payload = {
        "generated_at": "2026-08-23",
        "source": "kr_quant_research.staged.live.prices.parquet",
        "lookback_years": 3,
        "universe_size": len(stocks_out),
        "end_year": 2026,
        "stocks": stocks_out,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        "wrote", OUT,
        "stocks", len(stocks_out),
        "bytes", OUT.stat().st_size,
        "skip_pref", skipped_pref,
        "skip_etf", skipped_etf,
        "skip_thin", skipped_thin,
    )


if __name__ == "__main__":
    main()
