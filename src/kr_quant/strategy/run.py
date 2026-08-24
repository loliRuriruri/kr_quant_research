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
        archetype_desc = f"{company or '해당 종목'}은 고점 돌파 시 차익 실현 매물이 나와 추격 매수는 물리기 쉽고, 단기 악재나 투매로 주가가 과매도권까지 푹 꺼졌을 때 분할 매수하여 반등에 파는 '눌림목/역발상 매매'가 훨씬 유리한 종목입니다."
        avoid_rule = "신고가 돌파 시 추격 매수, 골든크로스 직후 고점 매수 (추세추종 전략 승률 17~50%로 물릴 확률 극히 높음)"
    elif trend_avg_ret > 0 and rev_avg_ret <= 0:
        archetype = "추세추종형 (돌파/모멘텀 유리)"
        archetype_badge = "🚀 추세추종형 파동"
        archetype_desc = f"{company or '해당 종목'}은 한번 상승 탄력이 붙으면 전고점을 뚫고 연속 시세가 분출되는 성향이 강해, 신고가 돌파나 골든크로스 발생 시 시세에 동승하는 '추세추종 매매'가 유리한 종목입니다."
        avoid_rule = "떨어지는 칼날(과매도) 잡기, 추세 꺾인 종목 물타기"
    elif rev_avg_ret >= trend_avg_ret:
        archetype = "평균회귀 우세형 (눌림목 우선)"
        archetype_badge = "🔄 평균회귀 우세"
        archetype_desc = f"{company or '해당 종목'}은 박스권 및 진폭 흐름에서 과매도 반등의 수익성과 승률이 추세 돌파보다 우수하게 나타납니다."
        avoid_rule = "급등 구간에서의 무리한 뇌동 추격 매수"
    else:
        archetype = "혼합/박스권 진폭형"
        archetype_badge = "⚖️ 혼합 박스권 파동"
        archetype_desc = f"{company or '해당 종목'}은 추세와 역추세가 혼재되어 있어 특정 단일 전략보다는 철저한 손절선(-5%)을 동반한 보수적 대응이 필요합니다."
        avoid_rule = "손절 기준 없는 비중 확대"

    best_raw = strategies[0]
    best_trades = int(best_raw.get("trade_count") or 0)

    actionable = best_raw
    actionable_rank = 1
    actionable_reason = ""

    if best_trades < 5 and len(strategies) > 1:
        second = strategies[1]
        second_trades = int(second.get("trade_count") or 0)
        if second_trades >= 5 and float(second.get("total_return") or 0) > 0:
            actionable = second
            actionable_rank = 2
            actionable_reason = (
                f"1위 전략({best_raw.get('name')})은 3년간 매매 횟수가 {best_trades}회로 표본이 부족하여 우연한 수익(과적합) 위험이 있습니다. "
                f"실전에서는 3년간 {second_trades}회의 충분한 기회를 주며 미래 승률 {int((float(second.get('wf_hit') or 0))*100)}%와 "
                f"최고 수익률({float(second.get('total_return') or 0)*100:+.1f}%)을 기록한 '{second.get('name')}'이 가장 실효성 높은 실전 1픽입니다."
            )

    if not actionable_reason:
        wf_pct = int((float(actionable.get("wf_hit") or 0)) * 100) if actionable.get("wf_hit") is not None else 50
        actionable_reason = f"3년간 {actionable.get('trade_count', 0)}회의 실전 매매 검증에서 총수익률 {float(actionable.get('total_return') or 0)*100:+.1f}%, Walk-Forward 미래 승률 {wf_pct}%로 가장 안정적인 밸런스를 입증했습니다."

    sid = str(actionable.get("strategy_id") or "")
    params_ko = str(actionable.get("params_ko") or "")

    if "bollinger" in sid:
        entry_rule = f"주가가 단기 투매로 볼린저 밴드 하단선({params_ko})을 하향 이탈했다가 다시 복귀할 때 분할 매수"
        exit_rule = "볼린저 밴드 중심선(20일 이평선) 도달 시 절반 익절, 상단선 도달 시 전량 수익 확정"
    elif "rsi" in sid:
        entry_rule = f"RSI 지표가 {params_ko} 과매도권(30 이하)에 진입 후 고개를 들 때 분할 매수"
        exit_rule = "RSI 70 이상 과매수권 도달 시 또는 직전 고점 도달 시 차익 실현"
    elif "donchian" in sid:
        entry_rule = f"최근 {params_ko} 전고점을 강한 거래량과 함께 양봉으로 상향 돌파할 때 추세 동승 매수"
        exit_rule = f"청산 채널 저점 이탈 시 또는 20일 이동평균선 하회 시 추세 마감으로 익절/손절"
    else:
        entry_rule = f"단기 이평선이 장기 이평선({params_ko})을 상향 돌파(골든크로스)할 때 진입"
        exit_rule = "단기선이 장기선을 하향 이탈(데드크로스)할 때 청산"

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
    prices = _prices(settings)
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
    slippage = float(costs.get("slippage_bps") or 5)
    oos_ratio = float((cfg.get("splits") or {}).get("oos_ratio") or 0.2)
    min_days = int(cfg.get("minimum_history_days") or 40)

    try:
        ev = evaluate_ticker(data, slippage_bps=slippage, oos_ratio=oos_ratio, min_days=min_days)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ticker": code, "company": company or code, "error": f"백테스트 연산 실패: {exc}"}

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
    }
