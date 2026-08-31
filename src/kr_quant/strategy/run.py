from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml

from kr_quant.settings import Settings
from kr_quant.quality.price_integrity import latest_clean_price_segments
from kr_quant.strategy.engine import ExecutionModel, execution_model_from_mapping, run_backtest
from kr_quant.strategy.registry import FAMILY_KO, SELECTION_KO, format_params_ko, strategy_comment, strategy_registry
from kr_quant.strategy.search import search_strategy, stability_label, walk_forward, walk_forward_score
from kr_quant.universe.point_in_time import pit_portfolio_study, strategy_universe_evidence


def cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "strategy_lab.json"


def _cfg(settings: Settings) -> dict[str, Any]:
    path = settings.root / "config" / "strategy_lab.yaml"
    if not path.exists():
        return {
            "costs": {
                "commission_bps": 1.5,
                "slippage_bps": 5,
                "sell_tax_bps": 20,
                "sell_tax_schedule_bps": [{"effective_from": "2026-01-01", "bps": 20}],
            },
            "execution": {
                "position_notional_krw": 10_000_000,
                "max_participation_rate": 0.10,
                "impact_bps_at_max_participation": 20,
                "price_limit_pct": 0.30,
                "lock_tolerance_pct": 0.005,
                "max_pending_days": 3,
                "block_zero_volume": True,
            },
            "splits": {"oos_ratio": 0.2},
            "minimum_history_days": 40,
        }
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _execution_model(cfg: dict[str, Any]) -> ExecutionModel:
    costs = dict(cfg.get("costs") or {})
    raw = {**dict(cfg.get("execution") or {}), **costs}
    return execution_model_from_mapping(
        raw,
        commission_bps=float(costs.get("commission_bps") or 0),
        slippage_bps=float(costs.get("slippage_bps") or 5),
    )


def _prices(settings: Settings) -> pd.DataFrame:
    from kr_quant.quality.corporate_actions import apply_official_adjustments, load_actions_from_settings

    frame = pd.DataFrame()
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            break
    if frame.empty:
        return frame
    return apply_official_adjustments(frame, load_actions_from_settings(settings))


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
    keep = ["date", "open", "high", "low", "close", "volume"]
    keep.extend(
        column
        for column in ("listed_shares", "market_cap", "adj_close", "adj_factor", "price_return", "total_return")
        if column in hist.columns
    )
    return hist[keep].reset_index(drop=True)


