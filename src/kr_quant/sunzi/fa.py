"""法 (discipline) eligibility gate. Overlay only — never writes quant_score."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kr_quant.context.explain import clean_reason_list

_DEFAULT = {
    "used_in_quant": False,
    "min_data_confidence": 70,
    "min_coverage": 0.80,
    "critical_exclusions": [
        "AUDIT_OPINION_FAIL",
        "DISTRESS_STATUS",
        "TRADING_STATUS_EXCLUDED",
        "NEGATIVE_EQUITY",
        "STALE_FINANCIALS",
        "CORE_DATA_INCOMPLETE",
        "FILING_LINEAGE_CONFLICT",
    ],
    "critical_risk_any": ["CB_BW_OVERHANG", "REPEATED_CB_BW"],
    "critical_risk_pair": ["LEVERAGE_STRESS", "THIN_EQUITY"],
    "weights": {"confidence": 25, "risk": 20, "coverage": 20, "pit": 15, "eligibility": 20},
    "disclaimer": "法은 데이터·리스크·공시 규율 게이트입니다. 매수 지시가 아닙니다.",
}

REASON_KO = {
    "LOW_CONFIDENCE": "데이터 신뢰도가 문턱(70) 미만입니다.",
    "LOW_COVERAGE": "필수 지표 커버리지가 80% 미만입니다.",
    "CRITICAL_EXCLUSION": "감사·거래정지·자본잠식·공시 시효 같은 치명 제외가 있습니다.",
    "CRITICAL_RISK": "전환사채 오버행 또는 레버리지·자본 얇음이 겹칩니다.",
    "NOT_ELIGIBLE": "시총·거래대금·보통주 조건을 통과하지 못했습니다.",
}


def load_fa_config(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        return dict(_DEFAULT)
    path = Path(root) / "config" / "fa_gate.yaml"
    if not path.exists():
        return dict(_DEFAULT)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = dict(_DEFAULT)
    out.update(raw)
    return out


def _flags(raw: Any) -> list[str]:
    return [str(x) for x in clean_reason_list(raw) if x and x not in {"[]", "None"}]


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


def _clip(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def fa_gate(row: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or dict(_DEFAULT)
    conf = _num(row.get("data_confidence"))
    cov = _num(row.get("weighted_metric_coverage") if row.get("weighted_metric_coverage") is not None else row.get("coverage"))
    exclusions = _flags(row.get("exclusion_reasons"))
    risks = _flags(row.get("risk_flags"))
    data_flags = _flags(row.get("data_flags"))
    critical_ex = [c for c in exclusions if c in set(cfg.get("critical_exclusions") or [])]
    pair = set(cfg.get("critical_risk_pair") or [])
    any_risk = set(cfg.get("critical_risk_any") or [])
    critical_risk = [c for c in risks if c in any_risk]
    if pair and pair.issubset(set(risks)):
        critical_risk.extend(sorted(pair))
    min_conf = float(cfg.get("min_data_confidence") or 70)
    min_cov = float(cfg.get("min_coverage") or 0.8)
    reasons: list[str] = []
    if critical_ex:
        reasons.append("CRITICAL_EXCLUSION")
    if critical_risk:
        reasons.append("CRITICAL_RISK")
    if conf is not None and conf < min_conf:
        reasons.append("LOW_CONFIDENCE")
    if cov is not None and cov < min_cov:
        reasons.append("LOW_COVERAGE")
    if row.get("universe_eligible") is False:
        reasons.append("NOT_ELIGIBLE")
    reasons = list(dict.fromkeys(reasons))
    conf_s = 50.0 if conf is None else _clip(conf)
    cov_s = 50.0 if cov is None else _clip(cov * 100.0 if cov <= 1.5 else cov)
    risk_s = 100.0 if not critical_risk and not critical_ex else 15.0 if not critical_ex else 0.0
    if risks and not critical_risk:
        risk_s = 70.0
    pit_s = 100.0
    if "STALE_FINANCIALS" in exclusions or "STALE_FINANCIALS" in data_flags:
        pit_s = 0.0
    elif any("PIT" in x or "STALE" in x or "Q4" in x for x in data_flags):
        pit_s = 55.0
    elig_s = 100.0 if row.get("top20_eligible") else 75.0 if row.get("top100_eligible") else 50.0 if row.get("universe_eligible") else 20.0
    weights = cfg.get("weights") or _DEFAULT["weights"]
    score = (
        conf_s * float(weights.get("confidence") or 0)
        + risk_s * float(weights.get("risk") or 0)
        + cov_s * float(weights.get("coverage") or 0)
        + pit_s * float(weights.get("pit") or 0)
        + elig_s * float(weights.get("eligibility") or 0)
    ) / max(1.0, sum(float(v) for v in weights.values()))
    passed = not reasons
    reason_ko = [REASON_KO.get(code, code) for code in reasons]
    if passed:
        comment = "데이터·리스크·공시 규율을 통과해 A-후보로 봅니다."
    else:
        comment = " ".join(reason_ko) + " Quant 순위는 바꾸지 않고 A-후보만 제한합니다."
    return {
        "used_in_quant": False,
        "fa_gate_pass": passed,
        "a_candidate": passed,
        "fa_score": round(_clip(score), 1),
        "fa_reasons": reasons,
        "fa_reasons_ko": reason_ko,
        "fa_label": "法 통과" if passed else "法 미달",
        "comment": comment,
        "disclaimer": cfg.get("disclaimer") or _DEFAULT["disclaimer"],
        "parts": {
            "confidence": round(conf_s, 1),
            "risk": round(risk_s, 1),
            "coverage": round(cov_s, 1),
            "pit": round(pit_s, 1),
            "eligibility": round(elig_s, 1),
        },
    }


def annotate_fa(rows: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg or dict(_DEFAULT)
    for row in rows:
        if not isinstance(row, dict):
            continue
        gate = fa_gate(row, cfg)
        row["fa_gate_pass"] = gate["fa_gate_pass"]
        row["a_candidate"] = gate["a_candidate"]
        row["fa_score"] = gate["fa_score"]
        row["fa_label"] = gate["fa_label"]
        row["fa_reasons_ko"] = gate["fa_reasons_ko"]
        row["fa_comment"] = gate["comment"]
        row["fa"] = gate
    return rows
