from __future__ import annotations

import json
from typing import Any


def clean_reason_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if hasattr(raw, "tolist") and not isinstance(raw, (str, bytes, list, tuple)):
        try:
            raw = raw.tolist()
        except Exception:  # noqa: BLE001
            raw = str(raw)
    if isinstance(raw, float) and raw != raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        values = list(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if text in {"", "[]", "()", "{}", "None", "nan", "NaN"}:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text.replace("'", '"'))
                values = parsed if isinstance(parsed, list) else [text]
            except json.JSONDecodeError:
                values = [p for p in text.split("|") if p]
        else:
            values = [p for p in text.split("|") if p]
    else:
        values = [raw]
    out: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in {"[]", "None", "nan"}:
            out.append(text)
    return out


def interpret_row(row: dict[str, Any]) -> dict[str, Any]:
    """Korean explanation of why a name appeared. Never changes scores."""
    coverage = float(row.get("weighted_metric_coverage") or 0)
    confidence = float(row.get("data_confidence") or 0)
    eligible = bool(row.get("top20_eligible") or row.get("universe_eligible"))
    value = row.get("value_score")
    quality = row.get("quality_score")
    growth = row.get("growth_score")
    financial = row.get("financial_score")
    momentum = row.get("momentum_score")
    positives: list[str] = []
    cautions: list[str] = []

    if coverage >= 0.9:
        positives.append("필수 재무·가격 커버리지가 충분합니다.")
    elif coverage < 0.5:
        cautions.append("팩터 커버리지가 낮아 점수만 보고 판단하면 안 됩니다.")
    if confidence >= 80:
        positives.append("데이터 신뢰도가 높습니다.")
    elif confidence < 70:
        cautions.append("데이터 신뢰도가 낮습니다. 재무를 보강한 뒤에 보세요.")
    for label, val, bar in (
        ("가치", value, 18),
        ("품질", quality, 15),
        ("성장", growth, 15),
        ("안정", financial, 6),
        ("모멘텀", momentum, 6),
    ):
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num >= bar:
            positives.append(f"{label} 점수가 상대적으로 높습니다 ({num:.1f}).")
    if row.get("momentum_enabled") is False:
        cautions.append("모멘텀은 이번 실행에서 꺼져 있습니다.")
    reasons = clean_reason_list(row.get("exclusion_reasons"))
    if reasons:
        cautions.append("제외 사유: " + ", ".join(reasons[:4]))
    if not eligible:
        conclusion = "유니버스 또는 TOP 게이트를 통과하지 못했습니다."
    elif cautions and coverage < 0.8:
        conclusion = "데이터 보강 전 판단 보류"
    elif eligible:
        conclusion = "재무 게이트를 통과한 조사 후보입니다. 매수 신호가 아닙니다."
    else:
        conclusion = "추가 확인이 필요합니다."
    return {
        "conclusion": conclusion,
        "selection_reason": "Quant는 Value/Quality/Growth/Stability와, KRX 상장주식수로 분할 보정한 모멘텀을 씁니다. 배당 재투자는 넣지 않습니다.",
        "positives": positives,
        "cautions": cautions,
        "used_in_quant": False,
    }