def evaluate_ticker(
    data: pd.DataFrame,
    *,
    commission_bps: float = 0,
    slippage_bps: float,
    oos_ratio: float,
    min_days: int,
    price_integrity_config: dict[str, Any] | None = None,
    execution_model: ExecutionModel | dict[str, Any] | None = None,
    actions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    raw_bars = 0 if data is None else int(len(data))
    from kr_quant.quality.corporate_actions import series_contract
    from kr_quant.quality.price_integrity import attach_official_action_explanations

    official = bool(
        data is not None
        and "adj_factor" in getattr(data, "columns", [])
        and pd.to_numeric(data["adj_factor"], errors="coerce").fillna(1).ne(1).any()
    )
    clean_data, price_issues, price_quality = latest_clean_price_segments(data, price_integrity_config)
    data = clean_data
    price_issues, price_quality = attach_official_action_explanations(price_issues, price_quality, actions)
    price_quality.update(series_contract(official=official))
    price_quality["execution_price_basis"] = "raw_ohlc_next_open"
    price_quality["issues"] = price_issues.to_dict("records")
    if data is None or len(data) < min_days:
        warning = "가격 이력 부족"
        if price_quality.get("issue_count"):
            warning += " · 가격 단절 이전 구간 제외 후 최근 안전구간이 부족합니다."
        return {
            "ok": False,
            "bars": 0 if data is None else int(len(data)),
            "raw_bars": raw_bars,
            "strategies": [],
            "warning": warning,
            "price_integrity": price_quality,
        }
    rows: list[dict[str, Any]] = []
    min_trades = 8
    for spec in strategy_registry().values():
        searched = search_strategy(
            data,
            spec,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            minimum_trades=min_trades,
            execution_model=execution_model,
        )
        # Descriptive full-history metrics and displayed parameters must describe
        # the same selected strategy. Final OOS metrics remain separate below.
        signals = spec.generate_signals(data, searched.parameters)
        result = run_backtest(
            data,
            signals,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_model=execution_model,
        )
        metrics = dict(result.metrics)
        n_bars = int(len(data))
        if n_bars >= 500:
            train_d, test_d, step_d = 250, 60, 60
        elif n_bars >= 200:
            train_d, test_d, step_d = 120, 40, 40
        else:
            train_d, test_d, step_d = 40, 15, 15
        windows = (
            walk_forward(
                data,
                spec,
                train_days=train_d,
                test_days=test_d,
                step_days=step_d,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
                execution_model=execution_model,
            )
            if n_bars >= train_d + test_d
            else []
        )
        wf = walk_forward_score(windows)
        final_oos_sharpe = float(searched.oos.get("sharpe") or 0) if searched.oos else 0.0
        final_oos_trades = int(searched.oos.get("trade_count", 0)) if searched.oos else 0
        label = stability_label(
            sharpe=final_oos_sharpe,
            trades=final_oos_trades,
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
                "train_score": round(searched.train_score, 4),
                "selection_score": round(searched.selection_score, 4),
                "validation_return": searched.validation.get("total_return"),
                "validation_sharpe": searched.validation.get("sharpe"),
                "validation_trade_count": searched.validation.get("trade_count"),
                "oos_return": searched.oos.get("total_return"),
                "oos_sharpe": searched.oos.get("sharpe"),
                "oos_trade_count": searched.oos.get("trade_count"),
                "selection_basis": "validation",
                "n_combos": searched.n_combos,
                **metrics,
            }
        )
        rows[-1]["params_ko"] = format_params_ko(rows[-1].get("params") if isinstance(rows[-1].get("params"), dict) else None)
        rows[-1]["family_ko"] = FAMILY_KO.get(str(rows[-1].get("family") or ""), "")
        rows[-1]["comment"] = strategy_comment(rows[-1])
    # The final OOS and walk-forward results are evidence, not selectors.
    # Rank strategy families only by the already-designated validation score.
    rows.sort(key=lambda r: float(r.get("selection_score") or 0), reverse=True)
    best = rows[0] if rows else {}
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
        "raw_bars": raw_bars,
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
        "price_integrity": price_quality,
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
            payload = annotate_strategy_payload(json.loads(path.read_text(encoding="utf-8")))
            from kr_quant.freshness import latest_price_date, trading_session_lag

            price_day = latest_price_date(settings)
            cache_day = payload.get("source_price_as_of")
            if not cache_day:
                row_dates = [row.get("to") for row in payload.get("rows") or [] if isinstance(row, dict) and row.get("to")]
                cache_day = max(row_dates) if row_dates else None
            cache_date = None
            if cache_day:
                try:
                    cache_date = pd.Timestamp(cache_day).date()
                except (TypeError, ValueError):
                    cache_date = None
            lag = trading_session_lag(cache_date, price_day) if price_day else None
            payload["source_price_as_of"] = cache_day
            payload["current_price_as_of"] = None if price_day is None else price_day.isoformat()
            payload["lag_trading_days"] = lag
            payload["stale"] = bool(lag)
            if lag:
                payload["need_run"] = True
                payload["freshness_warning"] = f"전략 결과가 최신 시세보다 {lag}거래일 뒤처졌습니다. 전략 재검증이 필요합니다."
            payload.setdefault(
                "universe_evidence",
                strategy_universe_evidence(
                    settings.output_dir,
                    rows=payload.get("rows") or [],
                    selection_as_of=payload.get("source_price_as_of"),
                ),
            )
            return payload
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
    commission = float(costs.get("commission_bps") or 0)
    slippage = float(costs.get("slippage_bps") or 5)
    execution_model = _execution_model(cfg)
    oos_ratio = float((cfg.get("splits") or {}).get("oos_ratio") or 0.2)
    min_days = int(cfg.get("minimum_history_days") or 40)
    prices = _prices(settings)
    from kr_quant.quality.corporate_actions import load_actions_from_settings

    actions = load_actions_from_settings(settings)
    names: list[tuple[str, str]] = list(tickers or [])
    if not names:
        csv = settings.output_dir / "latest_top20.csv"
        if csv.exists():
            df = pd.read_csv(csv, dtype={"ticker": str})
            names = [(str(r.get("ticker") or "").zfill(6), str(r.get("company") or "")) for r in df.to_dict("records")]
    rows: list[dict[str, Any]] = []
    for code, company in names[:20]:
        data = ohlc_for(prices, code)
        ev = evaluate_ticker(
            data,
            commission_bps=commission,
            slippage_bps=slippage,
            oos_ratio=oos_ratio,
            min_days=min_days,
            price_integrity_config=settings.config.get("corporate_actions") or {},
            execution_model=execution_model,
            actions=actions,
        )
        rows.append({"ticker": code, "company": company or code, **ev})
    source_price_as_of = None
    if not prices.empty and "trade_date" in prices.columns:
        dates = pd.to_datetime(prices["trade_date"], errors="coerce").dropna()
        if not dates.empty:
            source_price_as_of = dates.max().date().isoformat()
    universe_evidence = strategy_universe_evidence(
        settings.output_dir,
        rows=rows,
        selection_as_of=source_price_as_of,
    )
    out = {
        "configured": True,
        "used_in_quant": False,
        "need_run": False,
        "fetched_at": time.time(),
        "source_price_as_of": source_price_as_of,
        "current_price_as_of": source_price_as_of,
        "lag_trading_days": 0,
        "stale": False,
        "commission_bps": commission,
        "slippage_bps": slippage,
        "execution": "signal close -> next tradable open",
        "execution_model": execution_model.public(),
        "execution_note": "수수료·매도세·기본 슬리피지·거래대금 참여율 충격과 무거래/상하한가 잠김을 일봉 프록시로 반영합니다.",
        "universe_evidence": universe_evidence,
        "pit_portfolio": pit_portfolio_study(settings.output_dir),
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
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return out



def generate_plain_strategy_playbook(strategies: list[dict[str, Any]], company: str = "") -> dict[str, Any]:
    if not strategies:
        return {}

    reversion_strats = [s for s in strategies if s.get("family") == "MEAN_REVERSION" or "reversion" in str(s.get("strategy_id", ""))]
    trend_strats = [s for s in strategies if s.get("family") == "TREND" or "cross" in str(s.get("strategy_id", "")) or "donchian" in str(s.get("strategy_id", ""))]

    rev_avg_ret = sum(float(s.get("total_return") or 0) for s in reversion_strats) / len(reversion_strats) if reversion_strats else 0
    trend_avg_ret = sum(float(s.get("total_return") or 0) for s in trend_strats) / len(trend_strats) if trend_strats else 0

    if rev_avg_ret > 0 and trend_avg_ret <= 0:
        archetype = "평균회귀형 (눌림목/과매도 반등 유리)"
        archetype_badge = "🔄 평균회귀형 파동"
        archetype_desc = f"{company or '해당 종목'}의 과거 표본에서는 추세 돌파보다 과매도 뒤 평균 복귀 규칙의 전체기간 성과가 상대적으로 높았습니다. 시장 구조가 바뀌면 재현되지 않을 수 있습니다."
        avoid_rule = "평균회귀가 작동하지 않는 하락 추세에서는 손실이 누적될 수 있으므로 최종검증 거래 수와 최대낙폭을 함께 확인해야 합니다."
    elif trend_avg_ret > 0 and rev_avg_ret <= 0:
        archetype = "추세추종형 (돌파/모멘텀 유리)"
        archetype_badge = "🚀 추세추종형 파동"
        archetype_desc = f"{company or '해당 종목'}의 과거 표본에서는 평균회귀보다 추세 돌파 규칙의 전체기간 성과가 상대적으로 높았습니다. 횡보장에서는 가짜 신호가 늘 수 있습니다."
        avoid_rule = "횡보 구간의 반복 돌파 실패와 최종검증 표본 부족은 전체기간 수익률을 그대로 신뢰하면 안 되는 주요 조건입니다."
    elif rev_avg_ret >= trend_avg_ret:
        archetype = "평균회귀 우세형 (눌림목 우선)"
        archetype_badge = "🔄 평균회귀 우세"
        archetype_desc = f"{company or '해당 종목'}의 과거 표본에서는 평균회귀 규칙이 추세 규칙보다 상대적으로 나았지만 차이가 미래에도 유지된다는 뜻은 아닙니다."
        avoid_rule = "검증·최종검증 수익 방향이 다르거나 거래 수가 적으면 유형 판정을 보류해야 합니다."
    else:
        archetype = "혼합/박스권 진폭형"
        archetype_badge = "⚖️ 혼합 박스권 파동"
        archetype_desc = f"{company or '해당 종목'}은 추세와 평균회귀 결과가 혼재해 한 가지 가격 규칙으로 설명하기 어렵습니다."
        avoid_rule = "단일 백테스트 결과를 확정적 가격 행동으로 해석하지 말고 추가 표본을 확인해야 합니다."

    best_raw = strategies[0]
    best_trades = int(best_raw.get("trade_count") or 0)

    actionable = best_raw
    actionable_rank = 1
    val_ret = actionable.get("validation_return")
    oos_ret = actionable.get("oos_return")
    val_trades = int(actionable.get("validation_trade_count") or 0)
    oos_trades = int(actionable.get("oos_trade_count") or 0)
    wf_windows = int(actionable.get("wf_windows") or 0)
    wf_pct = int(float(actionable.get("wf_hit") or 0) * 100) if wf_windows else 0
    actionable_reason = (
        f"가운데 검증 구간 점수로 선택됐습니다. 검증 수익률 "
        f"{float(val_ret or 0) * 100:+.1f}%({val_trades}회), 선택에 쓰지 않은 최종검증 수익률 "
        f"{float(oos_ret or 0) * 100:+.1f}%({oos_trades}회), Walk-Forward 양(+)의 구간 비율 "
        f"{wf_pct}%({wf_windows}개 구간)입니다."
    )
    if str(actionable.get("stability_label") or "") == "LOW" or min(best_trades, oos_trades) < 5:
        actionable_reason += " 표본 부족 또는 구간 불일치로 안정성 LOW이므로 결론을 보류해야 합니다."

    sid = str(actionable.get("strategy_id") or "")
    params_ko = str(actionable.get("params_ko") or "")

    if "bollinger" in sid:
        entry_rule = f"검증한 진입 조건: 종가가 볼린저 하단선({params_ko}) 아래로 내려간 날의 다음 거래일 시가"
        exit_rule = "검증한 청산 조건: 종가가 볼린저 중심선 위로 복귀한 날의 다음 거래일 시가"
    elif "rsi" in sid:
        entry_rule = f"검증한 진입 조건: RSI가 설정 과매도선({params_ko}) 아래인 날의 다음 거래일 시가"
        exit_rule = "검증한 청산 조건: RSI가 설정 과매수선 위인 날의 다음 거래일 시가"
    elif "donchian" in sid:
        entry_rule = f"검증한 진입 조건: 종가가 과거 돈치안 상단({params_ko})을 돌파한 날의 다음 거래일 시가"
        exit_rule = "검증한 청산 조건: 종가가 설정 돈치안 하단을 이탈한 날의 다음 거래일 시가"
    else:
        entry_rule = f"검증한 진입 조건: 단기 이평선이 장기 이평선({params_ko})을 상향 돌파한 날의 다음 거래일 시가"
        exit_rule = "검증한 청산 조건: 단기 이평선이 장기 이평선을 하향 이탈한 날의 다음 거래일 시가"

    return {
        "archetype": archetype,
        "archetype_badge": archetype_badge,
        "archetype_desc": archetype_desc,
        "actionable_name": actionable.get("name") or "",
        "actionable_rank": actionable_rank,
        "actionable_params_ko": params_ko,
        "actionable_reason": actionable_reason,
        "entry_rule": entry_rule,
        "exit_rule": exit_rule,
        "avoid_rule": avoid_rule,
    }

def backtest_single_stock(settings: Settings, query: str) -> dict[str, Any]:
    from kr_quant.quality.corporate_actions import load_actions_from_settings

    prices = _prices(settings)
    actions = load_actions_from_settings(settings)
    if prices.empty:
        return {"ok": False, "error": "주가 데이터(prices.parquet)가 없습니다."}

    q = str(query or "").strip()
    code = ""
    company = ""

    tickers = prices["ticker"].astype(str).str.zfill(6) if not prices.empty and "ticker" in prices.columns else pd.Series(dtype=str)

    if q.isdigit() or (len(q) <= 6 and q.replace(".", "").isdigit()):
        code = "".join(ch for ch in q if ch.isdigit()).zfill(6)
        matched = prices[tickers == code] if not prices.empty else pd.DataFrame()
        if not matched.empty and "company" in matched.columns:
            company = str(matched["company"].iloc[0])
    elif "company" in prices.columns:
        matched = prices[prices["company"].astype(str).str.contains(q, case=False, na=False, regex=False)]
        if not matched.empty:
            code = str(matched["ticker"].iloc[0]).zfill(6)
            company = str(matched["company"].iloc[0])

    if not code:
        for stem in ("latest_all_stocks", "latest_top100", "latest_top20"):
            csv = settings.output_dir / f"{stem}.csv"
            pq = settings.output_dir / f"{stem}.parquet"
            df = None
            if csv.exists():
                df = pd.read_csv(csv, dtype={"ticker": str})
            elif pq.exists():
                df = pd.read_parquet(pq)
            if df is None or df.empty:
                continue
            for r in df.to_dict("records"):
                t = str(r.get("ticker") or "").zfill(6)
                c = str(r.get("company") or "")
                if q.zfill(6) == t or q in c or c in q:
                    code = t
                    company = c
                    break
            if code:
                break

    if not code:
        return {"ok": False, "error": f"종목 '{query}'을(를) 찾을 수 없습니다. 6자리 종목코드나 정확한 종목명을 입력하세요. (퀀트 TOP20이 아니어도 시세가 있으면 실행됩니다.)"}

    data = ohlc_for(prices, code)
    if data.empty or len(data) < 20:
        return {"ok": False, "ticker": code, "company": company, "error": f"종목 '{code}'의 가격 이력이 부족합니다 ({len(data)}일). 퀀트 선별 여부와 무관하게 일봉이 있어야 합니다."}

    cfg = _cfg(settings)
    costs = cfg.get("costs") or {}
    commission = float(costs.get("commission_bps") or 0)
    slippage = float(costs.get("slippage_bps") or 5)
    execution_model = _execution_model(cfg)
    oos_ratio = float((cfg.get("splits") or {}).get("oos_ratio") or 0.2)
    min_days = int(cfg.get("minimum_history_days") or 40)

    try:
        ev = evaluate_ticker(
            data,
            commission_bps=commission,
            slippage_bps=slippage,
            oos_ratio=oos_ratio,
            min_days=min_days,
            price_integrity_config=settings.config.get("corporate_actions") or {},
            execution_model=execution_model,
            actions=actions,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ticker": code, "company": company or code, "error": f"백테스트 연산 실패: {exc}"}
    if not ev.get("ok"):
        return {
            "ok": False,
            "ticker": code,
            "company": company or code,
            "error": ev.get("warning") or "가격 품질 검증 후 사용할 수 있는 이력이 부족합니다.",
            "bars": ev.get("bars"),
            "raw_bars": ev.get("raw_bars"),
            "price_integrity": ev.get("price_integrity") or {},
        }

    for st in ev.get("strategies") or []:
        st["params_ko"] = format_params_ko(st.get("params") if isinstance(st.get("params"), dict) else None)
        st["family_ko"] = FAMILY_KO.get(str(st.get("family") or ""), "")
        st["comment"] = strategy_comment(st)

    best = (ev.get("strategies") or [{}])[0]

    return {
        "ok": True,
        "ticker": code,
        "company": company or code,
        "bars": ev.get("bars"),
        "raw_bars": ev.get("raw_bars"),
        "from": ev.get("from"),
        "to": ev.get("to"),
        "best_id": ev.get("best_id"),
        "best_name": ev.get("best_name"),
        "best_params_ko": best.get("params_ko"),
        "best_comment": best.get("comment"),
        "best_family_ko": best.get("family_ko"),
        "stability_label": ev.get("stability_label"),
        "warning": ev.get("warning"),
        "strategies": ev.get("strategies") or [],
        "playbook": generate_plain_strategy_playbook(ev.get("strategies") or [], company or code),
        "price_integrity": ev.get("price_integrity") or {},
        "execution_model": execution_model.public(),
        "execution_note": "수수료·매도세·기본 슬리피지·거래대금 참여율 충격과 무거래/상하한가 잠김을 일봉 프록시로 반영합니다.",
        "universe_evidence": {
            "selection_mode": "USER_SELECTED_CURRENT_SECURITY",
            "selection_as_of": ev.get("to"),
            "backtest_history_from": ev.get("from"),
            "survivorship_bias_controlled": False,
            "research_grade": "SINGLE_SECURITY_PATH_ONLY",
            "limitation": "사용자가 현재 조회 가능한 단일 종목을 선택한 가격경로 검증입니다. 당시 전체 상장종목을 재구성한 횡단면 전략 검증은 아닙니다.",
        },
    }
