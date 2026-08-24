# -*- coding: utf-8 -*-
"""Export a secret-free, read-only JSON snapshot for Cloudflare Pages.

Reads already-computed local outputs. Does not call live APIs, does not
write zeros for missing values, and never aliases FUND to 연기금/국민연금.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.context.watchlist import load_watchlist
from kr_quant.factors.scorecard import build_factor_scorecard
from kr_quant.freshness import freshness_snapshot
from kr_quant.settings import load_settings
from kr_quant.web.guide import EXCLUSION_KO, WARNING_FIX, WARNING_KO, explain_run_status

SECRET_KEY_RE = re.compile(r"(api[_-]?key|secret|token|password|authorization|bearer|cookie)", re.I)
NAN = {None}

FORMULAS: dict[str, dict[str, str]] = {
    "quant_score": {
        "formula": "Value(30) + Quality(25) + Growth(25) + Momentum(10) + Stability(10) − risk_penalty",
        "kind": "model",
        "source": "KR Quant v1 (로컬 계산)",
    },
    "per": {
        "formula": "시가총액(KRX) / 지배주주순이익 TTM(OpenDART)",
        "kind": "observed",
        "source": "KRX 시총 + OpenDART TTM",
    },
    "pbr": {
        "formula": "시가총액(KRX) / 지배주주지분(OpenDART)",
        "kind": "observed",
        "source": "KRX 시총 + OpenDART",
    },
    "ev_ebit": {
        "formula": "EV / 영업이익 TTM. EV = 시총 + 우선주 + 순이자부채 + NCI − 현금 − 단기금융자산",
        "kind": "observed",
        "source": "KRX + OpenDART",
    },
    "fcf_yield": {
        "formula": "(영업현금흐름 TTM − 자본적지출 TTM) / 시가총액",
        "kind": "observed",
        "source": "OpenDART TTM + KRX 시총",
    },
    "earnings_yield": {
        "formula": "지배주주순이익 TTM / 시가총액",
        "kind": "observed",
        "source": "OpenDART TTM + KRX 시총",
    },
    "roe": {
        "formula": "지배주주순이익 TTM / 평균 지배주주지분",
        "kind": "observed",
        "source": "OpenDART TTM",
    },
    "roic": {
        "formula": "NOPAT / 투하자본 (현금분류 단순화 시 ROIC_CASH_CLASSIFICATION_SIMPLE 경고)",
        "kind": "observed",
        "source": "OpenDART TTM",
    },
    "operating_margin": {
        "formula": "영업이익 TTM / 매출 TTM",
        "kind": "observed",
        "source": "OpenDART TTM",
    },
    "return_12m": {
        "formula": "최근 종가 / 약 252거래일 전 종가 − 1 (상장주식수·시총으로 분할만 보정)",
        "kind": "observed",
        "source": "KRX 일봉",
    },
}


def _is_num(x: Any) -> bool:
    try:
        return x is not None and x == x and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _num(x: Any) -> float | None:
    if not _is_num(x):
        return None
    return float(x)


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items() if not SECRET_KEY_RE.search(str(k))}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "item") and not isinstance(obj, (bytes, str, dict, list)):
        try:
            return _clean(obj.item())
        except Exception:
            return str(obj)
    if pd.isna(obj) if not isinstance(obj, (list, dict, str, bytes)) else False:
        return None
    return obj


def fact(
    value: Any,
    *,
    as_of: str | None,
    source: str,
    kind: str,
    formula: str,
    unit: str = "",
    warning: str | None = None,
    freshness: str | None = None,
) -> dict[str, Any]:
    missing = not _is_num(value) and not (isinstance(value, str) and value)
    if missing and not isinstance(value, (int, float)):
        missing = value in (None, "", [])
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        missing = True
        value = None
    out = {
        "value": None if missing else value,
        "display": "미수집" if missing else value,
        "as_of": as_of,
        "source": source,
        "kind": kind,
        "formula": formula,
        "unit": unit,
        "missing": bool(missing),
        "freshness": freshness,
        "warning": warning if warning else ("값이 없어 0으로 채우지 않았습니다." if missing else None),
        "limit": "투자 권유가 아니며 과거 스냅샷입니다. 주문 기능이 없습니다.",
    }
    return out


def _flags(val: Any) -> list[str]:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return []
    if hasattr(val, "tolist") and not isinstance(val, (list, str, dict)):
        try:
            val = val.tolist()
        except Exception:
            val = list(val)
    if isinstance(val, list):
        return [str(x) for x in val if x and str(x) not in {"[]", "None", "nan"}]
    text = str(val)
    if "|" in text:
        return [p for p in text.split("|") if p]
    if "," in text and " " not in text[:3]:
        return [p for p in text.split(",") if p]
    return [text] if text and text not in {"[]", "None"} else []


def load_all_stocks(settings) -> pd.DataFrame:
    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def sparkline(prices: pd.DataFrame, ticker: str, n: int = 60) -> list[float]:
    if prices.empty or "ticker" not in prices.columns:
        return []
    code = str(ticker).zfill(6)
    hist = prices[prices["ticker"].astype(str).str.zfill(6) == code]
    if hist.empty or "close" not in hist.columns:
        return []
    hist = hist.copy()
    hist["trade_date"] = pd.to_datetime(hist["trade_date"], errors="coerce")
    hist = hist.dropna(subset=["trade_date"]).sort_values("trade_date")
    closes = pd.to_numeric(hist["close"], errors="coerce").dropna().tolist()
    return [round(float(x), 4) for x in closes[-n:]]


def compact_row(r: pd.Series, as_of: str) -> dict[str, Any]:
    rank = _num(r.get("quant_rank"))
    return {
        "ticker": str(r.get("ticker") or "").zfill(6),
        "company": r.get("company") or "",
        "market": r.get("market") or "",
        "sector": r.get("sector") or "",
        "industry": r.get("industry") or "",
        "quant_rank": None if rank is None else int(rank),
        "quant_score": _num(r.get("quant_score")),
        "value_score": _num(r.get("value_score")),
        "quality_score": _num(r.get("quality_score")),
        "growth_score": _num(r.get("growth_score")),
        "momentum_score": _num(r.get("momentum_score")),
        "financial_score": _num(r.get("financial_score")),
        "data_confidence": _num(r.get("data_confidence")),
        "universe_eligible": bool(r.get("universe_eligible")),
        "top20_eligible": bool(r.get("top20_eligible")),
        "top100_eligible": bool(r.get("top100_eligible")),
        "as_of": as_of,
    }


def stock_detail(r: pd.Series, as_of: str, prices: pd.DataFrame) -> dict[str, Any]:
    ticker = str(r.get("ticker") or "").zfill(6)
    flags = _flags(r.get("data_flags")) + _flags(r.get("risk_flags"))
    conf = r.get("confidence_components")
    if not isinstance(conf, dict):
        conf = {}
    metrics = r.get("metric_values")
    if not isinstance(metrics, dict):
        metrics = {}
    scorecard = build_factor_scorecard(r.to_dict())
    metric_facts = {}
    for key, spec in FORMULAS.items():
        raw = r.get(key) if key in r.index and pd.notna(r.get(key)) else metrics.get(key)
        warn = None
        if key == "roic" and "ROIC_CASH_CLASSIFICATION_SIMPLE" in flags:
            warn = "현금분류를 단순화한 ROIC입니다. 공식 투하자본과 다를 수 있습니다."
        if key == "return_12m" and "SHARE_ADJ_MOMENTUM" in flags:
            warn = "분할만 보정한 수익률입니다. 배당 총수익이 아닙니다."
        metric_facts[key] = fact(
            _num(raw),
            as_of=as_of,
            source=spec["source"],
            kind=spec["kind"],
            formula=spec["formula"],
            warning=warn,
            freshness=as_of,
        )
    exclusions = _flags(r.get("exclusion_reasons"))
    return {
        "ticker": ticker,
        "company": r.get("company") or ticker,
        "market": r.get("market") or "",
        "sector": r.get("sector") or "",
        "industry": r.get("industry") or "",
        "corp_code": r.get("corp_code") or "",
        "as_of": as_of,
        "cutoff_ts": str(r.get("cutoff_ts") or ""),
        "universe_eligible": bool(r.get("universe_eligible")),
        "exclusions": [{"code": c, "label": EXCLUSION_KO.get(c, c)} for c in exclusions],
        "scores": {
            "quant": metric_facts["quant_score"],
            "value": fact(_num(r.get("value_score")), as_of=as_of, source="KR Quant v1", kind="model", formula="가치 팩터 최대 30점", freshness=as_of),
            "quality": fact(_num(r.get("quality_score")), as_of=as_of, source="KR Quant v1", kind="model", formula="품질 팩터 최대 25점", freshness=as_of),
            "growth": fact(_num(r.get("growth_score")), as_of=as_of, source="KR Quant v1", kind="model", formula="성장 팩터 최대 25점", freshness=as_of),
            "momentum": fact(_num(r.get("momentum_score")), as_of=as_of, source="KR Quant v1 / KRX", kind="model", formula="모멘텀 최대 10점 (분할 보정)", freshness=as_of),
            "stability": fact(_num(r.get("financial_score")), as_of=as_of, source="KR Quant v1", kind="model", formula="안정 팩터 최대 10점", freshness=as_of),
            "risk_penalty": fact(_num(r.get("risk_penalty")), as_of=as_of, source="KR Quant v1", kind="model", formula="리스크 감점", freshness=as_of),
            "rank": fact(_num(r.get("quant_rank")), as_of=as_of, source="KR Quant v1", kind="model", formula="동일 스냅샷 내 점수 순위", freshness=as_of),
            "rank_change": fact(_num(r.get("rank_change")), as_of=as_of, source="KR Quant v1", kind="model", formula="전일 순위 − 당일 순위", freshness=as_of),
        },
        "valuation": {k: metric_facts[k] for k in ("per", "pbr", "ev_ebit", "fcf_yield", "earnings_yield") if k in metric_facts},
        "financials": {k: metric_facts[k] for k in ("roe", "roic", "operating_margin") if k in metric_facts},
        "momentum": {k: metric_facts[k] for k in ("return_12m",) if k in metric_facts},
        "growth": {
            "revenue_yoy": fact(_num(r.get("revenue_yoy")), as_of=as_of, source="OpenDART TTM", kind="observed", formula="매출 TTM / 1년 전 매출 TTM − 1", freshness=as_of),
            "op_yoy": fact(_num(r.get("op_yoy")), as_of=as_of, source="OpenDART TTM", kind="observed", formula="영업이익 TTM / 1년 전 영업이익 TTM − 1", freshness=as_of),
            "revenue_3y_cagr": fact(_num(r.get("revenue_3y_cagr")), as_of=as_of, source="OpenDART", kind="observed", formula="매출 3년 CAGR", freshness=as_of),
            "op_3y_cagr": fact(_num(r.get("op_3y_cagr")), as_of=as_of, source="OpenDART", kind="observed", formula="영업이익 3년 CAGR", freshness=as_of),
        },
        "leverage": {
            "net_debt_assets": fact(_num(r.get("net_debt_assets")), as_of=as_of, source="OpenDART", kind="observed", formula="순이자부채 / 자산", freshness=as_of),
            "interest_coverage": fact(_num(r.get("interest_coverage")), as_of=as_of, source="OpenDART TTM", kind="observed", formula="영업이익 TTM / 이자비용 TTM", freshness=as_of),
        },
        "confidence": fact(_num(r.get("data_confidence")), as_of=as_of, source="로컬 품질 게이트", kind="model", formula="coverage·PIT·신선도·대사·이력 가중합", freshness=as_of),
        "confidence_components": conf,
        "data_flags": flags,
        "coverage": _num(r.get("weighted_metric_coverage")),
        "scorecard": _clean(scorecard),
        "sparkline": sparkline(prices, ticker),
        "flow": {
            "status": "미수집",
            "note": "가격만으로 외인·기금 수급을 만들지 않습니다. KIS 공식 수급이 있을 때만 시장 요약의 수급 오버레이에 표시합니다.",
            "source": "KIS (보조, used_in_quant=false)",
            "missing": True,
        },
        "filings": {
            "status": "미수집",
            "note": "공개 스냅샷에는 OpenDART 원문 응답을 넣지 않습니다. 공시 원문은 OpenDART에서 확인하세요.",
            "source": "OpenDART",
            "link": "https://opendart.fss.or.kr",
            "missing": True,
        },
        "news": {
            "status": "미수집",
            "note": "네이버 뉴스는 탐색용이며 투자 사실의 단독 근거로 쓰지 않아 공개 스냅샷에 넣지 않습니다.",
            "source": "Naver (탐색 전용, 미수록)",
            "missing": True,
        },
        "ai": {
            "used_in_quant": False,
            "note": "AI는 분석 설명만 담당하며 퀀트 점수와 순위를 수정하지 않습니다. 공개 사이트에는 AI 실행 UI가 없습니다.",
        },
        "recompute": _recompute_check(r),
    }


def _recompute_check(r: pd.Series) -> dict[str, Any]:
    parts = [
        _num(r.get("value_score")) or 0.0,
        _num(r.get("quality_score")) or 0.0,
        _num(r.get("growth_score")) or 0.0,
        _num(r.get("momentum_score")) or 0.0,
        _num(r.get("financial_score")) or 0.0,
    ]
    penalty = _num(r.get("risk_penalty")) or 0.0
    expected = sum(parts) - penalty
    actual = _num(r.get("quant_score"))
    ok = actual is not None and abs(expected - actual) < 0.05
    missing_inputs = [_n for _n, v in (
        ("value_score", r.get("value_score")),
        ("quality_score", r.get("quality_score")),
        ("growth_score", r.get("growth_score")),
        ("momentum_score", r.get("momentum_score")),
        ("financial_score", r.get("financial_score")),
    ) if not _is_num(v)]
    return {
        "formula": FORMULAS["quant_score"]["formula"],
        "sum_of_factors": round(sum(parts), 6),
        "risk_penalty": penalty,
        "expected": round(expected, 6),
        "actual": actual,
        "match": ok,
        "missing_inputs": missing_inputs,
        "note": None if ok else "팩터 합과 종합점수가 어긋나면 스냅샷을 재계산하세요. 공개 사이트는 값을 고치지 않습니다.",
    }


def sanitize_flow(raw: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return {
            "missing": True,
            "display": "미수집",
            "source": "KIS",
            "kind": "official",
            "note": "공식 수급 캐시가 없습니다. 가격으로부터 수급을 추정하지 않았습니다.",
            "used_in_quant": False,
        }
    def slim(rows: list, n: int = 12) -> list[dict[str, Any]]:
        out = []
        for row in rows[:n]:
            if not isinstance(row, dict):
                continue
            out.append({
                "ticker": str(row.get("ticker") or "").zfill(6),
                "company": row.get("company") or "",
                "foreign_net": _num(row.get("foreign_net")),
                "institution_net": _num(row.get("institution_net")),
                "fund_net": _num(row.get("pension_net") if row.get("pension_net") is not None else row.get("fund_net")),
                "fund_label": "기금",
                "fund_note": "원천이 연기금·국민연금을 명시하지 않아 기금으로만 표기합니다.",
                "from": row.get("from"),
                "to": row.get("to"),
            })
        return out
    return {
        "missing": False,
        "used_in_quant": False,
        "source": "KIS 교차검증/보조 (used_in_quant=false)",
        "kind": "official",
        "fetched_at": raw.get("fetched_at"),
        "disclaimer": "기금(FUND)은 연기금·국민연금으로 바꾸지 않았습니다. 토스 분류도 국민연금 단독이 아닙니다. 가격만으로 수급을 만들지 않았습니다.",
        "dual": slim(raw.get("dual") or []),
        "fund": slim(raw.get("pension") or []),
        "empty": slim(raw.get("empty") or []),
    }


def sources_catalog(as_of: str) -> list[dict[str, Any]]:
    return [
        {"id": "KRX", "role": "기본", "covers": "종목 마스터·일봉 가격·시가총액", "kind": "official", "link": "https://openapi.krx.co.kr", "as_of": as_of, "used_in_quant": True},
        {"id": "OpenDART", "role": "기본", "covers": "재무제표 TTM·공시", "kind": "official", "link": "https://opendart.fss.or.kr", "as_of": as_of, "used_in_quant": True, "pit": "available_date ≤ run_date"},
        {"id": "KIS", "role": "교차검증·보조", "covers": "투자자별 수급", "kind": "official", "link": "https://apiportal.koreainvestment.com", "as_of": as_of, "used_in_quant": False, "note": "FUND는 기금으로 표기. 연기금으로 바꾸지 않음."},
        {"id": "ECOS", "role": "거시", "covers": "한국은행 금리·물가 등", "kind": "official", "link": "https://ecos.bok.or.kr", "used_in_quant": False},
        {"id": "FRED", "role": "거시", "covers": "연준·미국 금리", "kind": "official", "link": "https://fred.stlouisfed.org", "used_in_quant": False},
        {"id": "Naver", "role": "탐색 전용", "covers": "뉴스 탐색", "kind": "exploration", "link": "https://news.naver.com", "used_in_quant": False, "note": "투자 사실의 단독 근거로 쓰지 않아 공개 스냅샷에 수록하지 않습니다."},
    ]


def export(out_dir: Path) -> dict[str, Any]:
    settings = load_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    stocks = load_all_stocks(settings)
    quality_path = settings.output_dir / "data_quality_report.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    as_of = str(quality.get("as_of_date") or (stocks["as_of_date"].iloc[0] if not stocks.empty and "as_of_date" in stocks.columns else "미수집"))
    fresh = _clean(freshness_snapshot(settings, screen_as_of=as_of if as_of != "미수집" else None))
    explain = explain_run_status(quality, status_csv_exists=settings.status_csv.exists())

    prices = pd.DataFrame()
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        p = folder / "prices.parquet"
        if p.exists():
            prices = pd.read_parquet(p, columns=["ticker", "trade_date", "close"])
            break

    watch_raw = load_watchlist(settings.root)
    watch_codes = [str(w.get("ticker") or "").zfill(6) for w in watch_raw]

    ranking_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    if not stocks.empty:
        elig = stocks[stocks["universe_eligible"] == True].copy() if "universe_eligible" in stocks.columns else stocks.copy()
        if "quant_rank" in elig.columns:
            elig = elig.sort_values("quant_rank", na_position="last")
        ranking_rows = [compact_row(r, as_of) for _, r in elig.iterrows()]
        want = set(watch_codes)
        if "top100_eligible" in stocks.columns:
            want.update(stocks.loc[stocks["top100_eligible"] == True, "ticker"].astype(str).str.zfill(6).tolist())
        elif ranking_rows:
            want.update(r["ticker"] for r in ranking_rows[:100])
        hit = stocks[stocks["ticker"].isin(want)]
        for _, r in hit.iterrows():
            details[str(r["ticker"]).zfill(6)] = stock_detail(r, as_of, prices)

    watch = []
    for w in watch_raw:
        code = str(w.get("ticker") or "").zfill(6)
        row = next((r for r in ranking_rows if r["ticker"] == code), None)
        watch.append({
            "ticker": code,
            "company": (row or {}).get("company") or w.get("company") or code,
            "note": w.get("note") or "",
            "quant_rank": (row or {}).get("quant_rank"),
            "quant_score": (row or {}).get("quant_score"),
            "missing_score": row is None,
        })

    flow_path = settings.root / "data" / "cache" / "investor_flow.json"
    flow_raw = {}
    if flow_path.exists():
        try:
            flow_raw = json.loads(flow_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            flow_raw = {}
    flow = sanitize_flow(flow_raw)

    try:
        from kr_quant.portfolio.analysis import analyze_top20
        portfolio = _clean(analyze_top20(settings))
    except Exception as exc:  # noqa: BLE001
        portfolio = {"missing": True, "error": "미수집", "detail": str(exc)[:160]}

    match_n = sum(1 for d in details.values() if d.get("recompute", {}).get("match"))
    meta = {
        "product": "KR Quant Research",
        "mode": "public-readonly-snapshot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of,
        "cutoff_ts": str(stocks["cutoff_ts"].iloc[0]) if not stocks.empty and "cutoff_ts" in stocks.columns else None,
        "model_version": quality.get("model_version") or (str(stocks["model_version"].iloc[0]) if not stocks.empty and "model_version" in stocks.columns else None),
        "run_id": quality.get("run_id"),
        "result_hash": quality.get("result_hash"),
        "config_hash": (quality.get("config_hash") or "")[:16],
        "orders": False,
        "ai_mutates_quant": False,
        "public_ui": {"settings": False, "ai_run": False, "jobs": False},
        "recompute_pass": match_n,
        "recompute_total": len(details),
        "disclaimer": "검증된 로컬 스냅샷입니다. 투자 권유가 아니며 주문을 내지 않습니다. AI는 점수를 고치지 않습니다.",
    }
    market = {
        "as_of": as_of,
        "quality_status": quality.get("status") or "no-run",
        "counts": quality.get("counts") or {},
        "warnings": [{"code": w, "label": WARNING_KO.get(w, w), "fix": WARNING_FIX.get(w, "")} for w in (quality.get("warnings") or [])],
        "explain": explain,
        "freshness": fresh,
        "portfolio": portfolio,
        "top20": ranking_rows[:20],
        "used_in_quant": {"krx": True, "opendart": True, "kis_flow": False, "macro": False, "naver": False},
    }
    payload = {
        "meta": _clean(meta),
        "market": _clean(market),
        "ranking": _clean(ranking_rows),
        "watchlist": _clean(watch),
        "stocks": _clean(details),
        "flow": _clean(flow),
        "quality": _clean(quality),
        "sources": sources_catalog(as_of),
        "formulas": FORMULAS,
    }
    (out_dir / "snapshot.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for name, data in payload.items():
        (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist-public/data")
    args = parser.parse_args()
    meta = export(Path(args.out))
    print(json.dumps({"ok": True, "as_of": meta.get("as_of_date"), "stocks": meta.get("recompute_total")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
