from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from kr_quant.settings import Settings
from kr_quant.strategy.engine import oos_return, run_backtest
from kr_quant.strategy.registry import FAMILY_KO, SELECTION_KO, format_params_ko, strategy_comment, strategy_registry
from kr_quant.strategy.search import search_strategy, stability_label, walk_forward, walk_forward_score


def cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "strategy_lab.json"


def _cfg(settings: Settings) -> dict[str, Any]:
    path = settings.root / "config" / "strategy_lab.yaml"
    if not path.exists():
        return {"costs": {"slippage_bps": 5}, "splits": {"oos_ratio": 0.2}, "minimum_history_days": 40}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _prices(settings: Settings) -> pd.DataFrame:
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            return pd.read_parquet(path)
    return pd.DataFrame()


def ohlc_for(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    code = str(ticker).zfill(6)
    hist = prices[prices["ticker"].astype(str).str.zfill(6) == code].copy()
    if hist.empty:
        return hist
    hist["date"] = pd.to_datetime(hist["trade_date"], errors="coerce")
    hist = hist.dropna(subset=["date"]).sort_values("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in hist.columns:
            hist[col] = hist["close"] if col != "volume" else 0
        hist[col] = pd.to_numeric(hist[col], errors="coerce")
    hist["open"] = hist["open"].fillna(hist["close"])
    return hist[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def evaluate_ticker(data: pd.DataFrame, *, slippage_bps: float, oos_ratio: float, min_days: int) -> dict[str, Any]:
    if data is None or len(data) < min_days:
        return {"ok": False, "bars": 0 if data is None else int(len(data)), "strategies": [], "warning": "가격 이력 부족"}
    rows: list[dict[str, Any]] = []
    min_trades = 8
    for spec in strategy_registry().values():
        signals = spec.generate_signals(data)
        result = run_backtest(data, signals, commission_bps=0, slippage_bps=slippage_bps)
        metrics = dict(result.metrics)
        metrics["oos_return"] = None if oos_return(result.equity_curve, oos_ratio) is None else round(float(oos_return(result.equity_curve, oos_ratio)), 4)
        searched = search_strategy(data, spec, slippage_bps=slippage_bps, minimum_trades=min_trades)
        n_bars = int(len(data))
        if n_bars >= 500:
            train_d, test_d, step_d = 250, 60, 60
        elif n_bars >= 200:
            train_d, test_d, step_d = 120, 40, 40
        else:
            train_d, test_d, step_d = 40, 15, 15
        windows = (
            walk_forward(data, spec, train_days=train_d, test_days=test_d, step_days=step_d, slippage_bps=slippage_bps)
            if n_bars >= train_d + test_d
            else []
        )
        wf = walk_forward_score(windows)
        label = stability_label(
            sharpe=float(searched.oos.get("sharpe") or metrics.get("sharpe") or 0),
            trades=int(searched.oos.get("trade_count") or metrics.get("trade_count") or 0),
            wf_score=wf,
            min_trades=min_trades,
        )
        rows.append(
            {
                "strategy_id": spec.strategy_id,
                "name": spec.name,
                "family": spec.family,
                "params": searched.parameters or spec.defaults,
                "stability": round(searched.stability, 1),
                "stability_label": label,
                "wf_score": round(wf, 1),
                "wf_windows": len(windows),
                "wf_hit": None if not windows else round(sum(1 for w in windows if float(w.get("oos_return") or 0) > 0) / len(windows), 3),
                "oos_sharpe": searched.oos.get("sharpe"),
                "n_combos": searched.n_combos,
                **metrics,
            }
        )
        rows[-1]["params_ko"] = format_params_ko(rows[-1].get("params") if isinstance(rows[-1].get("params"), dict) else None)
        rows[-1]["family_ko"] = FAMILY_KO.get(str(rows[-1].get("family") or ""), "")
        rows[-1]["comment"] = strategy_comment(rows[-1])
    rows.sort(key=lambda r: (0 if r.get("stability_label") == "LOW" else 1, float(r.get("oos_sharpe") or r.get("sharpe") or 0)), reverse=True)
    shown = [r for r in rows if r.get("stability_label") != "LOW"] or rows
    best = shown[0] if shown else {}
    warn = "표본이 짧아 과적합 위험이 큽니다. 연구용입니다."
    if len(data) < 200:
        pass
    else:
        warn = None
    if best.get("stability_label") == "LOW":
        warn = (warn or "") + " 안정성 LOW는 순위로 쓰지 마세요."
    return {
        "ok": True,
        "bars": int(len(data)),
        "from": str(data["date"].iloc[0].date()) if len(data) else None,
        "to": str(data["date"].iloc[-1].date()) if len(data) else None,
        "best_id": best.get("strategy_id"),
        "best_name": best.get("name"),
        "best_params_ko": best.get("params_ko"),
        "best_comment": best.get("comment"),
        "best_family_ko": best.get("family_ko"),
        "stability_label": best.get("stability_label"),
        "warning": warn.strip() if warn else None,
        "strategies": rows,
        "used_in_quant": False,
    }


def annotate_strategy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for rec in payload.get("rows") or []:
        if not isinstance(rec, dict):
            continue
        for item in rec.get("strategies") or []:
            if not isinstance(item, dict):
                continue
            if not item.get("params_ko"):
                item["params_ko"] = format_params_ko(item.get("params") if isinstance(item.get("params"), dict) else None)
            if not item.get("family_ko"):
                item["family_ko"] = FAMILY_KO.get(str(item.get("family") or ""), "")
            if not item.get("comment"):
                item["comment"] = strategy_comment(item)
        best = (rec.get("strategies") or [{}])[0]
        rec["best_params_ko"] = rec.get("best_params_ko") or (best.get("params_ko") if isinstance(best, dict) else None)
        rec["best_comment"] = rec.get("best_comment") or (best.get("comment") if isinstance(best, dict) else None)
        rec["best_family_ko"] = rec.get("best_family_ko") or (best.get("family_ko") if isinstance(best, dict) else None)
    payload["selection"] = payload.get("selection") or SELECTION_KO
    return payload


def load_strategy(settings: Settings) -> dict[str, Any]:
    path = cache_path(settings.root)
    if path.exists():
        try:
            return annotate_strategy_payload(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return {
        "need_run": True,
        "used_in_quant": False,
        "rows": [],
        "catalog": list(strategy_registry().keys()),
        "selection": SELECTION_KO,
    }


def scan_strategies(settings: Settings, *, tickers: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    cfg = _cfg(settings)
    costs = cfg.get("costs") or {}
    slippage = float(costs.get("slippage_bps") or 5)
    oos_ratio = float((cfg.get("splits") or {}).get("oos_ratio") or 0.2)
    min_days = int(cfg.get("minimum_history_days") or 40)
    prices = _prices(settings)
    names: list[tuple[str, str]] = list(tickers or [])
    if not names:
        csv = settings.output_dir / "latest_top20.csv"
        if csv.exists():
            df = pd.read_csv(csv, dtype={"ticker": str})
            names = [(str(r.get("ticker") or "").zfill(6), str(r.get("company") or "")) for r in df.to_dict("records")]
    rows: list[dict[str, Any]] = []
    for code, company in names[:20]:
        data = ohlc_for(prices, code)
        ev = evaluate_ticker(data, slippage_bps=slippage, oos_ratio=oos_ratio, min_days=min_days)
        rows.append({"ticker": code, "company": company or code, **ev})
    out = {
        "configured": True,
        "used_in_quant": False,
        "need_run": False,
        "fetched_at": time.time(),
        "slippage_bps": slippage,
        "execution": "next-bar open",
        "selection": SELECTION_KO,
        "disclaimer": "일봉 백테스트. 파라미터는 학습 구간에서만 고르고, 이후 구간·walk-forward로 봅니다. 실시간 호가·주문이 아닙니다.",
        "catalog": [
            {"id": s.strategy_id, "name": s.name, "family": s.family, "params": s.defaults}
            for s in strategy_registry().values()
        ],
        "rows": rows,
    }
    path = cache_path(settings.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out
