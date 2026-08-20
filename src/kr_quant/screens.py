"""Research screens inspired by Toss 골라보기 names. Our formulas, not Toss API."""

from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from kr_quant.settings import Settings

FilterFn = Callable[[pd.DataFrame], pd.DataFrame]


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def _eligible(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    if "universe_eligible" in out.columns:
        out = out[out["universe_eligible"] == True]  # noqa: E712
    return out


def _top(df: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    if "quant_score" in df.columns:
        df = df.sort_values("quant_score", ascending=False)
    return df.head(n)


def screen_uptrend(df: pd.DataFrame) -> pd.DataFrame:
    r3, r6 = _num(df, "return_3m"), _num(df, "return_6m")
    mom = _num(df, "momentum_score")
    hit = df[(r3 > 0) & (r6 > 0) & (mom >= 5)]
    return _top(hit)


def screen_value_growth(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "value_score") >= 18) & (_num(df, "growth_score") >= 15)]
    return _top(hit)


def screen_cheap_value(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "value_score") >= 20) & (_num(df, "growth_score") < 18)]
    return _top(hit)


def screen_cash_return(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "fcf_yield") > 0.04) & (_num(df, "financial_score") >= 5)]
    return _top(hit)


def screen_earners(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "roic") > 0.08) & (_num(df, "quality_score") >= 15) & (_num(df, "roe") > 0.08)]
    return _top(hit)


def screen_value_turn(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "value_score") >= 18) & (_num(df, "return_3m") > 0) & (_num(df, "momentum_score") >= 4)]
    return _top(hit)


def screen_future_cash(df: pd.DataFrame) -> pd.DataFrame:
    nda = _num(df, "net_debt_assets")
    hit = df[(_num(df, "fcf_yield") > 0.03) & (_num(df, "quality_score") >= 14) & (nda.fillna(1) < 0.35)]
    return _top(hit)


def screen_growth(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "growth_score") >= 18) & (_num(df, "revenue_yoy") > 0)]
    return _top(hit)


def screen_quality_value(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[(_num(df, "value_score") >= 16) & (_num(df, "quality_score") >= 16)]
    return _top(hit)


def screen_stable_growth(df: pd.DataFrame) -> pd.DataFrame:
    hit = df[
        (_num(df, "growth_score") >= 14)
        & (_num(df, "financial_score") >= 6)
        & (_num(df, "quality_score") >= 14)
        & (_num(df, "risk_penalty").fillna(0) < 4)
    ]
    return _top(hit)


SCREENS: list[dict[str, Any]] = [
    {
        "id": "uptrend",
        "name": "연속 상승세",
        "popular": True,
        "how": "3개월·6개월 수익률이 모두 플러스이고 모멘텀 점수가 있는 종목",
        "fn": screen_uptrend,
    },
    {
        "id": "value_growth",
        "name": "저평가 성장주",
        "popular": True,
        "how": "가치 점수 18 이상, 성장 점수 15 이상",
        "fn": screen_value_growth,
    },
    {
        "id": "cheap_value",
        "name": "아직 저렴한 가치주",
        "popular": False,
        "how": "가치는 높은데 성장 점수는 아직 낮은 종목",
        "fn": screen_cheap_value,
    },
    {
        "id": "cash_return",
        "name": "꾸준한 배당주",
        "popular": True,
        "how": "배당 공식이 없어 FCF 수익률 4%+와 안정 점수로 현금 여력을 봅니다",
        "fn": screen_cash_return,
    },
    {
        "id": "earners",
        "name": "돈 잘버는 회사 찾기",
        "popular": False,
        "how": "ROIC·ROE 8% 이상, 품질 점수 15 이상",
        "fn": screen_earners,
    },
    {
        "id": "value_turn",
        "name": "저평가 탈출",
        "popular": False,
        "how": "가치는 싼데 최근 3개월 수익률이 플러스로 돌아선 종목",
        "fn": screen_value_turn,
    },
    {
        "id": "future_cash",
        "name": "미래의 배당왕 찾기",
        "popular": False,
        "how": "FCF 수익률·품질·낮은 순부채. 실제 배당 이력이 아닙니다",
        "fn": screen_future_cash,
    },
    {
        "id": "growth",
        "name": "성장 기대주",
        "popular": False,
        "how": "성장 점수 18 이상, 매출 YoY 플러스",
        "fn": screen_growth,
    },
    {
        "id": "dual",
        "name": "쌍끌이 매수",
        "popular": True,
        "how": "토스 수급에서 외인·기관이 같이 산 종목. 재무 게이트와 겹치면 위에 둡니다",
        "fn": None,
    },
    {
        "id": "quality_value",
        "name": "고수익 저평가",
        "popular": True,
        "how": "가치·품질 점수가 같이 높은 종목",
        "fn": screen_quality_value,
    },
    {
        "id": "stable_growth",
        "name": "안정 성장주",
        "popular": False,
        "how": "성장·품질·안정 점수가 있고 리스크 페널티가 작은 종목",
        "fn": screen_stable_growth,
    },
]


def _flow_dual_tickers(settings: Settings) -> set[str]:
    path = settings.root / "data" / "cache" / "investor_flow.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    tickers: set[str] = set()
    for row in data.get("dual") or []:
        code = str(row.get("ticker") or "").zfill(6)
        if code and row.get("dual"):
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
        "comment_short": extra,
    }


def list_screens() -> list[dict[str, Any]]:
    return [{"id": s["id"], "name": s["name"], "popular": s["popular"], "how": s["how"]} for s in SCREENS]


def run_screen(settings: Settings, screen_id: str) -> dict[str, Any]:
    spec = next((s for s in SCREENS if s["id"] == screen_id), None)
    if spec is None:
        return {"configured": False, "used_in_quant": False, "error": "없는 목록입니다.", "rows": []}
    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return {"configured": False, "used_in_quant": False, "error": "점수 결과가 없습니다.", "rows": []}
    df = _eligible(pd.read_parquet(path))
    if spec["id"] == "dual":
        dual = _flow_dual_tickers(settings)
        hit = df[df["ticker"].isin(dual)] if dual else df.iloc[0:0]
        note = "수급 쌍끌이"
    else:
        hit = spec["fn"](df)
        note = spec["how"]
    rows = [_row_public(r, note) for r in hit.head(40).to_dict("records")]
    return {
        "configured": True,
        "used_in_quant": False,
        "id": spec["id"],
        "name": spec["name"],
        "how": spec["how"],
        "n": len(rows),
        "disclaimer": "토스 골라보기 이름을 참고한 우리 공식입니다. 토스 목록을 긁어오지 않으며 Quant 점수에 합산하지 않습니다.",
        "rows": rows,
    }


def screens_payload(settings: Settings, screen_id: str | None = None) -> dict[str, Any]:
    catalog = list_screens()
    chosen = screen_id or "value_growth"
    body = run_screen(settings, chosen)
    return {
        "used_in_quant": False,
        "selection": "토스 주식 골라보기와 비슷한 이름으로 우리 재무·수급 규칙을 걸러 봅니다. 공식 API가 없어 긁지 않습니다.",
        "catalog": catalog,
        **body,
    }
