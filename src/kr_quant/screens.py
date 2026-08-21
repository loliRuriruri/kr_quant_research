"""Research screens inspired by Toss 골라보기 names. Our formulas, not Toss API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from kr_quant.settings import Settings

FilterFn = Callable[[pd.DataFrame], pd.DataFrame]


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def _eligible(df: pd.DataFrame) -> pd.DataFrame:
    """Liquidity/common-stock universe, not TOP20."""
    out = df.copy()
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    if "universe_eligible" in out.columns:
        out = out[out["universe_eligible"] == True]  # noqa: E712
    return out


def _top(df: pd.DataFrame, n: int = 50, by: str | None = None) -> pd.DataFrame:
    col = by or ""
    if col and col in df.columns:
        df = df.sort_values(col, ascending=False, na_position="last")
    elif "quant_score" in df.columns:
        df = df.sort_values("quant_score", ascending=False, na_position="last")
    return df.head(n)


def _load_stocks_df(settings: Settings) -> pd.DataFrame:
    candidates: list[Path] = []
    if settings.output_dir.exists():
        run_folders = sorted(settings.output_dir.glob("as_of_date=*"), key=lambda p: p.name, reverse=True)
        for rf in run_folders:
            candidates.append(rf / "all_stocks.parquet")

    candidates.append(settings.output_dir / "latest_all_stocks.parquet")
    candidates.append(settings.root / "data" / "output" / "latest_all_stocks.parquet")

    for path in candidates:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                if not df.empty and len(df) > 0:
                    return df
            except Exception:
                continue

    top_csv = settings.output_dir / "latest_top100.csv"
    if top_csv.exists():
        try:
            return pd.read_csv(top_csv)
        except Exception:
            pass

    return pd.DataFrame()


def screen_uptrend(df: pd.DataFrame) -> pd.DataFrame:
    mom = _num(df, "momentum_score").fillna(0)
    r3 = _num(df, "return_3m").fillna(0)
    hit = df[(mom >= 3.0) | (r3 > 0)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = mom + (r3 * 10)
    return _top(work, by="_s")


def screen_value_growth(df: pd.DataFrame) -> pd.DataFrame:
    v = _num(df, "value_score").fillna(0)
    g = _num(df, "growth_score").fillna(0)
    hit = df[(v >= 18) & (g >= 15)]
    if hit.empty:
        hit = df[(v >= 12) & (g >= 10)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = v + g
    return _top(work, by="_s")


def screen_cheap_value(df: pd.DataFrame) -> pd.DataFrame:
    v = _num(df, "value_score").fillna(0)
    hit = df[v >= 12]
    if hit.empty:
        hit = df
    return _top(hit, by="value_score")


def screen_cash_return(df: pd.DataFrame) -> pd.DataFrame:
    fcf = _num(df, "fcf_yield").fillna(0)
    fin = _num(df, "financial_score").fillna(0)
    hit = df[(fcf > 0.01) | (fin >= 4.5)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = (fcf * 100) + fin
    return _top(work, by="_s")


def screen_earners(df: pd.DataFrame) -> pd.DataFrame:
    q = _num(df, "quality_score").fillna(0)
    roic = _num(df, "roic").fillna(0)
    roe = _num(df, "roe").fillna(0)
    hit = df[(q >= 12) | (roic > 0.04) | (roe > 0.05)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = q + (roic * 50) + (roe * 50)
    return _top(work, by="_s")


def screen_value_turn(df: pd.DataFrame) -> pd.DataFrame:
    v = _num(df, "value_score").fillna(0)
    m = _num(df, "momentum_score").fillna(0)
    hit = df[(v >= 10) & (m >= 3.0)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = v + m
    return _top(work, by="_s")


def screen_future_cash(df: pd.DataFrame) -> pd.DataFrame:
    q = _num(df, "quality_score").fillna(0)
    fin = _num(df, "financial_score").fillna(0)
    hit = df[(q >= 10) & (fin >= 4.5)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = q + fin
    return _top(work, by="_s")


def screen_growth(df: pd.DataFrame) -> pd.DataFrame:
    g = _num(df, "growth_score").fillna(0)
    hit = df[g >= 12]
    if hit.empty:
        hit = df
    return _top(hit, by="growth_score")


def screen_quality_value(df: pd.DataFrame) -> pd.DataFrame:
    v = _num(df, "value_score").fillna(0)
    q = _num(df, "quality_score").fillna(0)
    hit = df[(v >= 10) & (q >= 10)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = v + q
    return _top(work, by="_s")


def screen_stable_growth(df: pd.DataFrame) -> pd.DataFrame:
    g = _num(df, "growth_score").fillna(0)
    q = _num(df, "quality_score").fillna(0)
    f = _num(df, "financial_score").fillna(0)
    hit = df[(g >= 10) & (q >= 10) & (f >= 4.0)]
    if hit.empty:
        hit = df
    work = hit.copy()
    work["_s"] = g + q + f
    return _top(work, by="_s")


SCREENS: list[dict[str, Any]] = [
    {
        "id": "uptrend",
        "name": "연속 상승세",
        "popular": True,
        "how": "조건 통과 종목에서 모멘텀 및 3개월 수익률 상위 종목. TOP20 전용이 아니고 모멘텀 순입니다",
        "fn": screen_uptrend,
    },
    {
        "id": "value_growth",
        "name": "저평가 성장주",
        "popular": True,
        "how": "가치 18 · 성장 15 이상 (또는 상대 상위 균형), 가치+성장 합산 순으로 정렬합니다",
        "fn": screen_value_growth,
    },
    {
        "id": "cheap_value",
        "name": "아직 저렴한 가치주",
        "popular": False,
        "how": "가치 점수 상위 종목. 종합 점수 대신 순수 밸류에이션 순으로 보여 줍니다",
        "fn": screen_cheap_value,
    },
    {
        "id": "cash_return",
        "name": "꾸준한 배당주",
        "popular": True,
        "how": "FCF 수익률과 재무 안정성 점수로 현금 창출 여력을 봅니다",
        "fn": screen_cash_return,
    },
    {
        "id": "earners",
        "name": "돈 잘버는 회사 찾기",
        "popular": False,
        "how": "ROIC·ROE 및 자본 효율성 품질 점수 상위 기업",
        "fn": screen_earners,
    },
    {
        "id": "value_turn",
        "name": "저평가 탈출",
        "popular": False,
        "how": "밸류에이션이 저평가 상태이면서 최근 모멘텀이 살아나는 턴어라운드 종목",
        "fn": screen_value_turn,
    },
    {
        "id": "future_cash",
        "name": "미래의 배당왕 찾기",
        "popular": False,
        "how": "품질 점수 및 건전한 재무 구조를 갖춘 미래 잉여현금흐름 우수 기업",
        "fn": screen_future_cash,
    },
    {
        "id": "growth",
        "name": "성장 기대주",
        "popular": False,
        "how": "매출 및 영업이익 성장 팩터 점수 상위 종목",
        "fn": screen_growth,
    },
    {
        "id": "dual",
        "name": "쌍끌이 매수",
        "popular": True,
        "how": "외국인·기관합계 동시 순매수 유입 종목. (수급 스캔 데이터 연동)",
        "fn": None,
    },
    {
        "id": "dual_pe",
        "name": "쌍끌이+사모",
        "popular": True,
        "how": "외인·기관 쌍끌이와 사모펀드 순매수가 겹친 집중 수급 종목",
        "fn": None,
    },
    {
        "id": "dual_pe_retail",
        "name": "쌍끌이+사모+개인이탈",
        "popular": False,
        "how": "쌍끌이·사모 매수에 개인 순매도가 겹친 극단 메이저 수급 종목",
        "fn": None,
    },
    {
        "id": "quality_value",
        "name": "고수익 저평가",
        "popular": True,
        "how": "가치 및 자본 수익성 품질 점수가 동시에 높은 우량 가치주",
        "fn": screen_quality_value,
    },
    {
        "id": "stable_growth",
        "name": "안정 성장주",
        "popular": False,
        "how": "성장·품질·재무 안정성 점수가 고르게 높고 변동성 리스크가 낮은 종목",
        "fn": screen_stable_growth,
    },
]


def _flow_tickers(settings: Settings, key: str) -> set[str]:
    candidates = [
        settings.root / "data" / "cache" / "investor_flow.json",
        settings.data_dir / "cache" / "investor_flow.json",
    ]
    data: dict[str, Any] = {}
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data:
                    break
            except json.JSONDecodeError:
                continue

    if not data:
        return set()

    tickers: set[str] = set()
    raw_rows = (
        data.get(key)
        or data.get(f"{key}_buyers")
        or data.get(f"{key}_sellers")
        or []
    )
    for row in raw_rows:
        if isinstance(row, dict):
            code = str(row.get("ticker") or "").zfill(6)
            if code:
                tickers.add(code)
        elif isinstance(row, str):
            code = str(row).zfill(6)
            if code:
                tickers.add(code)
    return tickers


def _row_public(rec: dict[str, Any], extra: str = "") -> dict[str, Any]:
    return {
        "ticker": str(rec.get("ticker") or "").zfill(6),
        "company": rec.get("company"),
        "industry": rec.get("industry") or rec.get("sector"),
        "quant_rank": rec.get("quant_rank"),
        "quant_score": rec.get("quant_score"),
        "value_score": rec.get("value_score"),
        "quality_score": rec.get("quality_score"),
        "growth_score": rec.get("growth_score"),
        "momentum_score": rec.get("momentum_score"),
        "financial_score": rec.get("financial_score"),
        "top20_eligible": rec.get("top20_eligible"),
        "fa_label": rec.get("fa_label"),
        "comment_short": extra,
    }


def list_screens() -> list[dict[str, Any]]:
    return [{"id": s["id"], "name": s["name"], "popular": s["popular"], "how": s["how"]} for s in SCREENS]


def run_screen(settings: Settings, screen_id: str, *, include_quant: bool = True) -> dict[str, Any]:
    spec = next((s for s in SCREENS if s["id"] == screen_id), None)
    if spec is None:
        return {"configured": False, "used_in_quant": False, "error": "없는 목록입니다.", "rows": []}
    raw = _load_stocks_df(settings)
    if raw.empty:
        return {"configured": False, "used_in_quant": False, "error": "점수 결과가 없습니다. 실행 탭에서 데모 또는 퀀트를 실행하세요.", "rows": []}
    df = _eligible(raw)
    if df.empty:
        df = raw

    flow_map = {"dual": "dual", "dual_pe": "dual_pe", "dual_pe_retail": "dual_pe_retail"}
    if spec["id"] in flow_map:
        tickers = _flow_tickers(settings, flow_map[spec["id"]])
        hit = df[df["ticker"].isin(tickers)] if tickers else df.iloc[0:0]
        if hit.empty:
            # Fallback to top momentum/flow candidates
            hit = _top(df, n=20, by="momentum_score")
            spec = {
                **spec,
                "how": f"{spec['how']} (실시간 수급 스캔 전이므로 모멘텀 상위 후보를 표시합니다. [수급] 탭에서 수급을 스캔하면 실시간으로 동기화됩니다.)",
            }
    else:
        fn = spec.get("fn")
        hit = fn(df) if fn else _top(df, n=30)

    from kr_quant.sunzi.fa import annotate_fa

    if not include_quant:
        if "top20_eligible" in hit.columns:
            non_top = hit[hit["top20_eligible"] != True]  # noqa: E712
            if not non_top.empty:
                hit = non_top
        elif "quant_rank" in hit.columns:
            non_top = hit[pd.to_numeric(hit["quant_rank"], errors="coerce").fillna(9999) > 20]
            if not non_top.empty:
                hit = non_top

    from kr_quant.web.comments import quant_comment_short

    recs = annotate_fa(hit.head(50).to_dict("records"))
    rows = [_row_public(r, quant_comment_short(r)) for r in recs]
    return {
        "configured": True,
        "used_in_quant": False,
        "id": spec["id"],
        "name": spec["name"],
        "how": spec["how"],
        "n": len(rows),
        "disclaimer": "토스 골라보기 이름을 참고한 우리 공식입니다. 토스 목록을 긁지 않습니다.",
        "include_quant": include_quant,
        "rows": rows,
    }


def screens_payload(settings: Settings, screen_id: str | None = None, *, include_quant: bool = True) -> dict[str, Any]:
    catalog = list_screens()
    chosen = screen_id or "value_growth"
    body = run_screen(settings, chosen, include_quant=include_quant)
    return {
        "used_in_quant": False,
        "selection": "시총·거래대금 조건을 통과한 종목에서 목록 규칙으로 거릅니다.",
        "catalog": catalog,
        **body,
    }
