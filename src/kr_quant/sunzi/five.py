"""손자 道天地將法 overlay board. Never writes quant_score."""

from __future__ import annotations

import time
from typing import Any

from kr_quant.settings import Settings
from kr_quant.sunzi.alignment import dao_panel, jiang_panel
from kr_quant.sunzi.critic import ASPECT_YANG, compose_yang_briefing, critic_panel
from kr_quant.sunzi.fa import annotate_fa, fa_gate

_TIAN_CACHE: dict[str, Any] = {"at": 0.0, "panel": None}


def _clip(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:
        return None
    return num


def tian_panel(settings: Settings | None = None, market: dict[str, Any] | None = None) -> dict[str, Any]:
    """天 = market regime. Same for every name that day. Overlay only."""
    regime: dict[str, Any] = {}
    components: list[dict[str, Any]] = []
    if isinstance(market, dict) and (market.get("regime_score") is not None or market.get("regime")):
        regime = market
        components = list(market.get("components") or [])
    elif settings is not None:
        now = time.time()
        cached = _TIAN_CACHE.get("panel")
        if cached and now - float(_TIAN_CACHE.get("at") or 0) < 90:
            return dict(cached)
        from kr_quant.context.market import COMPONENT_KO, derive_market_components, market_regime
        from kr_quant.layers.context import _market_config, load_price_frame

        prices = load_price_frame(settings)
        if prices is None or getattr(prices, "empty", True):
            panel = {
                "used_in_quant": False,
                "id": "tian",
                "label": "天 시장",
                "score": None,
                "confidence": "D",
                "regime": None,
                "regime_ko": "시세 없음",
                "evidence": [],
                "contrary": ["KRX 일봉이 없어 天을 못 그립니다."],
                "comment": "시장 국면은 天의 입력입니다. Quant에 넣지 않습니다.",
                "components": [],
            }
            _TIAN_CACHE.update({"at": now, "panel": panel})
            return dict(panel)
        cfg = _market_config(settings)
        raw = derive_market_components(prices)
        regime = market_regime(raw, cfg)
        for key, label in COMPONENT_KO.items():
            val = regime.get(key)
            if val is None:
                tone = "미연결"
            elif float(val) >= 60:
                tone = "우호"
            elif float(val) <= 40:
                tone = "부담"
            else:
                tone = "중립"
            components.append({"id": key, "label": label, "value": val, "tone": tone})
    score = _num(regime.get("regime_score"))
    label_ko = str(regime.get("label") or "")
    evidence: list[str] = []
    contrary: list[str] = []
    for item in components:
        tone = item.get("tone")
        val = item.get("value")
        bit = f"{item.get('label')} {tone}"
        if val is not None:
            bit += f" {float(val):.0f}"
        if tone == "우호":
            evidence.append(bit)
        elif tone == "부담":
            contrary.append(bit)
        elif tone and tone != "미연결":
            evidence.append(bit)
    if label_ko:
        evidence.insert(0, f"국면 {label_ko}.")
    conf = "B"
    if score is None:
        conf = "D"
    elif contrary and not evidence:
        conf = "C"
    panel = {
        "used_in_quant": False,
        "id": "tian",
        "label": "天 시장",
        "score": None if score is None else round(_clip(score), 1),
        "confidence": conf,
        "regime": regime.get("regime"),
        "regime_ko": label_ko or "미산정",
        "evidence": evidence[:6],
        "contrary": contrary[:6],
        "comment": (
            f"시장 국면 {label_ko or '미산정'}을 天으로 봅니다. 종목 공통이며 Quant와 합산하지 않습니다."
        ),
        "components": components,
    }
    if settings is not None:
        _TIAN_CACHE.update({"at": time.time(), "panel": panel})
    return dict(panel)


def di_panel(row: dict[str, Any], sector: dict[str, Any] | None = None) -> dict[str, Any]:
    """地 = industry ranking of this name. Overlay only."""
    name = str(row.get("industry") or row.get("sector") or (sector.get("name") if sector else "") or "미분류")
    evidence: list[str] = []
    contrary: list[str] = []
    if not sector:
        return {
            "used_in_quant": False,
            "id": "di",
            "label": "地 업종",
            "score": None,
            "confidence": "D",
            "industry": name,
            "state_ko": "표본부족",
            "evidence": [],
            "contrary": [f"{name} 업종 묶음이 없어 地를 못 붙입니다."],
            "comment": "업종 상대강도는 地입니다. Quant에 넣지 않습니다.",
        }
    score = _num(sector.get("score"))
    state = str(sector.get("state_ko") or "")
    if sector.get("comment"):
        evidence.append(str(sector["comment"]))
    if state in {"선행", "개선"}:
        evidence.append(f"{name} 상태 {state}.")
    elif state in {"약화", "부진"}:
        contrary.append(f"{name} 상태 {state}.")
    rs = sector.get("rs")
    if rs is not None:
        evidence.append(f"상대강도 {rs:.0f}.")
    return {
        "used_in_quant": False,
        "id": "di",
        "label": "地 업종",
        "score": None if score is None else round(_clip(score), 1),
        "confidence": "B" if score is not None else "D",
        "industry": name,
        "state_ko": state or "보통",
        "rank": sector.get("rank"),
        "n": sector.get("n"),
        "evidence": evidence[:5],
        "contrary": contrary[:4],
        "comment": (
            f"{name} 업종 조사 점수 {('—' if score is None else f'{score:.0f}')} · {state or '보통'}. "
            "한 종목 급등과 업종 강세를 가르기 위한 地이며 Quant에 합산하지 않습니다."
        ),
    }


def five_aspects(
    row: dict[str, Any],
    *,
    tian: dict[str, Any] | None = None,
    sector: dict[str, Any] | None = None,
    filings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fa = fa_gate(row) if not isinstance(row.get("fa"), dict) else row["fa"]
    dao = dao_panel(row, filings=filings)
    jiang = jiang_panel({**row, "fa_gate_pass": fa.get("fa_gate_pass")}, filings=filings)
    tian_p = tian if isinstance(tian, dict) and tian.get("id") == "tian" else tian_panel(market=tian)
    di = di_panel(row, sector)
    parts = {
        "dao": dao,
        "tian": tian_p,
        "di": di,
        "jiang": jiang,
        "fa": {
            "used_in_quant": False,
            "id": "fa",
            "label": fa.get("fa_label") or "法",
            "score": fa.get("fa_score"),
            "confidence": "A" if fa.get("fa_gate_pass") else "C",
            "fa_gate_pass": fa.get("fa_gate_pass"),
            "evidence": list(fa.get("fa_reasons_ko") or []) if not fa.get("fa_gate_pass") else ["데이터·리스크·공시 규율을 통과했습니다."],
            "contrary": list(fa.get("fa_reasons_ko") or []) if not fa.get("fa_gate_pass") else [],
            "comment": fa.get("comment"),
        },
    }
    scores = [_num(p.get("score")) for p in parts.values()]
    present = [s for s in scores if s is not None]
    overlay = round(sum(present) / len(present), 1) if present else None
    critic = critic_panel(row, parts)
    return {
        "used_in_quant": False,
        "ticker": str(row.get("ticker") or "").zfill(6) if row.get("ticker") else None,
        "company": row.get("company"),
        "quant_score": _num(row.get("quant_score")),
        "quant_rank": row.get("quant_rank"),
        "overlay_mean": overlay,
        "parts": parts,
        "critic": critic,
        "fa_gate_pass": fa.get("fa_gate_pass"),
        "comment": (
            "道天地將法은 조사 오버레이입니다. 평균은 참고용이며 재무 Quant 순위를 바꾸지 않습니다."
        ),
    }


def _sector_lookup(settings: Settings) -> dict[str, dict[str, Any]]:
    from kr_quant.sector.ranking import rank_sectors

    board = rank_sectors(settings)
    out: dict[str, dict[str, Any]] = {}
    for item in board.get("rows") or []:
        if isinstance(item, dict) and item.get("name"):
            out[str(item["name"])] = item
    return out


def _empty_board(tian: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    return {
        "used_in_quant": False,
        "configured": not bool(error),
        "error": error,
        "tian": tian,
        "aspects": [dict(spec, score=None, note="") for spec in ASPECT_YANG],
        "briefing": compose_yang_briefing(tian, {}, 0, 0, {}),
        "rows": [],
        "n": 0,
        "fa_pass_n": 0,
        "postures": {},
        "legend": [
            {"id": spec["id"], "han": spec["han"], "ko": spec["ko"], "where": spec["sunzi"], "yang": spec["yang"]}
            for spec in ASPECT_YANG
        ],
    }


def _load_scored_frame(settings: Settings):
    import pandas as pd

    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    if df is None or getattr(df, "empty", True):
        return None
    df = df.copy()
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return df


def _prices_name_records(settings: Settings, query: str, limit: int = 20) -> list[dict[str, Any]]:
    from kr_quant.strategy.run import _prices

    prices = _prices(settings)
    if prices is None or getattr(prices, "empty", True) or "ticker" not in prices.columns:
        return []
    q = query.strip()
    df = prices.copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    company = df["company"].astype(str) if "company" in df.columns else None
    if q.isdigit():
        hit = df[df["ticker"].str.contains(q, regex=False)]
    else:
        upper = q.upper()
        mask = df["ticker"].str.contains(q, case=False, regex=False)
        if company is not None:
            mask = mask | company.str.contains(q, case=False, regex=False) | company.str.upper().str.contains(upper, regex=False)
        hit = df[mask]
    if hit.empty:
        return []
    cols = [c for c in ("ticker", "company", "market") if c in hit.columns]
    uniq = hit[cols].drop_duplicates(subset=["ticker"]).head(limit)
    out: list[dict[str, Any]] = []
    for rec in uniq.to_dict("records"):
        out.append({
            "ticker": str(rec.get("ticker") or "").zfill(6),
            "company": rec.get("company") or rec.get("ticker"),
            "market": rec.get("market") or "KOSPI",
            "industry": rec.get("industry") or rec.get("sector") or "미분류",
        })
    return out


def _select_records(
    df,
    *,
    query: str | None,
    universe: str,
    market: str | None,
    n: int,
) -> list[dict[str, Any]]:
    work = df
    if market and market not in {"", "all"} and "market" in work.columns:
        work = work[work["market"].astype(str).str.upper() == str(market).upper()]
    q = (query or "").strip()
    if q:
        ticker = work["ticker"].astype(str) if "ticker" in work.columns else None
        company = work["company"].astype(str) if "company" in work.columns else None
        mask = None
        if ticker is not None:
            mask = ticker.str.contains(q, case=False, regex=False)
        if company is not None:
            cm = company.str.contains(q, case=False, regex=False)
            mask = cm if mask is None else (mask | cm)
        if mask is not None:
            work = work[mask]
    elif universe != "all" and "universe_eligible" in work.columns:
        work = work[work["universe_eligible"] == True]  # noqa: E712
    if "quant_rank" in work.columns:
        work = work.sort_values("quant_rank", na_position="last")
    elif "quant_score" in work.columns:
        work = work.sort_values("quant_score", ascending=False, na_position="last")
    return work.head(max(1, min(int(n), 400))).to_dict("records")


def _compact_row(rec: dict[str, Any], five: dict[str, Any]) -> dict[str, Any]:
    critic = five.get("critic") or {}
    industry = str(rec.get("industry") or rec.get("sector") or "미분류")
    return {
        "ticker": str(rec.get("ticker") or "").zfill(6),
        "company": rec.get("company"),
        "market": rec.get("market") or "",
        "industry": industry,
        "quant_score": None if rec.get("quant_score") is None else round(float(rec["quant_score"]), 1) if _num(rec.get("quant_score")) is not None else None,
        "quant_rank": rec.get("quant_rank"),
        "universe_eligible": bool(rec.get("universe_eligible")),
        "overlay_mean": five["overlay_mean"],
        "fa_gate_pass": five["fa_gate_pass"],
        "dao": five["parts"]["dao"]["score"],
        "tian": five["parts"]["tian"]["score"],
        "di": five["parts"]["di"]["score"],
        "jiang": five["parts"]["jiang"]["score"],
        "fa": five["parts"]["fa"]["score"],
        "di_state": five["parts"]["di"].get("state_ko"),
        "tian_regime": five["parts"]["tian"].get("regime_ko"),
        "fa_label": five["parts"]["fa"]["label"],
        "dao_comment": five["parts"]["dao"].get("comment"),
        "jiang_comment": five["parts"]["jiang"].get("comment"),
        "di_comment": five["parts"]["di"].get("comment"),
        "posture": critic.get("posture"),
        "posture_ko": critic.get("posture_ko"),
        "strategy_tag": critic.get("strategy_tag") or "知彼知己 (지피지기)",
        "tactical_briefing": critic.get("tactical_briefing") or critic.get("comment"),
        "maneuver_entry": critic.get("maneuver_entry") or "",
        "escape_route": critic.get("escape_route") or "",
        "axes": critic.get("axes") or {},
        "critic_score": critic.get("score"),
        "critic_comment": critic.get("comment"),
        "one_line_judgment": critic.get("one_line_judgment"),
        "sunzi_interpretation": critic.get("sunzi_interpretation") or {},
        "no_action_required": critic.get("no_action_required"),
        "variant": critic.get("variant"),
        "waiting_test": critic.get("waiting_test") or {},
        "strongest_bear_evidence": critic.get("strongest_bear_evidence") or [],
        "consensus": critic.get("consensus"),
        "fa_comment": rec.get("fa_comment") or five["parts"]["fa"].get("comment"),
        "fa_reasons_ko": rec.get("fa_reasons_ko") or [],
    }


def build_sunzi_board(
    settings: Settings,
    n: int = 40,
    query: str | None = None,
    universe: str = "quant",
    posture: str | None = None,
    fa_filter: str | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    tian = tian_panel(settings)
    sectors = _sector_lookup(settings)
    df = _load_scored_frame(settings)
    q = (query or "").strip()
    if df is None:
        if q:
            records = _prices_name_records(settings, q, limit=max(1, min(int(n), 40)))
            if not records:
                return _empty_board(tian, "그 이름으로는 전장 명부를 못 찾았습니다. 재계산을 먼저 하거나 종목코드를 넣어 보세요.")
        else:
            return _empty_board(tian, "스크리닝 결과가 없습니다. 재계산을 먼저 실행하세요.")
    else:
        records = _select_records(df, query=q or None, universe=universe, market=market, n=n)
        if q and not records:
            records = _prices_name_records(settings, q, limit=max(1, min(int(n), 40)))
        if not records:
            return _empty_board(tian, "조건에 맞는 종목이 없습니다. 필터를 풀어 보시죠.")
    annotate_fa(records)
    rows: list[dict[str, Any]] = []
    for rec in records:
        industry = str(rec.get("industry") or rec.get("sector") or "미분류")
        try:
            five = five_aspects(rec, tian=tian, sector=sectors.get(industry))
        except Exception:
            continue
        rows.append(_compact_row(rec, five))
    want_posture = (posture or "").strip().upper()
    if want_posture and want_posture not in {"", "ALL"}:
        rows = [r for r in rows if str(r.get("posture") or "").upper() == want_posture]
    fa_want = (fa_filter or "").strip().lower()
    if fa_want == "pass":
        rows = [r for r in rows if r.get("fa_gate_pass") is True]
    elif fa_want == "fail":
        rows = [r for r in rows if r.get("fa_gate_pass") is False]
    passed = sum(1 for r in rows if r.get("fa_gate_pass"))
    postures: dict[str, int] = {}
    for row in rows:
        key = str(row.get("posture") or "OBSERVE")
        postures[key] = postures.get(key, 0) + 1

    def _avg(key: str) -> float | None:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    aspect_scores = {
        "dao": _avg("dao"),
        "tian": tian.get("score"),
        "di": _avg("di"),
        "jiang": _avg("jiang"),
        "fa": _avg("fa"),
    }
    aspects = []
    for spec in ASPECT_YANG:
        item = dict(spec)
        item["score"] = aspect_scores.get(spec["id"])
        if spec["id"] == "fa":
            item["note"] = f"적격 {passed}/{len(rows)}"
        elif spec["id"] == "tian":
            item["note"] = str(tian.get("regime_ko") or "")
        else:
            item["note"] = "이 명단의 평균"
        aspects.append(item)
    focus_name = None
    if q and len(rows) == 1:
        focus_name = str(rows[0].get("company") or rows[0].get("ticker") or q)
    elif q:
        focus_name = q
    briefing = compose_yang_briefing(
        tian,
        postures,
        len(rows),
        passed,
        aspect_scores,
        focus_name=focus_name,
        scope="all" if (q or universe == "all") else "quant",
    )
    return {
        "used_in_quant": False,
        "configured": True,
        "n": len(rows),
        "fa_pass_n": passed,
        "query": q or None,
        "universe": "all" if (q or universe == "all") else "quant",
        "tian": tian,
        "aspects": aspects,
        "briefing": briefing,
        "postures": postures,
        "rows": rows,
        "legend": [
            {"id": spec["id"], "han": spec["han"], "ko": spec["ko"], "where": spec["sunzi"], "yang": spec["yang"]}
            for spec in ASPECT_YANG
        ],
        "disclaimer": (
            "이 판단은 Quant와 합산하지 않아. 착수는 매수가 아니고, 내 판단도 틀릴 수 있어."
        ),
    }
