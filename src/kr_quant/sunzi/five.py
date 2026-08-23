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


def build_sunzi_board(settings: Settings, n: int = 40) -> dict[str, Any]:
    import pandas as pd

    tian = tian_panel(settings)
    sectors = _sector_lookup(settings)
    path = settings.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return {
            "used_in_quant": False,
            "configured": False,
            "error": "스크리닝 결과가 없습니다. 재계산을 먼저 실행하세요.",
            "tian": tian,
            "aspects": [dict(spec, score=None, note="") for spec in ASPECT_YANG],
            "briefing": compose_yang_briefing(tian, {}, 0, 0, {}),
            "rows": [],
        }
    df = pd.read_parquet(path)
    if "universe_eligible" in df.columns:
        df = df[df["universe_eligible"] == True]  # noqa: E712
    if "quant_rank" in df.columns:
        df = df.sort_values("quant_rank", na_position="last")
    records = df.head(max(10, min(int(n), 100))).to_dict("records")
    annotate_fa(records)
    rows: list[dict[str, Any]] = []
    for rec in records:
        industry = str(rec.get("industry") or rec.get("sector") or "미분류")
        try:
            five = five_aspects(rec, tian=tian, sector=sectors.get(industry))
        except Exception:
            continue
        compact = {
            "ticker": str(rec.get("ticker") or "").zfill(6),
            "company": rec.get("company"),
            "industry": industry,
            "quant_score": None if rec.get("quant_score") is None else round(float(rec["quant_score"]), 1),
            "quant_rank": rec.get("quant_rank"),
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
            "posture": (five.get("critic") or {}).get("posture"),
            "posture_ko": (five.get("critic") or {}).get("posture_ko"),
            "critic_score": (five.get("critic") or {}).get("score"),
            "critic_comment": (five.get("critic") or {}).get("comment"),
            "no_action_required": (five.get("critic") or {}).get("no_action_required"),
            "variant": (five.get("critic") or {}).get("variant"),
            "fa_comment": rec.get("fa_comment") or five["parts"]["fa"].get("comment"),
            "fa_reasons_ko": rec.get("fa_reasons_ko") or [],
        }
        rows.append(compact)
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
            item["note"] = "상위 후보 평균"
        aspects.append(item)
    briefing = compose_yang_briefing(tian, postures, len(rows), passed, aspect_scores)
    return {
        "used_in_quant": False,
        "configured": True,
        "n": len(rows),
        "fa_pass_n": passed,
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
            "손자가 道·天·地·將·法으로 전장을 세면, 양웬리는 그걸 ‘이 싸움이 필요한가’로 읽습니다. "
            "원작 대사를 복제하지 않으며 착수=매수가 아니고 Quant와 합산하지 않습니다."
        ),
    }
